#!/usr/bin/env python3
"""Manifest helpers for the greybox-cg-v2v two-stage review gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "greybox-cg-v2v.revision_manifest.v1"
SKILL_NAME = "greybox-cg-v2v"
TRUSTED_CANVAS_ENV_NAMES = ("canvas_id", "CANVAS_ID", "SEELE_CANVAS_ID")
TRUSTED_SESSION_ENV_NAMES = (
    "trace_id",
    "X_SEELE_CANVAS_TRACE_ID",
    "SEELE_CANVAS_TRACE_ID",
    "session_canvas_id",
)

STATES = {
    "drafting_greybox",
    "greybox_recorded_local",
    "greybox_ready_for_review",
    "revision_requested",
    "greybox_approved",
    "rendering_final",
    "final_ready",
    "failed",
}

GREYBOX_THREEJS_PREVIEW = "greybox_threejs_preview"
GREYBOX_VIDEO = "greybox_video"
FINAL_VIDEO = "final_video"

REQUIRED_ARTIFACT_TYPES = {GREYBOX_THREEJS_PREVIEW, GREYBOX_VIDEO}
AMBIGUOUS_APPROVAL_WORDS = {
    "还行吧",
    "可以吧",
    "差不多",
    "再看看",
    "maybe",
    "looks ok",
    "ok-ish",
    "probably",
    "seems fine",
}
NEGATIVE_APPROVAL_WORDS = {
    "不同意",
    "不批准",
    "不确认",
    "不要确认",
    "别确认",
    "先不确认",
    "不要生成",
    "别生成",
    "不生成",
    "不要开始",
    "先别",
    "no",
    "nope",
    "not approved",
    "do not approve",
    "don't approve",
    "dont approve",
    "not confirmed",
    "do not confirm",
    "don't confirm",
    "dont confirm",
    "do not generate",
    "don't generate",
    "dont generate",
    "reject",
    "rejected",
    "revise",
    "change it",
}
EXACT_APPROVAL_PHRASES = {
    "确认",
    "批准",
    "同意",
    "确认生成成片",
    "确认生成最终视频",
    "确认当前revision生成最终视频",
    "确认当前revision生成成片",
    "开始生成成片",
    "开始生成最终视频",
    "生成最终视频",
    "就用这个",
    "用这个生成最终视频",
    "approve",
    "approved",
    "confirm",
    "confirmed",
    "proceed",
    "use this",
    "use this revision",
    "start final render",
    "generate final video",
    "confirm final render",
    "approve final render",
}


class ManifestError(ValueError):
    """Raised when a manifest violates the two-stage contract."""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: str | os.PathLike[str]) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def stable_revision_id(source_prompt: str, parent_revision_id: str | None = None, request_text: str = "") -> str:
    seed = "\n".join([source_prompt, parent_revision_id or "", request_text])
    return "gbrev_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def normalize_path(path: str | None) -> str | None:
    if not path:
        return None
    return str(Path(path).expanduser().resolve())


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", value) is not None


def _is_public_https_url(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("https://") and "://localhost" not in value and "://127." not in value


def _is_uuid(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        return str(uuid.UUID(value)) == value.lower()
    except (ValueError, AttributeError):
        return False


def _session_canvas_uuid(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    first = value.split("|", 1)[0].strip()
    return first if "|" in value and _is_uuid(first) else None


def resolve_runtime_identity(
    supplied_canvas_id: str | None = None,
    supplied_session_canvas_id: str | None = None,
) -> tuple[str, str]:
    """Resolve Canvas identity from runtime env; CLI values are compatibility assertions only."""

    canvas_values = {os.environ[name].strip() for name in TRUSTED_CANVAS_ENV_NAMES if os.environ.get(name, "").strip()}
    session_values = {
        os.environ[name].strip() for name in TRUSTED_SESSION_ENV_NAMES if os.environ.get(name, "").strip()
    }
    if len(canvas_values) != 1:
        detail = "missing" if not canvas_values else "conflicting"
        raise ManifestError(f"trusted runtime canvas_id is {detail}")
    if len(session_values) != 1:
        detail = "missing" if not session_values else "conflicting"
        raise ManifestError(f"trusted runtime session_canvas_id is {detail}")
    canvas_id = canvas_values.pop()
    session_canvas_id = session_values.pop()
    if not _is_uuid(canvas_id):
        raise ManifestError("trusted runtime canvas_id must be a canonical UUID")
    if _session_canvas_uuid(session_canvas_id) != canvas_id:
        raise ManifestError("trusted runtime session_canvas_id must be bound to runtime canvas_id")
    if supplied_canvas_id and supplied_canvas_id != canvas_id:
        raise ManifestError("--canvas-id does not match trusted runtime canvas_id")
    if supplied_session_canvas_id and supplied_session_canvas_id != session_canvas_id:
        raise ManifestError("--session-canvas-id does not match trusted runtime session_canvas_id")
    return canvas_id, session_canvas_id


def _canonical_parent_revision_id(manifest: dict[str, Any]) -> str | None:
    canonical = manifest.get("parent_greybox_revision_id")
    legacy = manifest.get("parent_revision_id")
    if canonical is not None and legacy is not None and canonical != legacy:
        raise ManifestError("parent revision aliases disagree")
    return canonical if canonical is not None else legacy


def _artifact_by_type(manifest: dict[str, Any], artifact_type: str) -> dict[str, Any] | None:
    for artifact in manifest.get("artifacts", []):
        if artifact.get("artifact_type") == artifact_type:
            return artifact
    return None


def create_ready_manifest(
    *,
    source_prompt: str,
    threejs_path: str,
    greybox_video_path: str,
    greybox_video_url: str | None = None,
    threejs_urls: list[str] | None = None,
    greybox_revision_id: str | None = None,
    parent_revision_id: str | None = None,
    canvas_id: str | None = None,
    session_canvas_id: str | None = None,
    game_id: str | None = None,
    turn_id: str | None = None,
    duration_ms: int | None = None,
    fps: int | None = None,
    width: int | None = None,
    height: int | None = None,
    v2v_prompt: str | None = None,
    model_choice: str = "seedance2_1080p",
    aspect_ratio: str = "16:9",
) -> dict[str, Any]:
    """Create a review-ready manifest. This is still pre-V2V and approval is pending."""

    revision_id = greybox_revision_id or stable_revision_id(source_prompt, parent_revision_id)
    video_path = normalize_path(greybox_video_path)
    preview_path = normalize_path(threejs_path)
    if not video_path:
        raise ManifestError("greybox_video_path is required")
    if not preview_path:
        raise ManifestError("threejs_path is required")

    video_hash = sha256_file(video_path) if Path(video_path).exists() else None
    source_prompt_hash = sha256_text(source_prompt)
    created_at = utc_now()
    public_ready = bool(
        canvas_id
        and session_canvas_id
        and _is_public_https_url(greybox_video_url)
        and threejs_urls
        and all(_is_public_https_url(url) for url in threejs_urls)
        and _is_sha256(video_hash)
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "skill_name": SKILL_NAME,
        "state": "greybox_ready_for_review" if public_ready else "greybox_recorded_local",
        "greybox_revision_id": revision_id,
        "latest_greybox_revision_id": revision_id,
        "parent_greybox_revision_id": parent_revision_id,
        "parent_revision_id": parent_revision_id,
        "revision_lineage": [revision_id],
        "source_prompt_hash": source_prompt_hash,
        "canvas_id": canvas_id,
        "session_canvas_id": session_canvas_id,
        "game_id": game_id,
        "turn_id": turn_id,
        "created_at": created_at,
        "updated_at": created_at,
        "idempotency_key": f"greybox:review:{revision_id}",
        "artifacts": [
            {
                "artifact_type": GREYBOX_THREEJS_PREVIEW,
                "role": "review_preview",
                "name": f"Greybox Three.js Preview {revision_id}",
                "engine": "threejs",
                "entrypoint": "index.html",
                "path": preview_path,
                "urls": threejs_urls or [],
                "metadata": {
                    "revision_id": revision_id,
                    "parent_revision_id": parent_revision_id,
                    "engine": "threejs",
                    "entrypoint": "index.html",
                    "urls": threejs_urls or [],
                    "requires_host_artifact_sync": True,
                },
            },
            {
                "artifact_type": GREYBOX_VIDEO,
                "role": "v2v_input_candidate",
                "name": f"Greybox Preview Video {revision_id}",
                "mime_type": "video/mp4",
                "path": video_path,
                "url": greybox_video_url,
                "sha256": video_hash,
                "duration_ms": duration_ms,
                "fps": fps,
                "width": width,
                "height": height,
                "metadata": {
                    "revision_id": revision_id,
                    "parent_greybox_revision_id": parent_revision_id,
                    "parent_revision_id": parent_revision_id,
                    "role": "v2v_input_candidate",
                    "url": greybox_video_url,
                    "duration_ms": duration_ms,
                    "fps": fps,
                },
            },
        ],
        "approval": {
            "required": True,
            "status": "pending",
            "approved_revision_id": None,
            "approved_greybox_video_path": None,
            "approved_greybox_video_url": None,
            "approved_greybox_video_sha256": None,
            "approved_at": None,
            "approved_by": None,
            "approval_idempotency_key": None,
            "approve_action": "greybox.approve",
            "revise_action": "greybox.revise",
            "explicit_confirmation_required": True,
        },
        "final_render": {
            "allowed": False,
            "state": None,
            "blocked_until_state": "greybox_approved",
            "source_greybox_revision_id": None,
            "v2v_input_video_path": None,
            "v2v_input_video_url": None,
            "v2v_input_video_sha256": None,
            "final_artifact_type": FINAL_VIDEO,
            "idempotency_key": None,
            "job_id": None,
            "started_at": None,
            "completed_at": None,
            "output": None,
            "request": {
                "prompt": v2v_prompt or source_prompt,
                "model_choice": model_choice,
                "generate_type": "multimodal_reference",
                "aspect_ratio": aspect_ratio,
                "duration": max(1, round(duration_ms / 1000)) if duration_ms else 8,
                "camera_fixed": False,
            },
        },
    }


def validate_manifest(manifest: dict[str, Any], *, require_files: bool = True) -> None:
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ManifestError("unsupported schema_version")
    if manifest.get("skill_name") != SKILL_NAME:
        raise ManifestError("skill_name must be greybox-cg-v2v")
    state = manifest.get("state")
    if state not in STATES:
        raise ManifestError(f"invalid state: {state}")
    revision_id = manifest.get("greybox_revision_id")
    if not isinstance(revision_id, str) or not revision_id:
        raise ManifestError("greybox_revision_id is required")
    if not re.match(r"^[A-Za-z0-9_.:-]+$", revision_id):
        raise ManifestError("greybox_revision_id contains unsafe characters")
    if not _is_sha256(manifest.get("source_prompt_hash")):
        raise ManifestError("source_prompt_hash must be a complete sha256:<64 lowercase hex>")
    canvas_id = manifest.get("canvas_id")
    if not _is_uuid(canvas_id):
        raise ManifestError("canvas_id must be a canonical UUID")
    session_canvas_id = manifest.get("session_canvas_id")
    session_canvas_uuid = _session_canvas_uuid(session_canvas_id)
    if not session_canvas_uuid:
        raise ManifestError("session_canvas_id must be a pipe-delimited runtime trace beginning with a canvas UUID")
    if session_canvas_uuid.lower() != canvas_id.lower():
        raise ManifestError("session_canvas_id must be bound to canvas_id")
    game_id = manifest.get("game_id")
    if game_id is not None and (not isinstance(game_id, str) or not game_id.strip()):
        raise ManifestError("game_id must be a non-empty string when present")
    if isinstance(game_id, str) and game_id.lower() in {canvas_id.lower(), session_canvas_id.lower()}:
        raise ManifestError("game_id must be distinct from canvas_id and session_canvas_id")
    parent_revision_id = _canonical_parent_revision_id(manifest)
    if manifest.get("latest_greybox_revision_id", revision_id) != revision_id:
        raise ManifestError("manifest is not the current latest revision")
    lineage = manifest.get("revision_lineage")
    if not isinstance(lineage, list) or not lineage or lineage[-1] != revision_id:
        raise ManifestError("revision_lineage must end at the current revision")
    if parent_revision_id is not None and (len(lineage) < 2 or lineage[-2] != parent_revision_id):
        raise ManifestError("parent revision must be the immediately previous current-latest revision")

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise ManifestError("artifacts must be a list")
    artifact_types = [artifact.get("artifact_type") for artifact in artifacts]
    if not REQUIRED_ARTIFACT_TYPES.issubset(set(artifact_types)):
        raise ManifestError("manifest must include Three.js preview and greybox video artifacts")
    if len(artifact_types) != len(set(artifact_types)):
        raise ManifestError("artifact_type values must be unique")
    if FINAL_VIDEO in artifact_types:
        final_artifact = _artifact_by_type(manifest, FINAL_VIDEO)
        if final_artifact and final_artifact.get("role") == "v2v_input_candidate":
            raise ManifestError("final video artifact cannot use greybox candidate role")

    preview = _artifact_by_type(manifest, GREYBOX_THREEJS_PREVIEW) or {}
    if preview.get("role") != "review_preview":
        raise ManifestError("Three.js preview role must be review_preview")
    if preview.get("engine") != "threejs":
        raise ManifestError("Three.js preview artifact must set engine=threejs")
    if preview.get("entrypoint") != "index.html":
        raise ManifestError("Three.js preview artifact must set entrypoint=index.html")
    preview_meta = preview.get("metadata") or {}
    if preview_meta.get("revision_id") != revision_id:
        raise ManifestError("Three.js preview revision metadata mismatch")
    if preview_meta.get("requires_host_artifact_sync") is not True:
        raise ManifestError("Three.js preview must declare requires_host_artifact_sync=true")
    if preview_meta.get("engine") != "threejs" or preview_meta.get("entrypoint") != "index.html":
        raise ManifestError("Three.js metadata must include engine=threejs and entrypoint=index.html")
    if preview_meta.get("urls") != preview.get("urls"):
        raise ManifestError("Three.js metadata.urls must match artifact urls")
    if state != "greybox_recorded_local":
        urls = preview.get("urls")
        if not isinstance(urls, list) or not urls or not all(_is_public_https_url(url) for url in urls):
            raise ManifestError("ready Three.js preview requires public HTTPS urls")

    video = _artifact_by_type(manifest, GREYBOX_VIDEO) or {}
    if video.get("role") != "v2v_input_candidate":
        raise ManifestError("greybox video role must be v2v_input_candidate")
    if video.get("name") == preview.get("name"):
        raise ManifestError("Three.js preview and greybox video must have distinct names")
    video_meta = video.get("metadata") or {}
    if video_meta.get("revision_id") != revision_id:
        raise ManifestError("greybox video revision metadata mismatch")
    if not _is_sha256(video.get("sha256")):
        raise ManifestError("greybox video requires a complete sha256:<64 lowercase hex>")
    if video_meta.get("role") != "v2v_input_candidate" or video_meta.get("url") != video.get("url"):
        raise ManifestError("greybox video metadata must bind role and public URL")
    if state != "greybox_recorded_local" and not _is_public_https_url(video.get("url")):
        raise ManifestError("ready greybox video requires a public HTTPS url")
    if require_files:
        video_path = video.get("path")
        if not video_path or not Path(video_path).exists():
            raise ManifestError("greybox video path is missing or does not exist")
        expected_hash = video.get("sha256")
        actual_hash = sha256_file(video_path)
        if expected_hash != actual_hash:
            raise ManifestError("greybox video sha256 does not match path contents")

    approval = manifest.get("approval") or {}
    if approval.get("required") is not True:
        raise ManifestError("approval.required must be true")
    if approval.get("status") not in {"pending", "approved", "rejected"}:
        raise ManifestError("approval.status must be pending, approved, or rejected")
    final_render = manifest.get("final_render") or {}
    if final_render.get("final_artifact_type") != FINAL_VIDEO:
        raise ManifestError("final_render.final_artifact_type must be final_video")
    request = final_render.get("request") or {}
    if request.get("generate_type") != "multimodal_reference" or not str(request.get("prompt") or "").strip():
        raise ManifestError("final_render.request must define a multimodal_reference prompt")


def approve_manifest(
    manifest: dict[str, Any],
    *,
    approved_revision_id: str,
    approved_by: str = "user",
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    validate_manifest(manifest)
    revision_id = manifest["greybox_revision_id"]
    if manifest.get("state") != "greybox_ready_for_review":
        raise ManifestError("only a fully published greybox_ready_for_review manifest can be approved")
    if approved_revision_id != revision_id:
        raise ManifestError("approved revision does not match manifest revision")

    out = deepcopy(manifest)
    approval = out["approval"]
    video = _artifact_by_type(out, GREYBOX_VIDEO)
    assert video is not None
    video_path = video.get("path")
    video_hash = sha256_file(video_path)
    if video_hash != video.get("sha256"):
        raise ManifestError("greybox video sha256 changed before approval")

    stable_key = idempotency_key or f"greybox:approve:{revision_id}:{approved_by}"
    if approval.get("status") == "approved":
        if approval.get("approved_revision_id") != revision_id:
            raise ManifestError("manifest approval points at another revision")
        if approval.get("approved_greybox_video_path") != video_path:
            raise ManifestError("approved greybox video path mismatch")
        if approval.get("approved_greybox_video_sha256") != video_hash:
            raise ManifestError("approved greybox video sha256 mismatch")
        return out

    now = utc_now()
    out["state"] = "greybox_approved"
    out["updated_at"] = now
    approval.update(
        {
            "status": "approved",
            "approved_revision_id": revision_id,
            "approved_greybox_video_path": video_path,
            "approved_greybox_video_url": video.get("url"),
            "approved_greybox_video_sha256": video_hash,
            "approved_at": now,
            "approved_by": approved_by,
            "approval_idempotency_key": stable_key,
        }
    )
    out["final_render"].update(
        {
            "allowed": True,
            "blocked_until_state": None,
            "source_greybox_revision_id": revision_id,
            "v2v_input_video_path": video_path,
            "v2v_input_video_url": video.get("url"),
            "v2v_input_video_sha256": video_hash,
            "idempotency_key": f"v2v:final:{revision_id}:{video_hash}",
        }
    )
    return out


def mark_final_started(manifest: dict[str, Any], *, job_id: str) -> dict[str, Any]:
    out = deepcopy(manifest)
    if out.get("state") == "final_ready":
        return out
    out["state"] = "rendering_final"
    out["updated_at"] = utc_now()
    out["final_render"]["state"] = "rendering_final"
    out["final_render"]["job_id"] = job_id
    out["final_render"]["started_at"] = out["final_render"].get("started_at") or utc_now()
    return out


def mark_final_failed(
    manifest: dict[str, Any],
    *,
    error_message: str,
    failed_stage: str = "v2v",
    error_code: str = "downstream_failure",
    retryable: bool = False,
) -> dict[str, Any]:
    out = deepcopy(manifest)
    sanitized = " ".join((error_message or "downstream V2V command failed").replace("\x00", "").split())
    out["state"] = "failed"
    out["updated_at"] = utc_now()
    out["failed_stage"] = failed_stage
    out["error_code"] = error_code
    out["error_message_sanitized"] = sanitized[:1000]
    out["retryable"] = retryable
    out["last_good_revision_id"] = out.get("greybox_revision_id")
    out.setdefault("final_render", {})
    out["final_render"]["state"] = "failed"
    out["final_render"]["failed_stage"] = failed_stage
    out["final_render"]["error_code"] = error_code
    out["final_render"]["error_message_sanitized"] = sanitized[:1000]
    out["final_render"]["retryable"] = retryable
    out["final_render"]["last_good_revision_id"] = out.get("greybox_revision_id")
    out["final_render"]["requires_explicit_retry_or_reconciliation"] = True
    return out


def mark_final_ready(manifest: dict[str, Any], *, final_video_url: str, final_video_path: str | None = None) -> dict[str, Any]:
    out = deepcopy(manifest)
    revision_id = out["greybox_revision_id"]
    final_artifact = {
        "artifact_type": FINAL_VIDEO,
        "role": "final_output",
        "name": f"Final Cinematic Video from Greybox {revision_id}",
        "mime_type": "video/mp4",
        "url": final_video_url,
        "path": normalize_path(final_video_path),
        "metadata": {
            "source_artifact_type": GREYBOX_VIDEO,
            "source_revision_id": revision_id,
        },
    }
    out["artifacts"] = [a for a in out.get("artifacts", []) if a.get("artifact_type") != FINAL_VIDEO] + [final_artifact]
    out["state"] = "final_ready"
    out["updated_at"] = utc_now()
    for field in ("failed_stage", "error_code", "error_message_sanitized", "retryable", "last_good_revision_id"):
        out.pop(field, None)
    out["final_render"]["state"] = "final_ready"
    out["final_render"]["completed_at"] = utc_now()
    out["final_render"]["output"] = {"url": final_video_url, "path": normalize_path(final_video_path)}
    for field in (
        "failed_stage",
        "error_code",
        "error_message_sanitized",
        "retryable",
        "last_good_revision_id",
        "requires_explicit_retry_or_reconciliation",
    ):
        out["final_render"].pop(field, None)
    return out


def create_revision_requested_manifest(
    base_manifest: dict[str, Any],
    *,
    request_text: str,
    new_source_prompt: str,
    threejs_path: str,
    greybox_video_path: str,
    greybox_video_url: str | None = None,
    threejs_urls: list[str] | None = None,
    base_manifest_path: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    validate_manifest(base_manifest)
    if base_manifest.get("latest_greybox_revision_id", base_manifest.get("greybox_revision_id")) != base_manifest.get("greybox_revision_id"):
        raise ManifestError("revision parent must be the current latest revision")
    if not request_text or not request_text.strip():
        raise ManifestError("revision request text is required")
    parent_revision_id = base_manifest["greybox_revision_id"]
    revision_id = stable_revision_id(new_source_prompt, parent_revision_id, request_text)
    base_lineage = base_manifest.get("revision_lineage") or [parent_revision_id]
    out = create_ready_manifest(
        source_prompt=new_source_prompt,
        threejs_path=threejs_path,
        greybox_video_path=greybox_video_path,
        greybox_video_url=greybox_video_url,
        threejs_urls=threejs_urls,
        greybox_revision_id=revision_id,
        parent_revision_id=parent_revision_id,
        canvas_id=base_manifest.get("canvas_id"),
        session_canvas_id=base_manifest.get("session_canvas_id"),
        game_id=base_manifest.get("game_id"),
        v2v_prompt=(base_manifest.get("final_render") or {}).get("request", {}).get("prompt") or new_source_prompt,
        model_choice=(base_manifest.get("final_render") or {}).get("request", {}).get("model_choice", "seedance2_1080p"),
        aspect_ratio=(base_manifest.get("final_render") or {}).get("request", {}).get("aspect_ratio", "16:9"),
    )
    out["revision_request"] = {
        "state": "revision_requested",
        "base_greybox_revision_id": parent_revision_id,
        "request_text_hash": sha256_text(request_text),
        "requested_at": utc_now(),
    }
    out["revision_lineage"] = [*base_lineage, revision_id]
    # Invalidate an already-approved parent as soon as its child exists. Persist atomically when
    # the caller supplies the canonical parent path; otherwise the caller must save the mutated object.
    base_manifest["latest_greybox_revision_id"] = revision_id
    base_manifest["state"] = "revision_requested"
    base_manifest.setdefault("approval", {})["status"] = "rejected"
    base_manifest.setdefault("final_render", {})["allowed"] = False
    base_manifest["final_render"]["blocked_until_state"] = "greybox_approved"
    base_manifest["updated_at"] = utc_now()
    if base_manifest_path is not None:
        save_manifest(base_manifest, base_manifest_path)
    return out


def _normalize_approval_text(text: str) -> str:
    normalized = text.strip().lower()
    normalized = re.sub(r"[`*\"'“”‘’。，、！？!?,.;:：；（）()\[\]{}<>《》]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    normalized = normalized.replace("revision ", "revision")
    return normalized


def is_explicit_approval_text(text: str, *, current_revision_id: str | None = None) -> bool:
    normalized = _normalize_approval_text(text)
    if not normalized:
        return False
    if any(word in normalized for word in NEGATIVE_APPROVAL_WORDS):
        return False
    if any(word in normalized for word in AMBIGUOUS_APPROVAL_WORDS):
        return False

    normalized_compact = normalized.replace(" ", "")
    if current_revision_id:
        current = current_revision_id.lower()
        revision_mentions = re.findall(r"\bgbrev_[a-z0-9_.:-]+\b", normalized)
        if revision_mentions and current not in revision_mentions:
            return False
        anchored_with_revision = {
            f"确认{current}生成最终视频",
            f"确认{current}生成成片",
            f"批准{current}",
            f"同意{current}",
            f"approve {current}",
            f"approved {current}",
            f"confirm {current}",
            f"use {current}",
            f"use revision{current}",
        }
        if normalized in anchored_with_revision or normalized_compact in {p.replace(" ", "") for p in anchored_with_revision}:
            return True

    if normalized in EXACT_APPROVAL_PHRASES or normalized_compact in {p.replace(" ", "") for p in EXACT_APPROVAL_PHRASES}:
        return True

    anchored_patterns = [
        r"^confirm revision[a-z0-9_.:-]+$",
        r"^approve revision[a-z0-9_.:-]+$",
        r"^approved revision[a-z0-9_.:-]+$",
        r"^use revision[a-z0-9_.:-]+$",
        r"^确认gbrev_[a-z0-9_.:-]+生成最终视频$",
        r"^批准gbrev_[a-z0-9_.:-]+$",
    ]
    return any(re.match(pattern, normalized_compact if "gbrev_" in pattern else normalized) for pattern in anchored_patterns)


def load_manifest(path: str | os.PathLike[str]) -> dict[str, Any]:
    manifest = json.loads(Path(path).read_text(encoding="utf-8"))
    # Read compatibility for v1 manifests; all subsequent writes emit both names.
    if "parent_greybox_revision_id" not in manifest and "parent_revision_id" in manifest:
        manifest["parent_greybox_revision_id"] = manifest.get("parent_revision_id")
    if "parent_revision_id" not in manifest and "parent_greybox_revision_id" in manifest:
        manifest["parent_revision_id"] = manifest.get("parent_greybox_revision_id")
    manifest.setdefault("latest_greybox_revision_id", manifest.get("greybox_revision_id"))
    return manifest


def save_manifest(
    manifest: dict[str, Any],
    path: str | os.PathLike[str],
    *,
    replace_attempts: int = 5,
    replace_backoff_seconds: float = 0.05,
) -> None:
    """Atomically persist a manifest, tolerating bounded Windows file-lock races."""

    if replace_attempts < 1 or replace_backoff_seconds < 0:
        raise ManifestError("manifest replace retry settings are invalid")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = deepcopy(manifest)
    parent = _canonical_parent_revision_id(payload)
    payload["parent_greybox_revision_id"] = parent
    payload["parent_revision_id"] = parent
    temp = target.with_name(f".{target.name}.{os.getpid()}.{time.time_ns()}.tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    try:
        for attempt in range(1, replace_attempts + 1):
            try:
                os.replace(temp, target)
                return
            except PermissionError as exc:
                if attempt == replace_attempts:
                    raise ManifestError(
                        f"atomic manifest replace remained locked after {replace_attempts} attempts; original preserved: {target}"
                    ) from exc
                time.sleep(replace_backoff_seconds * (2 ** (attempt - 1)))
            except OSError as exc:
                raise ManifestError(f"atomic manifest replace failed; original preserved: {target}: {exc}") from exc
    finally:
        temp.unlink(missing_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="Create, validate, or approve greybox-cg-v2v revision manifests.")
    sub = ap.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create-ready")
    create.add_argument("--source-prompt", required=True)
    create.add_argument("--threejs-path", required=True)
    create.add_argument("--greybox-video-path", required=True)
    create.add_argument("--greybox-video-url")
    create.add_argument("--threejs-url", action="append", default=[])
    create.add_argument("--revision-id")
    create.add_argument("--parent-revision-id")
    create.add_argument("--canvas-id", help="Legacy assertion only; Canvas identity comes from runtime env.")
    create.add_argument(
        "--session-canvas-id", help="Legacy assertion only; session identity comes from runtime env."
    )
    create.add_argument("--game-id", help="Optional business/game identifier; never used as Canvas identity.")
    create.add_argument("--duration-ms", type=int)
    create.add_argument("--fps", type=int)
    create.add_argument("--width", type=int)
    create.add_argument("--height", type=int)
    create.add_argument("--out", required=True)

    validate = sub.add_parser("validate")
    validate.add_argument("--manifest", required=True)
    validate.add_argument("--no-require-files", action="store_true")

    approve = sub.add_parser("approve")
    approve.add_argument("--manifest", required=True)
    approve.add_argument("--revision-id", required=True)
    approve.add_argument("--approved-by", default="user")
    approve.add_argument("--idempotency-key")
    approve.add_argument("--out")

    args = ap.parse_args()
    try:
        if args.command == "create-ready":
            canvas_id, session_canvas_id = resolve_runtime_identity(
                args.canvas_id, args.session_canvas_id
            )
            manifest = create_ready_manifest(
                source_prompt=args.source_prompt,
                threejs_path=args.threejs_path,
                greybox_video_path=args.greybox_video_path,
                greybox_video_url=args.greybox_video_url,
                threejs_urls=args.threejs_url,
                greybox_revision_id=args.revision_id,
                parent_revision_id=args.parent_revision_id,
                canvas_id=canvas_id,
                session_canvas_id=session_canvas_id,
                game_id=args.game_id,
                duration_ms=args.duration_ms,
                fps=args.fps,
                width=args.width,
                height=args.height,
            )
            validate_manifest(manifest)
            save_manifest(manifest, args.out)
            print(json.dumps({"success": True, "manifest": str(Path(args.out).resolve()), "greybox_revision_id": manifest["greybox_revision_id"]}))
            return 0
        if args.command == "validate":
            validate_manifest(load_manifest(args.manifest), require_files=not args.no_require_files)
            print(json.dumps({"success": True}))
            return 0
        if args.command == "approve":
            manifest = approve_manifest(
                load_manifest(args.manifest),
                approved_revision_id=args.revision_id,
                approved_by=args.approved_by,
                idempotency_key=args.idempotency_key,
            )
            save_manifest(manifest, args.out or args.manifest)
            print(json.dumps({"success": True, "greybox_revision_id": manifest["greybox_revision_id"], "state": manifest["state"]}))
            return 0
    except ManifestError as exc:
        print(json.dumps({"success": False, "message": str(exc)}), file=sys.stderr)
        return 2
    return 1


if __name__ == "__main__":
    sys.exit(main())
