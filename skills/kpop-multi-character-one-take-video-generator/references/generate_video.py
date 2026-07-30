#!/usr/bin/env python3
"""End-to-end K-pop multi-character one-take video generator.

This orchestrator owns only the fixed product contract. It delegates local
file upload and paid video generation to the checked-in production Skills.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import compile_prompt  # noqa: E402
import validate_prompt  # noqa: E402

SKILL_NAME = "kpop-multi-character-one-take-video-generator"
INPUT_ENV_NAME = "KPOP_ONE_TAKE_INPUT"
EXECUTOR_INPUT_ENV_NAME = "AI_MODEL_CALLING_INPUT"
UPLOAD_TIMEOUT_SECONDS = 300
VIDEO_TIMEOUT_SECONDS = 3660
ALLOWED_REQUEST_FIELDS = {"references", "scene"}
ALLOWED_REFERENCE_FIELDS = {"name", "source"}
IMAGE_SUFFIXES = {
    ".avif",
    ".bmp",
    ".gif",
    ".heic",
    ".heif",
    ".jpeg",
    ".jpg",
    ".png",
    ".tif",
    ".tiff",
    ".webp",
}
REF_TOKEN_ANYWHERE = re.compile(r"\[image\d+\]")


class InputContractError(ValueError):
    """Raised when the public generator input is invalid."""


class SharedInfrastructureError(RuntimeError):
    """Raised when a required production Skill script is unavailable."""


class BoundaryProtocolError(RuntimeError):
    """Raised when a reused production boundary does not return JSON."""


class GenerationCancelled(RuntimeError):
    """Raised when the foreground generation is cancelled."""


@dataclass(frozen=True)
class Reference:
    name: str
    source: str
    remote: bool


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


class CommandRunner(Protocol):
    def run(
        self,
        argv: list[str],
        *,
        env: dict[str, str] | None,
        timeout_seconds: int,
    ) -> CommandResult: ...


class SubprocessRunner:
    """Run a child in the foreground and retain its complete JSON stdout."""

    def run(
        self,
        argv: list[str],
        *,
        env: dict[str, str] | None,
        timeout_seconds: int,
    ) -> CommandResult:
        process = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        try:
            stdout, stderr = process.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
            raise subprocess.TimeoutExpired(argv, timeout_seconds, output=stdout, stderr=stderr)
        except BaseException:
            process.terminate()
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
            raise
        return CommandResult(process.returncode, stdout, stderr)


def resolve_shared_infrastructure_paths() -> dict[str, Path]:
    skills_root = Path(__file__).resolve().parents[2]
    return {
        "upload": skills_root / "file-upload-to-cdn" / "references" / "upload_file_to_cdn.py",
        "video": skills_root / "ai-model-calling" / "scripts" / "video_skill.py",
    }


def _canonical_remote_url(source: str) -> str:
    parsed = urlsplit(source)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise InputContractError(f"reference URL must be public HTTP(S): {source!r}")
    return urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path,
            parsed.query,
            "",
        )
    )


def _normalize_reference(raw: Any, index: int) -> Reference:
    if isinstance(raw, str):
        source = raw.strip()
        name = f"Member {index + 1}"
    elif isinstance(raw, dict):
        extra_fields = sorted(set(raw) - ALLOWED_REFERENCE_FIELDS)
        if extra_fields:
            raise InputContractError(f"references[{index}] has unsupported fields: {', '.join(extra_fields)}")
        source_value = raw.get("source")
        name_value = raw.get("name")
        if not isinstance(source_value, str):
            raise InputContractError(f"references[{index}].source must be a non-empty string")
        source = source_value.strip()
        if name_value is None:
            name = f"Member {index + 1}"
        elif not isinstance(name_value, str) or not name_value.strip():
            raise InputContractError(f"references[{index}].name must be a non-empty string when provided")
        else:
            name = name_value.strip()
    else:
        raise InputContractError(f"references[{index}] must be a source string or object")

    if not source:
        raise InputContractError(f"references[{index}].source must be a non-empty string")
    if REF_TOKEN_ANYWHERE.search(name):
        raise InputContractError(f"references[{index}].name must not contain [imageN] syntax")

    parsed = urlsplit(source)
    if parsed.scheme.lower() in {"http", "https"}:
        return Reference(name=name, source=_canonical_remote_url(source), remote=True)
    if "://" in source:
        raise InputContractError(f"references[{index}].source uses an unsupported URL scheme")

    suffix = Path(source).suffix.lower()
    if suffix not in IMAGE_SUFFIXES:
        raise InputContractError(f"references[{index}].source must be a supported local image file: {source!r}")
    return Reference(name=name, source=source, remote=False)


def normalize_request(input_data: Any) -> tuple[list[Reference], str | None]:
    if not isinstance(input_data, dict):
        raise InputContractError("input must be a JSON object")
    extra_fields = sorted(set(input_data) - ALLOWED_REQUEST_FIELDS)
    if extra_fields:
        raise InputContractError(f"unsupported input fields: {', '.join(extra_fields)}")

    raw_references = input_data.get("references")
    if not isinstance(raw_references, list):
        raise InputContractError("references must be an ordered list of 2 to 4 unique images")
    if not (2 <= len(raw_references) <= 4):
        raise InputContractError(f"references must contain 2 to 4 items, got {len(raw_references)}")

    references = [_normalize_reference(raw, index) for index, raw in enumerate(raw_references)]
    seen_names: set[str] = set()
    seen_sources: set[tuple[str, str]] = set()
    for index, reference in enumerate(references):
        name_key = reference.name.casefold()
        if name_key in seen_names:
            raise InputContractError(f"duplicate reference name at index {index}: {reference.name!r}")
        seen_names.add(name_key)

        source_key = (
            ("url", reference.source)
            if reference.remote
            else ("path", os.path.normcase(str(Path(reference.source).expanduser().resolve(strict=False))))
        )
        if source_key in seen_sources:
            raise InputContractError(f"duplicate reference source at index {index}: {reference.source!r}")
        seen_sources.add(source_key)

    scene = input_data.get("scene")
    if scene is not None:
        if not isinstance(scene, str):
            raise InputContractError("scene must be a string when provided")
        scene = scene.strip() or None
        if scene and REF_TOKEN_ANYWHERE.search(scene):
            raise InputContractError("scene must not contain [imageN] reference tokens")
    return references, scene


def _parse_json_stdout(result: CommandResult, *, boundary: str) -> dict[str, Any]:
    raw = result.stdout.strip()
    if not raw:
        detail = result.stderr.strip() or f"{boundary} returned empty stdout"
        raise BoundaryProtocolError(detail)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise BoundaryProtocolError(f"{boundary} returned invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise BoundaryProtocolError(f"{boundary} output must be a JSON object")
    return payload


def _run_json_boundary(
    runner: CommandRunner,
    argv: list[str],
    *,
    env: dict[str, str] | None,
    timeout_seconds: int,
    boundary: str,
) -> tuple[CommandResult, dict[str, Any]]:
    try:
        result = runner.run(argv, env=env, timeout_seconds=timeout_seconds)
    except KeyboardInterrupt as exc:
        raise GenerationCancelled(f"{boundary} cancelled") from exc
    except OSError as exc:
        raise BoundaryProtocolError(f"{boundary} could not start: {exc}") from exc
    return result, _parse_json_stdout(result, boundary=boundary)


def _is_public_video_url(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    parsed = urlsplit(value.strip())
    return parsed.scheme.lower() in {"http", "https"} and bool(parsed.netloc)


def upload_reference(
    reference: Reference,
    *,
    upload_script: Path,
    runner: CommandRunner,
) -> str:
    if reference.remote:
        return reference.source
    result, payload = _run_json_boundary(
        runner,
        [sys.executable, str(upload_script), "--file", reference.source],
        env=None,
        timeout_seconds=UPLOAD_TIMEOUT_SECONDS,
        boundary="file upload",
    )
    if payload.get("success") is not True or result.returncode != 0:
        message = str(payload.get("message") or result.stderr.strip() or "file upload failed")
        raise SharedInfrastructureError(message)
    data = payload.get("data")
    url = (data.get("cdn_url") or data.get("url")) if isinstance(data, dict) else ""
    if not _is_public_video_url(url):
        raise SharedInfrastructureError("file upload succeeded without a public HTTP(S) URL")
    return str(url).strip()


def compile_and_validate_prompt(references: list[Reference], scene: str | None) -> dict[str, Any]:
    brief: dict[str, Any] = {
        "members": [
            {"name": reference.name, "ref": f"[image{index + 1}]"} for index, reference in enumerate(references)
        ]
    }
    if scene is not None:
        brief["scene"] = scene
    normalized = compile_prompt.load_brief(json.dumps(brief, ensure_ascii=False))
    package = compile_prompt.compile_package(normalized)
    violations = validate_prompt.validate_package(package)
    if violations:
        raise SharedInfrastructureError("; ".join(str(violation) for violation in violations))
    return package


def build_executor_payload(
    *,
    package: dict[str, Any],
    image_urls: list[str],
    task_id: str,
) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "generate_type": "multimodal_reference",
        "prompt": package["prompt_text"],
        "image_urls": image_urls,
        "aspect_ratio": package["aspect_ratio"],
        "duration": int(package["duration_seconds"]),
    }


def _failure(
    *,
    task_id: str,
    error_type: str,
    stage: str,
    message: str,
    status: str = "failed",
    submission_state: str = "not_submitted",
) -> dict[str, Any]:
    return {
        "success": False,
        "status": status,
        "task": {
            "id": task_id,
            "status": status,
            "submission_state": submission_state,
        },
        "error_type": error_type,
        "error": {
            "type": error_type,
            "stage": stage,
            "message": message,
        },
        "message": message,
    }


def _classify_executor_failure(message: str) -> tuple[str, str, str, str]:
    lowered = message.casefold()
    if any(term in lowered for term in ("timed out", "timeout")):
        return "timeout_failure", "executor", "timed_out", "indeterminate"
    if any(term in lowered for term in ("cancelled", "canceled")):
        return "cancel_failure", "executor", "cancelled", "indeterminate"
    if any(
        term in lowered
        for term in (
            "prefreeze",
            "wallet",
            "balance",
            "quota",
            "credit",
            "billing",
            "insufficient funds",
            "payment required",
        )
    ):
        return "quota_failure", "billing", "failed", "not_submitted"
    if any(
        term in lowered
        for term in (
            "model_choice",
            "model choice",
            "requires a seedance",
            "unsupported model",
            "model unavailable",
            "model not found",
        )
    ):
        return "model_failure", "model_routing", "failed", "not_submitted"
    if "missing required environment" in lowered or "missing required input fields" in lowered:
        return "runtime_failure", "runtime", "failed", "not_submitted"
    return "provider_failure", "provider", "failed", "submitted"


def _success(
    *,
    task_id: str,
    reference_count: int,
    executor_result: dict[str, Any],
) -> dict[str, Any]:
    url = str(executor_result["url"]).strip()
    task = {
        "id": task_id,
        "status": "succeeded",
        "submission_state": "submitted",
        "executor_task_name": executor_result.get("task_name"),
        "provider_status": executor_result.get("status"),
    }
    return {
        "success": True,
        "status": "succeeded",
        "task": task,
        "video": {"url": url},
        "url": url,
        "video_url": url,
        "reference_count": reference_count,
        "model_choice": executor_result.get("model_choice"),
        "model": executor_result.get("model"),
        "resolution": executor_result.get("resolution"),
    }


def generate_video(
    input_data: Any,
    *,
    runner: CommandRunner | None = None,
    task_id_factory: Callable[[], str] | None = None,
) -> dict[str, Any]:
    runner = runner or SubprocessRunner()
    task_id = (task_id_factory or (lambda: str(uuid4())))()
    stage = "input"
    submission_state = "not_submitted"

    try:
        references, scene = normalize_request(input_data)
        stage = "infrastructure"
        paths = resolve_shared_infrastructure_paths()
        for label, path in paths.items():
            if not path.is_file():
                raise SharedInfrastructureError(f"shared {label} script not found: {path}")

        stage = "upload"
        image_urls = [
            upload_reference(reference, upload_script=paths["upload"], runner=runner) for reference in references
        ]

        stage = "prompt_validation"
        package = compile_and_validate_prompt(references, scene)
        executor_payload = build_executor_payload(
            package=package,
            image_urls=image_urls,
            task_id=task_id,
        )

        stage = "executor"
        submission_state = "indeterminate"
        child_env = os.environ.copy()
        child_env[EXECUTOR_INPUT_ENV_NAME] = json.dumps(
            executor_payload,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        result, executor_result = _run_json_boundary(
            runner,
            [
                sys.executable,
                str(paths["video"]),
                "--input-env",
                EXECUTOR_INPUT_ENV_NAME,
            ],
            env=child_env,
            timeout_seconds=VIDEO_TIMEOUT_SECONDS,
            boundary="video executor",
        )
        if executor_result.get("success") is not True or result.returncode != 0:
            message = str(
                executor_result.get("message")
                or result.stderr.strip()
                or f"video executor exited with status {result.returncode}"
            )
            error_type, error_stage, status, executor_submission_state = _classify_executor_failure(message)
            return _failure(
                task_id=task_id,
                error_type=error_type,
                stage=error_stage,
                message=message,
                status=status,
                submission_state=executor_submission_state,
            )
        if not _is_public_video_url(executor_result.get("url")):
            return _failure(
                task_id=task_id,
                error_type="provider_failure",
                stage="final_video",
                message="video executor reported success without a public final-video URL",
                submission_state="indeterminate",
            )
        return _success(
            task_id=task_id,
            reference_count=len(references),
            executor_result=executor_result,
        )
    except InputContractError as exc:
        return _failure(
            task_id=task_id,
            error_type="invalid_input",
            stage="input",
            message=str(exc),
        )
    except compile_prompt.PromptContractError as exc:
        return _failure(
            task_id=task_id,
            error_type="prompt_validation_failure",
            stage="prompt_validation",
            message=str(exc),
        )
    except subprocess.TimeoutExpired as exc:
        return _failure(
            task_id=task_id,
            error_type="timeout_failure",
            stage=stage,
            message=f"{stage} timed out after {exc.timeout} seconds",
            status="timed_out",
            submission_state=submission_state,
        )
    except (GenerationCancelled, KeyboardInterrupt) as exc:
        message = str(exc).strip() or f"{stage} cancelled"
        return _failure(
            task_id=task_id,
            error_type="cancel_failure",
            stage=stage,
            message=message,
            status="cancelled",
            submission_state=submission_state,
        )
    except BoundaryProtocolError as exc:
        error_type = "upload_failure" if stage == "upload" else "executor_protocol_failure"
        return _failure(
            task_id=task_id,
            error_type=error_type,
            stage=stage,
            message=str(exc),
            submission_state=submission_state,
        )
    except SharedInfrastructureError as exc:
        if stage == "upload":
            error_type = "upload_failure"
        elif stage == "prompt_validation":
            error_type = "prompt_validation_failure"
        else:
            error_type = "infrastructure_failure"
        return _failure(
            task_id=task_id,
            error_type=error_type,
            stage=stage,
            message=str(exc),
            submission_state=submission_state,
        )
    except Exception as exc:  # pragma: no cover - fail closed at the CLI boundary
        return _failure(
            task_id=task_id,
            error_type="internal_failure",
            stage=stage,
            message=str(exc),
            submission_state=submission_state,
        )


def _load_cli_input(argv: list[str] | None = None) -> Any:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input-file")
    source.add_argument("--input-json")
    source.add_argument("--input-env")
    args = parser.parse_args(argv)
    if args.input_file:
        raw = Path(args.input_file).read_text(encoding="utf-8-sig")
    elif args.input_env:
        raw = os.environ.get(args.input_env)
        if raw is None:
            raise InputContractError(f"--input-env variable not found: {args.input_env}")
    else:
        raw = args.input_json
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise InputContractError(f"input is not valid JSON: {exc}") from exc


def _handle_termination(signum: int, _frame: Any) -> None:
    raise GenerationCancelled(f"generation cancelled by {signal.Signals(signum).name}")


def main(argv: list[str] | None = None) -> int:
    previous_sigterm = signal.signal(signal.SIGTERM, _handle_termination)
    try:
        try:
            input_data = _load_cli_input(argv)
        except (InputContractError, OSError) as exc:
            output = _failure(
                task_id=str(uuid4()),
                error_type="invalid_input",
                stage="input",
                message=str(exc),
            )
        else:
            output = generate_video(input_data)
    finally:
        signal.signal(signal.SIGTERM, previous_sigterm)
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if output.get("success") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
