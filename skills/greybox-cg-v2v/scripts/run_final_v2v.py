#!/usr/bin/env python3
"""Approval-gated, resumable wrapper for greybox-cg-v2v final V2V calls."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Callable

from greybox_manifest import (
    ManifestError,
    load_manifest,
    mark_final_failed,
    mark_final_ready,
    mark_final_started,
    save_manifest,
    sha256_file,
    utc_now,
    validate_manifest,
)

AI_MODEL_INPUT_ENV = "AI_MODEL_CALLING_INPUT"
DEFAULT_WAIT_TIMEOUT_SECONDS = 540.0
MAX_GREYBOX_DURATION_SECONDS = 10
SUPPORTED_V2V_MODELS = {
    "seedance2_720p",
    "seedance2_1080p",
    "seedance2_fast_720p",
    "seedance2_fast_1080p",
}
SUPPORTED_SEEDANCE_ASPECT_RATIOS = {"16:9", "9:16", "1:1", "4:3", "3:4", "21:9", "adaptive"}
Downloader = Callable[[str, Path], dict[str, Any]]
WORKER_SCRIPT = Path(__file__).with_name("final_v2v_worker.py")
TRUSTED_CANVAS_ENV_NAMES = ("canvas_id", "CANVAS_ID", "SEELE_CANVAS_ID")
TRUSTED_SESSION_ENV_NAMES = (
    "trace_id",
    "X_SEELE_CANVAS_TRACE_ID",
    "SEELE_CANVAS_TRACE_ID",
    "session_canvas_id",
)


class DiagnosticError(ManifestError):
    """A deterministic, field-level local preflight failure."""

    def __init__(self, code: str, field: str, message: str, *, stage: str = "preflight") -> None:
        super().__init__(message)
        self.code = code
        self.field = field
        self.stage = stage
        self.retryable = False


def _approval_gate_enabled() -> bool:
    value = os.environ.get("GREYBOX_REQUIRE_APPROVAL", "true").strip().lower()
    return value not in {"0", "false", "no"}


def _job_id(idempotency_key: str) -> str:
    return "gbv2v_" + hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()[:16]


def _public_https_url(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("https://") and "://localhost" not in value and "://127." not in value


def _request_sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _canonical_uuid(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = str(uuid.UUID(value))
    except (ValueError, AttributeError):
        return None
    return parsed if parsed == value.lower() else None


def _single_runtime_value(names: tuple[str, ...], *, field: str) -> str:
    values = {os.environ[name].strip() for name in names if os.environ.get(name, "").strip()}
    if not values:
        raise DiagnosticError(f"runtime.{field}.missing", field, f"trusted runtime {field} is required")
    if len(values) != 1:
        raise DiagnosticError(f"runtime.{field}.conflict", field, f"trusted runtime {field} aliases disagree")
    return values.pop()


def validate_execution_identity(manifest: dict[str, Any]) -> tuple[str, str]:
    """Bind editable manifest identity to runtime-injected Canvas/session identity."""

    canvas_id = manifest.get("canvas_id")
    canonical_canvas = _canonical_uuid(canvas_id)
    if not canonical_canvas:
        raise DiagnosticError(
            "manifest.canvas_id.invalid_uuid", "canvas_id", "manifest canvas_id must be a canonical UUID"
        )
    trusted_canvas = _single_runtime_value(TRUSTED_CANVAS_ENV_NAMES, field="canvas_id")
    canonical_trusted = _canonical_uuid(trusted_canvas)
    if not canonical_trusted:
        raise DiagnosticError(
            "runtime.canvas_id.invalid_uuid", "canvas_id", "trusted runtime canvas_id must be a canonical UUID"
        )
    if canonical_canvas != canonical_trusted:
        raise DiagnosticError(
            "manifest.canvas_id.runtime_mismatch",
            "canvas_id",
            "manifest canvas_id does not match trusted runtime canvas_id",
        )

    session_canvas_id = manifest.get("session_canvas_id")
    if not isinstance(session_canvas_id, str) or "|" not in session_canvas_id:
        raise DiagnosticError(
            "manifest.session_canvas_id.invalid",
            "session_canvas_id",
            "manifest session_canvas_id must be a pipe-delimited runtime trace",
        )
    session_canvas_uuid = _canonical_uuid(session_canvas_id.split("|", 1)[0].strip())
    if session_canvas_uuid != canonical_canvas:
        raise DiagnosticError(
            "manifest.session_canvas_id.canvas_mismatch",
            "session_canvas_id",
            "manifest session_canvas_id is not bound to canvas_id",
        )
    trusted_session = _single_runtime_value(TRUSTED_SESSION_ENV_NAMES, field="session_canvas_id")
    if session_canvas_id != trusted_session:
        raise DiagnosticError(
            "manifest.session_canvas_id.runtime_mismatch",
            "session_canvas_id",
            "manifest session_canvas_id does not match trusted runtime session",
        )

    game_id = manifest.get("game_id")
    if isinstance(game_id, str) and game_id.lower() in {canonical_canvas, session_canvas_id.lower()}:
        raise DiagnosticError(
            "manifest.game_id.identity_collision",
            "game_id",
            "game_id must be distinct from Canvas and session identity",
        )
    return canonical_canvas, trusted_session


def assert_v2v_allowed(manifest: dict[str, Any], approved_revision_id: str, current_latest_revision_id: str) -> None:
    validate_execution_identity(manifest)
    try:
        validate_manifest(manifest)
    except ManifestError as exc:
        message = str(exc)
        field = next(
            (
                candidate
                for candidate in (
                    "canvas_id",
                    "session_canvas_id",
                    "game_id",
                    "greybox_revision_id",
                    "latest_greybox_revision_id",
                    "generate_type",
                    "model_choice",
                    "aspect_ratio",
                    "duration",
                    "video_url",
                    "sha256",
                    "path",
                    "approval",
                    "final_render",
                    "artifacts",
                    "schema_version",
                )
                if candidate in message
            ),
            "manifest",
        )
        if "multimodal_reference" in message:
            field = "generate_type"
        if field in {"generate_type", "model_choice", "aspect_ratio", "duration", "video_url"}:
            raise DiagnosticError(
                f"request.{field}.invalid", f"final_render.request.{field}", message
            ) from exc
        raise DiagnosticError(f"manifest.{field}.invalid", field, message) from exc
    if _approval_gate_enabled() is not True:
        raise DiagnosticError(
            "approval.gate.disabled",
            "GREYBOX_REQUIRE_APPROVAL",
            "GREYBOX_REQUIRE_APPROVAL was disabled; refusing unsafe final V2V in this wrapper",
        )
    revision_id = manifest.get("greybox_revision_id")
    if approved_revision_id != revision_id:
        raise DiagnosticError(
            "approval.revision.mismatch", "approved_revision_id", "approved revision does not match manifest revision"
        )
    if current_latest_revision_id != revision_id:
        raise DiagnosticError(
            "approval.revision.stale",
            "current_latest_revision_id",
            "approved revision is stale; it is not the current latest revision",
        )
    if manifest.get("latest_greybox_revision_id", revision_id) != revision_id:
        raise DiagnosticError(
            "manifest.revision.stale",
            "latest_greybox_revision_id",
            "manifest revision is stale; latest_greybox_revision_id differs",
        )
    if manifest.get("state") == "failed":
        raise DiagnosticError(
            "manifest.state.failed", "state", "manifest is failed; explicit retry or reconciliation is required"
        )
    if manifest.get("state") not in {"greybox_approved", "rendering_final", "final_ready"}:
        raise DiagnosticError("approval.state.invalid", "state", "manifest is not approved for final V2V")

    approval = manifest.get("approval") or {}
    final_render = manifest.get("final_render") or {}
    if approval.get("status") != "approved" or approval.get("approved_revision_id") != revision_id:
        raise DiagnosticError(
            "approval.binding.invalid", "approval", "approval is not bound to the current manifest revision"
        )
    if final_render.get("source_greybox_revision_id") != revision_id or final_render.get("allowed") is not True:
        raise DiagnosticError(
            "final_render.binding.invalid",
            "final_render.source_greybox_revision_id",
            "final_render is not bound and allowed for the current revision",
        )

    approved_path = approval.get("approved_greybox_video_path")
    render_path = final_render.get("v2v_input_video_path")
    approved_url = approval.get("approved_greybox_video_url")
    render_url = final_render.get("v2v_input_video_url")
    if not approved_path or approved_path != render_path:
        raise DiagnosticError(
            "approval.video_path.mismatch",
            "final_render.v2v_input_video_path",
            "approved video path and final_render input path differ",
        )
    if not _public_https_url(approved_url) or approved_url != render_url:
        raise DiagnosticError(
            "approval.video_url.mismatch",
            "final_render.v2v_input_video_url",
            "approved public video URL and final_render input URL differ",
        )
    if not Path(approved_path).exists():
        raise DiagnosticError(
            "approval.video_path.missing", "approval.approved_greybox_video_path", "approved video path does not exist"
        )
    actual_hash = sha256_file(approved_path)
    if approval.get("approved_greybox_video_sha256") != actual_hash:
        raise DiagnosticError(
            "approval.video_sha256.mismatch",
            "approval.approved_greybox_video_sha256",
            "approved video sha256 does not match path contents",
        )
    if final_render.get("v2v_input_video_sha256") != actual_hash:
        raise DiagnosticError(
            "final_render.video_sha256.mismatch",
            "final_render.v2v_input_video_sha256",
            "final_render video sha256 does not match path contents",
        )
    if not final_render.get("idempotency_key"):
        raise DiagnosticError(
            "final_render.idempotency_key.missing",
            "final_render.idempotency_key",
            "final_render.idempotency_key is required",
        )


def parse_downstream_argv(raw: str, *, source: str = "downstream argv") -> list[str]:
    try:
        argv = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DiagnosticError("argv.json.invalid", "downstream_argv", f"{source} must be a JSON array: {exc}") from exc
    if not isinstance(argv, list) or not argv or not all(
        isinstance(item, str) and item and "\x00" not in item for item in argv
    ):
        raise DiagnosticError(
            "argv.structure.invalid", "downstream_argv", f"{source} must be a non-empty JSON string array"
        )
    if argv.count("--input-env") != 1:
        raise DiagnosticError(
            "argv.input_env.invalid",
            "downstream_argv",
            "downstream executor must declare --input-env AI_MODEL_CALLING_INPUT exactly once",
        )
    index = argv.index("--input-env")
    if index + 1 >= len(argv) or argv[index + 1] != AI_MODEL_INPUT_ENV:
        raise DiagnosticError(
            "argv.input_env.invalid", "downstream_argv", "downstream executor must read AI_MODEL_CALLING_INPUT"
        )
    return argv


def default_downstream_argv() -> list[str]:
    executor = Path(__file__).resolve().parents[2] / "ai-model-calling" / "scripts" / "video_skill.py"
    if not executor.is_file():
        raise ManifestError(f"default downstream executor not found: {executor}")
    return [sys.executable, str(executor), "--input-env", AI_MODEL_INPUT_ENV]


def resolve_downstream_argv(args: argparse.Namespace) -> tuple[list[str], str]:
    selected = sum(bool(value) for value in (args.downstream_argv_json, args.downstream_argv_file, args.use_default_downstream))
    if selected != 1:
        raise DiagnosticError(
            "argv.source.invalid",
            "downstream_argv",
            "dispatch requires exactly one of --downstream-argv-file, --use-default-downstream, or legacy --downstream-argv-json",
        )
    if args.downstream_argv_file:
        source = Path(args.downstream_argv_file)
        try:
            raw = source.read_text(encoding="utf-8")
        except OSError as exc:
            raise DiagnosticError(
                "argv.file.unreadable", "downstream_argv_file", "cannot read downstream argv file"
            ) from exc
        return parse_downstream_argv(raw, source="downstream argv file"), "file"
    if args.use_default_downstream:
        return default_downstream_argv(), "controlled_default"
    return parse_downstream_argv(args.downstream_argv_json, source="legacy downstream argv"), "legacy_inline_json"


def build_executor_payload(manifest: dict[str, Any], job_id: str) -> dict[str, Any]:
    final_render = manifest["final_render"]
    config = final_render.get("request") or {}
    prompt = str(config.get("prompt") or "").strip()
    if not prompt:
        raise ManifestError("final_render.request.prompt is required")
    payload = {
        "task_name": "seedance_generate",
        "generate_type": config.get("generate_type"),
        "model_choice": config.get("model_choice", "seedance2_1080p"),
        "prompt": prompt,
        "video_url": final_render["v2v_input_video_url"],
        "aspect_ratio": config.get("aspect_ratio", "16:9"),
        "duration": config.get("duration", 8),
        "camera_fixed": config.get("camera_fixed", False),
        "canvas_id": manifest["canvas_id"],
        "seele_canvas_trace_id": manifest["session_canvas_id"],
        # video_skill forwards task_id to videoGen. The other fields are audit bindings.
        "task_id": job_id,
        "greybox_revision_id": manifest["greybox_revision_id"],
        "greybox_video_sha256": final_render["v2v_input_video_sha256"],
        "idempotency_key": final_render["idempotency_key"],
        "job_id": job_id,
    }
    for field in ("image_url", "image_urls", "audio_urls", "generate_audio"):
        if field in config:
            payload[field] = config[field]
    return payload


def load_validation_policy(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    try:
        policy = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"cannot load validation policy: {exc}") from exc
    if not isinstance(policy, dict) or set(policy) - {"duration_seconds_by_model"}:
        raise ManifestError("validation policy supports only duration_seconds_by_model")
    limits = policy.get("duration_seconds_by_model", {})
    if not isinstance(limits, dict):
        raise ManifestError("validation policy duration_seconds_by_model must be an object")
    for model, bounds in limits.items():
        if model not in SUPPORTED_V2V_MODELS or not isinstance(bounds, dict) or set(bounds) - {"min", "max"}:
            raise ManifestError("validation policy contains an invalid model or duration bound")
        for name, value in bounds.items():
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ManifestError(f"validation policy {model}.{name} must be a positive integer")
        if bounds.get("min", 1) > bounds.get("max", sys.maxsize):
            raise ManifestError(f"validation policy {model} min exceeds max")
    return policy


def validate_executor_payload(payload: dict[str, Any], policy: dict[str, Any] | None = None) -> None:
    if payload.get("generate_type") != "multimodal_reference":
        raise ManifestError("generate_type must be multimodal_reference for greybox final V2V")
    model = payload.get("model_choice")
    if model not in SUPPORTED_V2V_MODELS:
        raise ManifestError("model_choice must be a Seedance 2 video-reference model: " + ", ".join(sorted(SUPPORTED_V2V_MODELS)))
    aspect_ratio = payload.get("aspect_ratio")
    if aspect_ratio not in SUPPORTED_SEEDANCE_ASPECT_RATIOS:
        raise ManifestError("aspect_ratio is unsupported for Seedance: " + ", ".join(sorted(SUPPORTED_SEEDANCE_ASPECT_RATIOS)))
    duration = payload.get("duration")
    if isinstance(duration, bool) or not isinstance(duration, int) or duration <= 0:
        raise ManifestError("duration must be a positive integer")
    if duration > MAX_GREYBOX_DURATION_SECONDS:
        raise ManifestError(f"duration must be <= {MAX_GREYBOX_DURATION_SECONDS}s for greybox final V2V")
    bounds = ((policy or {}).get("duration_seconds_by_model") or {}).get(model, {})
    if duration < bounds.get("min", 1) or duration > bounds.get("max", sys.maxsize):
        raise ManifestError(f"duration {duration} is rejected by configured policy for {model}")
    if not _public_https_url(payload.get("video_url")):
        raise ManifestError("video_url must be a public HTTPS URL")


def validate_request_construction(
    manifest: dict[str, Any], job_id: str, validation_policy_file: str | None
) -> dict[str, Any]:
    try:
        payload = build_executor_payload(manifest, job_id)
        policy = load_validation_policy(validation_policy_file)
        validate_executor_payload(payload, policy)
    except DiagnosticError:
        raise
    except ManifestError as exc:
        message = str(exc)
        field = next(
            (
                name
                for name in (
                    "prompt",
                    "generate_type",
                    "model_choice",
                    "aspect_ratio",
                    "duration",
                    "video_url",
                    "validation_policy",
                )
                if name in message
            ),
            "request",
        )
        raise DiagnosticError(f"request.{field}.invalid", f"final_render.request.{field}", message) from exc
    return payload


def worker_job_paths(manifest_path: Path, job_id: str) -> dict[str, Path]:
    job_dir = manifest_path.resolve().parent / ".greybox_v2v_jobs" / job_id
    return {
        "job_dir": job_dir,
        "request": job_dir / "request.json",
        "status": job_dir / "status.json",
        "result": job_dir / "result.json",
        "stdout": job_dir / "downstream.stdout",
        "stderr": job_dir / "downstream.stderr",
        "helper_log": job_dir / "worker.log",
    }


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2, sort_keys=True)
            file.write("\n")
        os.replace(temp_name, path)
    finally:
        Path(temp_name).unlink(missing_ok=True)


def write_worker_request(paths: dict[str, Path], argv: list[str], payload: dict[str, Any], job_id: str) -> None:
    paths["job_dir"].mkdir(parents=True, exist_ok=True)
    request = {
        "version": 1,
        "job_id": job_id,
        "argv": argv,
        "model_input": payload,
        "status_path": str(paths["status"]),
        "result_path": str(paths["result"]),
        "stdout_path": str(paths["stdout"]),
        "stderr_path": str(paths["stderr"]),
    }
    write_json_atomic(paths["request"], request)
    # Persist a durable receipt before starting the detached process. Otherwise a short caller
    # wait can return before the worker has created status.json, leaving no inspectable job state.
    write_json_atomic(
        paths["status"],
        {
            "version": 1,
            "job_id": job_id,
            "state": "dispatch_prepared",
            "prepared_at": utc_now(),
        },
    )


def launch_persistent_worker(paths: dict[str, Path]) -> subprocess.Popen[bytes]:
    if not WORKER_SCRIPT.is_file():
        raise ManifestError(f"persistent worker helper not found: {WORKER_SCRIPT}")
    command = [sys.executable, str(WORKER_SCRIPT), "--request", str(paths["request"])]
    popen_options: dict[str, Any] = {"start_new_session": True}
    if os.name == "nt":
        popen_options = {
            "creationflags": getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        }
    with paths["helper_log"].open("ab") as helper_log:
        return subprocess.Popen(
            command,
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=helper_log,
            stderr=subprocess.STDOUT,
            close_fds=True,
            **popen_options,
        )


def load_worker_result(receipt: dict[str, Any]) -> dict[str, Any] | None:
    path_value = receipt.get("result_path")
    if not isinstance(path_value, str) or not path_value:
        return None
    path = Path(path_value)
    if not path.is_file():
        return None
    try:
        envelope = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"cannot load worker result envelope: {exc}") from exc
    if not isinstance(envelope, dict) or envelope.get("job_id") != receipt.get("job_id"):
        raise ManifestError("worker result envelope does not match dispatch receipt")
    return envelope


def _read_worker_output(path_value: Any) -> str:
    if not isinstance(path_value, str) or not path_value:
        return ""
    try:
        return Path(path_value).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def completed_process_from_worker(
    receipt: dict[str, Any], envelope: dict[str, Any]
) -> subprocess.CompletedProcess[str]:
    returncode = envelope.get("returncode")
    if isinstance(returncode, bool) or not isinstance(returncode, int):
        raise ManifestError("worker result envelope has invalid returncode")
    stdout = _read_worker_output(receipt.get("stdout_path"))
    stderr = _read_worker_output(receipt.get("stderr_path"))
    if envelope.get("worker_error"):
        stderr = "\n".join(part for part in (stderr, str(envelope["worker_error"])) if part)
    return subprocess.CompletedProcess(["persistent-greybox-worker"], returncode, stdout, stderr)


def parse_downstream_result(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    if result.returncode != 0:
        raise ManifestError(f"downstream_exit_{result.returncode}")
    return parse_reconcile_result_text(result.stdout)


def parse_reconcile_result_text(raw: str) -> dict[str, Any]:
    if not raw.strip():
        raise ManifestError("downstream_empty_result")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ManifestError("downstream_invalid_json") from exc
    if not isinstance(payload, dict) or payload.get("success") is not True:
        code = payload.get("error_code") if isinstance(payload, dict) else None
        raise ManifestError(str(code or "downstream_reported_failure"))
    if not _public_https_url(payload.get("url")):
        raise ManifestError("downstream_missing_public_video_url")
    return payload


def default_final_output_path(manifest_path: Path, job_id: str) -> Path:
    return manifest_path.resolve().parent / "final_videos" / f"{job_id}.mp4"


def download_final_video(url: str, destination: Path) -> dict[str, Any]:
    destination = destination.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".download", dir=destination.parent)
    os.close(fd)
    temp = Path(temp_name)
    try:
        with urllib.request.urlopen(url, timeout=120) as response, temp.open("wb") as output:
            shutil.copyfileobj(response, output)
        size = temp.stat().st_size
        if size <= 0:
            raise ManifestError("downloaded final video is empty")
        digest = sha256_file(temp)
        os.replace(temp, destination)
        return {"path": str(destination), "sha256": digest, "bytes": size, "downloaded_at": utc_now()}
    except Exception:
        temp.unlink(missing_ok=True)
        raise


def _set_dispatch_receipt(
    manifest: dict[str, Any],
    *,
    payload: dict[str, Any],
    job_id: str,
    argv_source: str,
    worker_paths: dict[str, Path],
) -> dict[str, Any]:
    claimed = mark_final_started(manifest, job_id=job_id)
    claimed["final_render"]["dispatch_receipt"] = {
        "receipt_version": 1,
        "job_id": job_id,
        "task_id": job_id,
        "idempotency_key": claimed["final_render"]["idempotency_key"],
        "request_sha256": _request_sha256(payload),
        "argv_source": argv_source,
        "status": "dispatch_prepared",
        "request_path": str(worker_paths["request"]),
        "status_path": str(worker_paths["status"]),
        "result_path": str(worker_paths["result"]),
        "stdout_path": str(worker_paths["stdout"]),
        "stderr_path": str(worker_paths["stderr"]),
        "helper_log_path": str(worker_paths["helper_log"]),
        "prepared_at": utc_now(),
    }
    claimed["final_render"]["requires_reconciliation"] = False
    return claimed


def _mark_wait_timeout(manifest: dict[str, Any], wait_timeout_seconds: float) -> dict[str, Any]:
    manifest["state"] = "rendering_final"
    manifest["updated_at"] = utc_now()
    final_render = manifest["final_render"]
    final_render["state"] = "wait_timeout"
    final_render["requires_reconciliation"] = True
    receipt = final_render.setdefault("dispatch_receipt", {})
    receipt["status"] = "wait_timeout"
    receipt["wait_timeout_seconds"] = wait_timeout_seconds
    receipt["wait_timed_out_at"] = utc_now()
    return manifest


def _delivery_failure(manifest: dict[str, Any], output: dict[str, Any], error: Exception) -> dict[str, Any]:
    remote_ready = mark_final_ready(manifest, final_video_url=output["url"])
    failed = mark_final_failed(
        remote_ready,
        error_message=str(error),
        failed_stage="delivery",
        error_code="final_video_download_failed",
        retryable=True,
    )
    failed["final_render"]["output"].update(
        {"delivery_state": "failed", "delivery_error": failed["error_message_sanitized"]}
    )
    failed["final_render"]["requires_reconciliation"] = False
    receipt = failed["final_render"].setdefault("dispatch_receipt", {})
    receipt["status"] = "render_succeeded_delivery_failed"
    return failed


def _complete_delivery(
    manifest: dict[str, Any], output: dict[str, Any], destination: Path, downloader: Downloader
) -> dict[str, Any]:
    delivery = downloader(output["url"], destination)
    completed = mark_final_ready(manifest, final_video_url=output["url"], final_video_path=delivery["path"])
    clean_output = {key: value for key, value in output.items() if key not in {"delivery_error", "delivery_state"}}
    completed["final_render"]["output"] = {**clean_output, **delivery, "delivery_state": "ready"}
    artifact = next(item for item in completed["artifacts"] if item.get("artifact_type") == "final_video")
    artifact["sha256"] = delivery["sha256"]
    artifact["size_bytes"] = delivery["bytes"]
    artifact["metadata"].update(
        {
            "source_url": output["url"],
            "sha256": delivery["sha256"],
            "size_bytes": delivery["bytes"],
            "downloaded_at": delivery["downloaded_at"],
            "delivery_state": "ready",
        }
    )
    completed["final_render"]["requires_reconciliation"] = False
    receipt = completed["final_render"].setdefault("dispatch_receipt", {})
    receipt["status"] = "completed"
    receipt["completed_at"] = utc_now()
    return completed


def _persist_delivery(
    manifest: dict[str, Any], output: dict[str, Any], manifest_path: Path, destination: Path, downloader: Downloader
) -> tuple[dict[str, Any], bool]:
    try:
        completed = _complete_delivery(manifest, output, destination, downloader)
    except Exception as exc:
        failed = _delivery_failure(manifest, output, exc)
        save_manifest(failed, manifest_path)
        return failed, False
    save_manifest(completed, manifest_path)
    return completed, True


def _finalize_completed_process(
    manifest: dict[str, Any],
    result: subprocess.CompletedProcess[str],
    manifest_path: Path,
    final_output_path: str | None,
    downloader: Downloader,
    *,
    reconciled: bool,
) -> int:
    final_render = manifest["final_render"]
    job_id = final_render["job_id"]
    try:
        output = parse_downstream_result(result)
    except ManifestError as exc:
        diagnostic: dict[str, Any] = {}
        try:
            diagnostic = json.loads(result.stdout.strip()) if result.stdout.strip() else {}
        except (json.JSONDecodeError, IndexError):
            pass
        failed = mark_final_failed(
            manifest,
            error_message=str(diagnostic.get("message") or result.stderr or result.stdout or exc),
            failed_stage="v2v",
            error_code=str(diagnostic.get("error_code") or exc),
            retryable=bool(diagnostic.get("retryable", False)),
        )
        receipt = failed["final_render"]["dispatch_receipt"]
        receipt["status"] = "render_failed"
        if reconciled:
            receipt["reconciled_at"] = utc_now()
        save_manifest(failed, manifest_path)
        print(
            json.dumps(
                {"success": False, "reconciled": reconciled, "render_failed": True, "message": str(exc)}
            ),
            file=sys.stderr,
        )
        return result.returncode or 1

    destination = Path(final_output_path) if final_output_path else default_final_output_path(manifest_path, job_id)
    completed, delivered = _persist_delivery(manifest, output, manifest_path, destination, downloader)
    if not delivered:
        print(
            json.dumps(
                {
                    "success": False,
                    "reconciled": reconciled,
                    "stage": "delivery",
                    "job_id": job_id,
                    "url": output["url"],
                }
            ),
            file=sys.stderr,
        )
        return 4
    print(
        json.dumps(
            {
                "success": True,
                "reconciled": reconciled,
                "job_id": job_id,
                **completed["final_render"]["output"],
            }
        )
    )
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Run or reconcile final V2V only after manifest approval passes.")
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--approved-revision-id", required=True)
    ap.add_argument("--current-latest-revision-id", required=True)
    ap.add_argument("--downstream-argv-file", help="Preferred: UTF-8 file containing a JSON argv array.")
    ap.add_argument("--use-default-downstream", action="store_true", help="Use the checked-in ai-model-calling video executor.")
    ap.add_argument("--downstream-argv-json", help="Legacy compatibility; prefer --downstream-argv-file.")
    ap.add_argument("--validation-policy-file", help="Optional JSON model-specific duration bounds.")
    ap.add_argument("--wait-timeout-seconds", type=float, default=DEFAULT_WAIT_TIMEOUT_SECONDS)
    ap.add_argument("--reconcile-result-file", help="Apply a saved successful executor result without dispatching again.")
    ap.add_argument("--resume-delivery", action="store_true", help="Retry only the download for a prior delivery failure.")
    ap.add_argument("--final-output-path", help="Defaults to <manifest-dir>/final_videos/<job_id>.mp4.")
    ap.add_argument("--out-manifest", help="Defaults to atomically updating --manifest in place.")
    ap.add_argument(
        "--diagnostic-receipt",
        help="Safe JSON receipt path; defaults to <manifest>.final-v2v-receipt.json.",
    )
    return ap


def run(args: argparse.Namespace, *, downloader: Downloader = download_final_video) -> int:
    manifest_path = Path(args.out_manifest or args.manifest)
    source_path = manifest_path if args.out_manifest and manifest_path.exists() else Path(args.manifest)
    manifest = load_manifest(source_path)

    if args.resume_delivery:
        final_render = manifest.get("final_render") or {}
        output = final_render.get("output") or {}
        if manifest.get("failed_stage") != "delivery" or not _public_https_url(output.get("url")):
            raise ManifestError("--resume-delivery requires a prior delivery failure with a saved final URL")
        job_id = final_render.get("job_id")
        if not job_id:
            raise ManifestError("delivery resume requires final_render.job_id")
        destination = Path(args.final_output_path) if args.final_output_path else default_final_output_path(manifest_path, job_id)
        completed, delivered = _persist_delivery(manifest, output, manifest_path, destination, downloader)
        if not delivered:
            print(json.dumps({"success": False, "stage": "delivery", "url": output["url"]}), file=sys.stderr)
            return 4
        print(json.dumps({"success": True, "resumed_delivery": True, "job_id": job_id, **completed["final_render"]["output"]}))
        return 0

    assert_v2v_allowed(manifest, args.approved_revision_id, args.current_latest_revision_id)
    final_render = manifest["final_render"]
    if manifest.get("state") == "final_ready" and final_render.get("job_id"):
        print(json.dumps({"success": True, "duplicate_suppressed": True, "job_id": final_render["job_id"]}))
        return 0

    receipt = final_render.get("dispatch_receipt") or {}
    if manifest.get("state") == "rendering_final" and receipt:
        worker_envelope = load_worker_result(receipt)
        if worker_envelope is not None:
            result = completed_process_from_worker(receipt, worker_envelope)
            return _finalize_completed_process(
                manifest,
                result,
                manifest_path,
                args.final_output_path,
                downloader,
                reconciled=True,
            )

    if args.reconcile_result_file:
        if manifest.get("state") != "rendering_final" or not final_render.get("dispatch_receipt"):
            raise ManifestError("reconciliation requires a rendering_final manifest with a dispatch receipt")
        try:
            raw_result = Path(args.reconcile_result_file).read_text(encoding="utf-8")
        except OSError as exc:
            raise ManifestError(f"cannot read reconcile result file: {exc}") from exc
        try:
            output = parse_reconcile_result_text(raw_result)
        except ManifestError as exc:
            try:
                diagnostic = json.loads(raw_result)
            except json.JSONDecodeError:
                raise exc
            if not isinstance(diagnostic, dict) or diagnostic.get("success") is not False:
                raise exc
            failed = mark_final_failed(
                manifest,
                error_message=str(diagnostic.get("message") or exc),
                failed_stage="v2v",
                error_code=str(diagnostic.get("error_code") or "downstream_reported_failure"),
                retryable=bool(diagnostic.get("retryable", False)),
            )
            receipt = failed["final_render"]["dispatch_receipt"]
            receipt["status"] = "render_failed"
            receipt["reconciled_at"] = utc_now()
            save_manifest(failed, manifest_path)
            print(
                json.dumps({"success": False, "reconciled": True, "render_failed": True, "message": str(exc)}),
                file=sys.stderr,
            )
            return 1
        job_id = final_render["job_id"]
        destination = Path(args.final_output_path) if args.final_output_path else default_final_output_path(manifest_path, job_id)
        completed, delivered = _persist_delivery(manifest, output, manifest_path, destination, downloader)
        if not delivered:
            print(json.dumps({"success": False, "stage": "delivery", "job_id": job_id, "url": output["url"]}), file=sys.stderr)
            return 4
        print(json.dumps({"success": True, "reconciled": True, "job_id": job_id, **completed["final_render"]["output"]}))
        return 0

    if manifest.get("state") == "rendering_final" and final_render.get("job_id"):
        print(
            json.dumps(
                {
                    "success": False,
                    "duplicate_suppressed": True,
                    "job_id": final_render["job_id"],
                    "status": final_render.get("state"),
                    "reconciliation_required": True,
                }
            )
        )
        return 3

    argv, argv_source = resolve_downstream_argv(args)
    job_id = _job_id(final_render["idempotency_key"])
    payload = validate_request_construction(manifest, job_id, args.validation_policy_file)
    paths = worker_job_paths(manifest_path, job_id)
    write_worker_request(paths, argv, payload, job_id)
    claimed = _set_dispatch_receipt(
        manifest,
        payload=payload,
        job_id=job_id,
        argv_source=argv_source,
        worker_paths=paths,
    )
    save_manifest(claimed, manifest_path)

    try:
        worker = launch_persistent_worker(paths)
    except OSError as exc:
        failed = mark_final_failed(
            claimed,
            error_message=str(exc),
            failed_stage="dispatch",
            error_code="persistent_worker_launch_failed",
            retryable=True,
        )
        failed["final_render"]["dispatch_receipt"]["status"] = "worker_launch_failed"
        save_manifest(failed, manifest_path)
        print(json.dumps({"success": False, "stage": "dispatch", "message": str(exc)}), file=sys.stderr)
        return 1

    claimed["final_render"]["dispatch_receipt"].update(
        {"status": "dispatched", "worker_pid": worker.pid, "dispatched_at": utc_now()}
    )
    save_manifest(claimed, manifest_path)

    wait_timeout = args.wait_timeout_seconds if args.wait_timeout_seconds > 0 else None
    try:
        worker.wait(timeout=wait_timeout)
    except subprocess.TimeoutExpired:
        # Popen.wait(timeout=...) never terminates the detached worker. It keeps producing the
        # deterministic result envelope for a later invocation to reconcile automatically.
        timed_out = _mark_wait_timeout(claimed, args.wait_timeout_seconds)
        save_manifest(timed_out, manifest_path)
        print(
            json.dumps(
                {
                    "success": False,
                    "wait_timeout": True,
                    "render_failed": False,
                    "worker_continues": True,
                    "job_id": job_id,
                    "result_path": str(paths["result"]),
                    "reconciliation_required": True,
                }
            ),
            file=sys.stderr,
        )
        return 3

    worker_envelope = load_worker_result(claimed["final_render"]["dispatch_receipt"])
    if worker_envelope is None:
        failed = mark_final_failed(
            claimed,
            error_message=f"persistent worker exited {worker.returncode} without a result envelope",
            failed_stage="dispatch",
            error_code="persistent_worker_result_missing",
            retryable=False,
        )
        failed["final_render"]["dispatch_receipt"]["status"] = "worker_result_missing"
        save_manifest(failed, manifest_path)
        print(json.dumps({"success": False, "stage": "dispatch", "job_id": job_id}), file=sys.stderr)
        return 1
    result = completed_process_from_worker(claimed["final_render"]["dispatch_receipt"], worker_envelope)
    return _finalize_completed_process(
        claimed,
        result,
        manifest_path,
        args.final_output_path,
        downloader,
        reconciled=False,
    )


def _manifest_digest(path: Path) -> str | None:
    try:
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _receipt_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _safe_external_id(container: dict[str, Any], *names: str) -> str | None:
    for name in names:
        value = container.get(name)
        if isinstance(value, (str, int)) and not isinstance(value, bool):
            text = str(value).strip()
            if text and len(text) <= 200:
                return text
    return None


def _receipt_runtime_value(names: tuple[str, ...]) -> str | None:
    values = {os.environ[name].strip() for name in names if os.environ.get(name, "").strip()}
    if len(values) != 1:
        return None
    value = values.pop()
    return value if len(value) <= 200 else None


def build_diagnostic_receipt(
    manifest_path: Path,
    *,
    code: str,
    stage: str,
    retryable: bool,
    field: str | None = None,
) -> dict[str, Any]:
    manifest = _receipt_manifest(manifest_path)
    final_render = manifest.get("final_render") if isinstance(manifest.get("final_render"), dict) else {}
    dispatch = final_render.get("dispatch_receipt") if isinstance(final_render.get("dispatch_receipt"), dict) else {}
    output = final_render.get("output") if isinstance(final_render.get("output"), dict) else {}
    return {
        "receiptVersion": 1,
        "canvasId": _receipt_runtime_value(TRUSTED_CANVAS_ENV_NAMES)
        or _safe_external_id(manifest, "canvas_id"),
        "sessionCanvasId": _receipt_runtime_value(TRUSTED_SESSION_ENV_NAMES)
        or _safe_external_id(manifest, "session_canvas_id"),
        "gameId": _safe_external_id(manifest, "game_id"),
        "revisionId": _safe_external_id(manifest, "greybox_revision_id"),
        "manifestDigest": _manifest_digest(manifest_path),
        "finalJobId": _safe_external_id(final_render, "job_id"),
        "stage": stage,
        "diagnosticCode": code,
        "field": field,
        "retryable": bool(retryable),
        "requestId": _safe_external_id(output, "requestId", "request_id")
        or _safe_external_id(dispatch, "requestId", "request_id"),
        "taskId": _safe_external_id(output, "taskId", "task_id")
        or _safe_external_id(dispatch, "taskId", "task_id"),
    }


def _receipt_path(args: argparse.Namespace) -> Path:
    if args.diagnostic_receipt:
        return Path(args.diagnostic_receipt)
    return Path(str(args.out_manifest or args.manifest) + ".final-v2v-receipt.json")


def _write_diagnostic_receipt(args: argparse.Namespace, receipt: dict[str, Any]) -> None:
    write_json_atomic(_receipt_path(args), receipt)


def _receipt_after_run(args: argparse.Namespace, returncode: int) -> dict[str, Any]:
    manifest_path = Path(args.out_manifest or args.manifest)
    manifest = _receipt_manifest(manifest_path)
    final_render = manifest.get("final_render") if isinstance(manifest.get("final_render"), dict) else {}
    if returncode == 0:
        code = "ok"
        stage = "completed" if manifest.get("state") == "final_ready" else "reconciled"
        retryable = False
    elif returncode == 3:
        code = "render.wait_timeout"
        stage = "wait"
        retryable = True
    elif returncode == 4:
        code = str(manifest.get("error_code") or "delivery.failed")
        stage = "delivery"
        retryable = bool(manifest.get("retryable", True))
    else:
        code = str(manifest.get("error_code") or final_render.get("error_code") or "execution.failed")
        stage = str(manifest.get("failed_stage") or final_render.get("failed_stage") or "execution")
        retryable = bool(manifest.get("retryable", final_render.get("retryable", False)))
    return build_diagnostic_receipt(
        manifest_path,
        code=code,
        stage=stage,
        retryable=retryable,
    )


def main(argv: list[str] | None = None, *, downloader: Downloader = download_final_video) -> int:
    args = build_arg_parser().parse_args(argv)
    manifest_path = Path(args.out_manifest or args.manifest)
    try:
        returncode = run(args, downloader=downloader)
        _write_diagnostic_receipt(args, _receipt_after_run(args, returncode))
        return returncode
    except DiagnosticError as exc:
        receipt = build_diagnostic_receipt(
            manifest_path,
            code=exc.code,
            stage=exc.stage,
            retryable=exc.retryable,
            field=exc.field,
        )
        _write_diagnostic_receipt(args, receipt)
        print(json.dumps({"success": False, **receipt, "message": str(exc)[:500]}), file=sys.stderr)
        return 2
    except ManifestError as exc:
        receipt = build_diagnostic_receipt(
            manifest_path,
            code="preflight.invalid",
            stage="preflight",
            retryable=False,
            field="manifest",
        )
        _write_diagnostic_receipt(args, receipt)
        print(json.dumps({"success": False, **receipt, "message": str(exc)[:500]}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
