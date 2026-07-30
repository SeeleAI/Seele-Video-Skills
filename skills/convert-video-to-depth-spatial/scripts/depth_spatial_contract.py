#!/usr/bin/env python3
"""Fail-closed Video Depth Anything-Small contract and HTTP executor."""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Mapping, NamedTuple
from urllib.parse import urlencode
from uuid import uuid4

MODEL_ID = "depth-anything/Video-Depth-Anything-Small"
MODEL_LICENSE = "Apache-2.0"
RAW_DEPTH_FORMAT = "npz"
ARTIFACT_NAMES = (
    "depth.mp4",
    "depth.npz",
    "manifest.json",
    "metrics.json",
    "receipt.json",
    "execution.log",
)
DIRECT_ENDPOINT_PATH = "/tasks/video_depth/execute"
GATEWAY_PATH = "/gateway/mq?" + urlencode(
    {
        "abs_cuda_proxy_service_name": "imagegen",
        "abs_cuda_proxy_func_name": "video_depth",
    }
)
DEFAULT_TIMEOUT_SECONDS = 1250
MAX_TIMEOUT_SECONDS = 1800
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
GATEWAY_SUBMIT_TIMEOUT_SECONDS = 540
RECOVERY_POLL_TIMEOUT_SECONDS = 480
RECOVERY_POLL_INTERVAL_SECONDS = 10
TASK_RESULT_REQUEST_TIMEOUT_SECONDS = 20
TASK_RESULT_PATH = "/syn-gateway/task"
DURABLE_RESULT_BASE_URL = os.environ.get("VIDEO_DEPTH_RESULT_BASE_URL", "").rstrip("/")
TASK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")

# This is the same approved TEST Agent gateway discovery convention used by
# ai-model-calling. It is not a public runtime endpoint.
PUBLIC_APP_TO_INTERNAL_GATEWAY_BASE_URL: dict[str, str] = {}


class ContractError(RuntimeError):
    """The request, environment, transport, or runtime violated the contract."""


class RuntimeRequestTimeout(ContractError):
    """The gateway may still finish a submitted task after the caller stops waiting."""


class Transport(NamedTuple):
    kind: str
    url: str
    headers: dict[str, str]


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Block redirects so configured destinations cannot pivot to another host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


def _clean_string(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _first_present(data: Mapping[str, Any], names: tuple[str, ...]) -> Any:
    for name in names:
        if name in data and data[name] not in (None, "", []):
            return data[name]
    return None


def _attachment_urls(data: Mapping[str, Any]) -> list[str]:
    urls: list[str] = []
    for name in ("fileUrlList", "file_url_list", "fileList", "file_list", "attachments"):
        raw = data.get(name)
        if raw in (None, "", []):
            continue
        if not isinstance(raw, list) or any(not _clean_string(item) for item in raw):
            raise ContractError("attachment URL list must contain only non-empty strings")
        for item in raw:
            url = _clean_string(item)
            if url not in urls:
                urls.append(url)
    return urls


def _validate_media_url(value: Any, *, field_name: str) -> str:
    url = _clean_string(value)
    if not url:
        raise ContractError(f"{field_name} is required")
    try:
        parsed = urllib.parse.urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise ContractError(f"{field_name} is not a valid URL") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ContractError(
            f"{field_name} must be a public HTTP(S) URL; upload local files with file-upload-to-cdn first"
        )
    if parsed.username is not None or parsed.password is not None:
        raise ContractError(f"{field_name} URL credentials are forbidden")
    if port not in (None, 80, 443):
        raise ContractError(f"{field_name} URL port must be 80 or 443")
    if parsed.fragment:
        raise ContractError(f"{field_name} URL fragments are forbidden")
    host = parsed.hostname.lower()
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise ContractError(f"{field_name} URL must not target a private or special IP")
    return url


def normalize_request(data: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(data, Mapping):
        raise ContractError("request must be a JSON object")

    explicit = _first_present(data, ("input_video", "video_url"))
    attachments = _attachment_urls(data)
    if explicit is None:
        if len(attachments) != 1:
            raise ContractError("provide exactly one input_video URL or one attached video URL")
        explicit = attachments[0]
    elif attachments != [] and attachments != [_clean_string(explicit)]:
        raise ContractError("input_video conflicts with the attached video URL")

    input_video = _validate_media_url(explicit, field_name="input_video")
    mode = data.get("mode", "depth")
    model = data.get("model", MODEL_ID)
    raw_depth_format = data.get("raw_depth_format", RAW_DEPTH_FORMAT)
    preserve_audio = data.get("preserve_audio", True)

    if mode != "depth":
        raise ContractError("mode must be: depth")
    if model != MODEL_ID:
        raise ContractError(f"model must be {MODEL_ID}; fallback/substitution is forbidden")
    if raw_depth_format != RAW_DEPTH_FORMAT:
        raise ContractError("raw_depth_format must be: npz")
    if preserve_audio is not True:
        raise ContractError("preserve_audio must be true")

    task_id = _clean_string(data.get("task_id")) or f"video-depth-{uuid4().hex}"
    if not TASK_ID_RE.fullmatch(task_id):
        raise ContractError("task_id contains forbidden characters")
    return {
        "input_video": input_video,
        "task_id": task_id,
        "mode": "depth",
        "model": MODEL_ID,
        "model_license": MODEL_LICENSE,
        "raw_depth_format": RAW_DEPTH_FORMAT,
        "preserve_audio": True,
        "pipeline": ["validate_input", "http_runtime", "depth_artifacts", "validate"],
    }


def runtime_payload(request: Mapping[str, Any]) -> dict[str, Any]:
    normalized = normalize_request(request)
    return {
        "input_video": normalized["input_video"],
        "task_id": normalized["task_id"],
        # Nerv reserves and removes task_id before invoking the task. This explicit
        # application field reaches ImageGen and keys its durable completion record.
        "client_task_id": normalized["task_id"],
        "mode": "depth",
        "model": MODEL_ID,
        "raw_depth_format": RAW_DEPTH_FORMAT,
        "preserve_audio": True,
    }


def artifact_manifest(request: Mapping[str, Any]) -> dict[str, Any]:
    normalized = normalize_request(request)
    return {
        "schema_version": "1.0",
        "task_id": normalized["task_id"],
        "model": MODEL_ID,
        "mode": "depth",
        "raw_depth_format": RAW_DEPTH_FORMAT,
        "preserve_audio": True,
        "artifacts": [{"name": name, "required": True} for name in ARTIFACT_NAMES],
    }


def validate_metrics(request: Mapping[str, Any], metrics: Mapping[str, Any]) -> dict[str, Any]:
    normalized = normalize_request(request)
    failures: list[dict[str, str]] = []
    if metrics.get("input_frame_count") != metrics.get("depth_frame_count"):
        failures.append({"code": "depth_frame_count_mismatch", "message": "depth video frame count must equal input"})
    if (
        normalized["preserve_audio"]
        and metrics.get("input_has_audio") is True
        and metrics.get("output_has_audio") is not True
    ):
        failures.append({"code": "audio_track_missing", "message": "input audio must be preserved"})
    sync_error = metrics.get("av_sync_error_ms")
    if isinstance(sync_error, (int, float)) and sync_error > 40:
        failures.append({"code": "av_sync_exceeded", "message": "A/V sync error exceeds 40 ms"})
    artifact_names = metrics.get("artifact_names")
    if not isinstance(artifact_names, list) or not set(ARTIFACT_NAMES).issubset(artifact_names):
        failures.append(
            {"code": "required_artifacts_missing", "message": "runtime did not report all required artifacts"}
        )
    return {
        "schema_version": "1.0",
        "status": "failed" if failures else "passed",
        "model": MODEL_ID,
        "fallback_used": False,
        "failures": failures,
    }


def _timeout_seconds(env: Mapping[str, str]) -> int:
    raw = _clean_string(env.get("VIDEO_DEPTH_RUNTIME_TIMEOUT_SECONDS"))
    if not raw:
        return DEFAULT_TIMEOUT_SECONDS
    try:
        value = int(raw)
    except ValueError as exc:
        raise ContractError("VIDEO_DEPTH_RUNTIME_TIMEOUT_SECONDS must be an integer") from exc
    if value < 10 or value > MAX_TIMEOUT_SECONDS:
        raise ContractError(f"VIDEO_DEPTH_RUNTIME_TIMEOUT_SECONDS must be between 10 and {MAX_TIMEOUT_SECONDS}")
    return value


def _validate_endpoint_url(url: str, *, allowed_hosts: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise ContractError("VIDEO_DEPTH_RUNTIME_URL is invalid") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ContractError("VIDEO_DEPTH_RUNTIME_URL must use HTTP(S)")
    if parsed.username is not None or parsed.password is not None:
        raise ContractError("VIDEO_DEPTH_RUNTIME_URL credentials are forbidden")
    if parsed.query or parsed.fragment or parsed.path != DIRECT_ENDPOINT_PATH:
        raise ContractError(f"VIDEO_DEPTH_RUNTIME_URL path must be exactly {DIRECT_ENDPOINT_PATH}")
    if port is not None and not 1 <= port <= 65535:
        raise ContractError("VIDEO_DEPTH_RUNTIME_URL port is invalid")
    allowlist = {item.strip().lower().rstrip(".") for item in allowed_hosts.split(",") if item.strip()}
    if not allowlist:
        raise ContractError("VIDEO_DEPTH_RUNTIME_ALLOWED_HOSTS is required for direct runtime mode")
    host = parsed.hostname.lower().rstrip(".")
    if host not in allowlist:
        raise ContractError("VIDEO_DEPTH_RUNTIME_URL host is not in VIDEO_DEPTH_RUNTIME_ALLOWED_HOSTS")
    return url.rstrip("/")


def _extract_auth_token(env: Mapping[str, str]) -> str:
    for name in ("X_AUTH", "AUTH_TOKEN", "KOKO_AUTH_TOKEN"):
        value = _clean_string(env.get(name))
        if value:
            return value
    raw = _clean_string(env.get("KOKO_AUTH"))
    if not raw:
        return ""
    try:
        parsed = json.loads(urllib.parse.unquote(raw))
    except Exception:
        return raw
    return _clean_string(parsed.get("authToken")) if isinstance(parsed, dict) else ""


def _gateway_headers(env: Mapping[str, str], *, gateway_task_id: str = "") -> dict[str, str]:
    canvas_id = _clean_string(env.get("canvas_id"))
    trace_id = _clean_string(env.get("trace_id"))
    missing = [name for name, value in (("canvas_id", canvas_id), ("trace_id", trace_id)) if not value]
    if missing:
        raise ContractError("missing required Agent runtime environment: " + ", ".join(missing))
    headers = {
        "Content-Type": "application/json",
        "token": _clean_string(env.get("VIDEO_DEPTH_SERVICE_TOKEN")),
        "x-canvas-id": canvas_id,
        "x-seele-canvas-trace-id": trace_id,
    }
    if gateway_task_id:
        headers["x-mcp-request-id"] = gateway_task_id
    auth_token = _extract_auth_token(env)
    if auth_token:
        headers["x-auth"] = auth_token
    cookie = _clean_string(env.get("COOKIE") or env.get("Cookie"))
    if cookie:
        headers["Cookie"] = cookie
    for env_name, header_name in (
        ("X_CHANNEL", "x-channel"),
        ("X_CLIENT", "x-client"),
        ("X_VERSION", "x-version"),
        ("REQUEST_ID", "request_id"),
        ("REFERER", "referer"),
        ("USER_AGENT", "user-agent"),
    ):
        value = _clean_string(env.get(env_name))
        if value:
            headers[header_name] = value
    return headers


def resolve_transport(env: Mapping[str, str] | None = None, *, gateway_task_id: str = "") -> Transport:
    values = os.environ if env is None else env
    direct_url = _clean_string(values.get("VIDEO_DEPTH_RUNTIME_URL"))
    if direct_url:
        return Transport(
            kind="direct",
            url=_validate_endpoint_url(
                direct_url,
                allowed_hosts=_clean_string(values.get("VIDEO_DEPTH_RUNTIME_ALLOWED_HOSTS")),
            ),
            headers={"Content-Type": "application/json"},
        )

    base_url = _clean_string(
        values.get("NEW_SYNC_GATE") or values.get("GATEWAY_BASE_URL") or values.get("SYN_GATEWAY_BASE_URL")
    )
    if not base_url:
        syn_base_url = _clean_string(values.get("SYN_BASE_URL"))
        base_url = PUBLIC_APP_TO_INTERNAL_GATEWAY_BASE_URL.get(syn_base_url.rstrip("/"), syn_base_url)
    if not base_url:
        raise ContractError(
            "no approved runtime route: set VIDEO_DEPTH_RUNTIME_URL + VIDEO_DEPTH_RUNTIME_ALLOWED_HOSTS in-cluster, "
            "or use the existing Agent gateway environment"
        )
    parsed = urllib.parse.urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username is not None:
        raise ContractError("Agent gateway base URL is invalid")
    return Transport(
        kind="agent_gateway",
        url=base_url.rstrip("/") + GATEWAY_PATH,
        headers=_gateway_headers(values, gateway_task_id=gateway_task_id),
    )


def preflight(request: Mapping[str, Any], env: Mapping[str, str] | None = None) -> dict[str, Any]:
    blockers: list[dict[str, str]] = []
    try:
        normalized = normalize_request(request)
    except ContractError as exc:
        normalized = {"task_id": "", "model": MODEL_ID}
        blockers.append({"code": "invalid_request", "message": str(exc)})
    try:
        transport = resolve_transport(env)
        _timeout_seconds(os.environ if env is None else env)
    except ContractError as exc:
        transport = None
        blockers.append({"code": "runtime_route_unavailable", "message": str(exc)})
    return {
        "schema_version": "1.0",
        "task_id": normalized.get("task_id", ""),
        "status": "blocked" if blockers else "ready",
        "classification": "env_issue" if blockers else "ready",
        "model": MODEL_ID,
        "transport": transport.kind if transport else None,
        "fallback_used": False,
        "blockers": blockers,
    }


def _read_bounded(response: Any) -> bytes:
    body = response.read(MAX_RESPONSE_BYTES + 1)
    if len(body) > MAX_RESPONSE_BYTES:
        raise ContractError(f"runtime response exceeds {MAX_RESPONSE_BYTES} bytes")
    return body


def _post_json(transport: Transport, payload: Mapping[str, Any], *, timeout_seconds: int) -> tuple[int, Any]:
    request = urllib.request.Request(
        transport.url,
        data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        headers=transport.headers,
        method="POST",
    )
    opener = urllib.request.build_opener(NoRedirectHandler())
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            status = getattr(response, "status", None) or response.getcode()
            body = _read_bounded(response)
    except urllib.error.HTTPError as exc:
        body = _read_bounded(exc)
        detail = body.decode("utf-8", errors="replace")[:1000]
        if exc.code == 504:
            raise RuntimeRequestTimeout(f"runtime HTTP 504: {detail}") from exc
        raise ContractError(f"runtime HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, TimeoutError) or "timed out" in str(exc).lower():
            raise RuntimeRequestTimeout(f"runtime request timed out: {exc}") from exc
        raise ContractError(f"runtime request failed: {exc}") from exc
    except (TimeoutError, OSError) as exc:
        if isinstance(exc, TimeoutError) or "timed out" in str(exc).lower():
            raise RuntimeRequestTimeout(f"runtime request timed out: {exc}") from exc
        raise ContractError(f"runtime request failed: {exc}") from exc
    if not 200 <= status < 300:
        raise ContractError(f"runtime returned non-2xx HTTP status {status}")
    try:
        return status, json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError("runtime returned invalid JSON") from exc


def _task_result_url(env: Mapping[str, str], gateway_task_id: str) -> str:
    base_url = _clean_string(env.get("SYN_BASE_URL"))
    if not base_url:
        raise ContractError("SYN_BASE_URL is required for gateway task recovery")
    try:
        parsed = urllib.parse.urlsplit(base_url)
    except ValueError as exc:
        raise ContractError("SYN_BASE_URL is invalid") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username is not None:
        raise ContractError("SYN_BASE_URL is invalid")
    quoted_task_id = urllib.parse.quote(gateway_task_id, safe="")
    return f"{base_url.rstrip('/')}{TASK_RESULT_PATH}/{quoted_task_id}"


def _durable_result_url(gateway_task_id: str) -> str:
    if not TASK_ID_RE.fullmatch(gateway_task_id):
        raise ContractError("resume_gateway_task_id contains forbidden characters")
    return f"{DURABLE_RESULT_BASE_URL}/{urllib.parse.quote(gateway_task_id, safe='')}.json"


def _get_json(url: str, headers: Mapping[str, str], *, timeout_seconds: int) -> tuple[int, Any]:
    request = urllib.request.Request(url, headers=dict(headers), method="GET")
    opener = urllib.request.build_opener(NoRedirectHandler())
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            status = getattr(response, "status", None) or response.getcode()
            body = _read_bounded(response)
    except urllib.error.HTTPError as exc:
        body = _read_bounded(exc)
        try:
            parsed_body: Any = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            parsed_body = body.decode("utf-8", errors="replace")[:1000]
        return exc.code, parsed_body
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return 0, {"query_error": str(exc)}
    try:
        return status, json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError("task result endpoint returned invalid JSON") from exc


def query_durable_task_result(gateway_task_id: str) -> dict[str, Any]:
    status, body = _get_json(
        _durable_result_url(gateway_task_id),
        {"Accept": "application/json", "Cache-Control": "no-cache"},
        timeout_seconds=TASK_RESULT_REQUEST_TIMEOUT_SECONDS,
    )
    if status in (0, 404):
        state = "query_error" if status == 0 else "not_found"
        return {"success": False, "terminal": False, "state": state, "message": str(body)}
    if not 200 <= status < 300 or not isinstance(body, dict):
        return {
            "success": False,
            "terminal": False,
            "state": "query_error",
            "message": f"durable result query HTTP {status}: {body}",
        }
    if _clean_string(body.get("status")).lower() != "completed":
        return {"success": False, "terminal": False, "state": "invalid_response"}
    if body.get("task_id") != gateway_task_id:
        return {
            "success": False,
            "terminal": True,
            "state": "completed",
            "message": "durable result task_id mismatch",
        }
    if body.get("success") is False:
        return {
            "success": False,
            "terminal": True,
            "state": "completed",
            "message": _clean_string(body.get("message")) or "video-depth task failed",
        }
    result_body = body.get("data")
    if body.get("success") is not True or not isinstance(result_body, dict):
        return {
            "success": False,
            "terminal": True,
            "state": "completed",
            "message": "durable result is missing completed task data",
        }
    return {"success": True, "terminal": True, "state": "completed", "data": result_body}


def query_gateway_task_result(
    gateway_task_id: str,
    env: Mapping[str, str],
) -> dict[str, Any]:
    status, body = _get_json(
        _task_result_url(env, gateway_task_id),
        _gateway_headers(env, gateway_task_id=gateway_task_id),
        timeout_seconds=TASK_RESULT_REQUEST_TIMEOUT_SECONDS,
    )
    if status == 0:
        return {"success": False, "terminal": False, "state": "query_error", "message": str(body)}
    if not 200 <= status < 300 or not isinstance(body, dict):
        return {
            "success": False,
            "terminal": False,
            "state": "query_error",
            "message": f"task result query HTTP {status}: {body}",
        }
    state = _clean_string(body.get("status")).lower()
    if state != "completed":
        return {"success": False, "terminal": False, "state": state or "invalid_response"}
    result_body = body.get("data")
    if not isinstance(result_body, dict):
        return {
            "success": False,
            "terminal": True,
            "state": "completed",
            "message": "completed gateway task has no result data",
        }
    if result_body.get("success") is False or ("code" in result_body and result_body.get("code") not in (None, 0)):
        return {
            "success": False,
            "terminal": True,
            "state": "completed",
            "message": f"recovered video-depth task failed: {result_body}",
        }
    return {"success": True, "terminal": True, "state": "completed", "data": result_body}


def _unwrap_runtime_data(body: Any) -> dict[str, Any]:
    current = body
    for _ in range(6):
        if not isinstance(current, dict):
            break
        if current.get("success") is False:
            message = (
                _clean_string(current.get("message")) or _clean_string(current.get("msg")) or "runtime success=false"
            )
            raise ContractError(message)
        if isinstance(current.get("artifacts"), dict) and isinstance(current.get("receipt"), dict):
            return current
        next_value = current.get("data")
        if isinstance(next_value, dict):
            current = next_value
            continue
        result_value = current.get("result")
        if isinstance(result_value, dict):
            current = result_value
            continue
        break
    raise ContractError("runtime response is missing data.artifacts and data.receipt")


def _validate_artifact_url(name: str, value: Any) -> str:
    return _validate_media_url(value, field_name=f"artifact {name}")


def validate_runtime_response(body: Any) -> dict[str, Any]:
    data = _unwrap_runtime_data(body)
    if data.get("model") != MODEL_ID:
        raise ContractError("runtime model substitution detected")
    artifacts = data["artifacts"]
    if set(artifacts) != set(ARTIFACT_NAMES):
        raise ContractError("runtime artifact set does not match the six-artifact contract")
    checked_artifacts = {name: _validate_artifact_url(name, artifacts[name]) for name in ARTIFACT_NAMES}

    receipt = data["receipt"]
    if receipt.get("status") != "succeeded" or receipt.get("classification") != "success":
        raise ContractError("runtime receipt is not a classified success")
    if receipt.get("model") != MODEL_ID or receipt.get("fallback_used") is not False:
        raise ContractError("runtime receipt reports model substitution or fallback")
    gpu = receipt.get("gpu")
    if not isinstance(gpu, str) or not gpu.strip() or "cpu" in gpu.lower():
        raise ContractError("runtime receipt does not attest CUDA/GPU execution")
    output_validation = receipt.get("output_validation")
    if not isinstance(output_validation, dict) or output_validation.get("passed") is not True:
        raise ContractError("runtime output validation did not pass")

    return {
        "task_id": _clean_string(data.get("task_id")),
        "model": MODEL_ID,
        "artifacts": checked_artifacts,
        "receipt": receipt,
    }


def _success_result(
    result: Mapping[str, Any],
    *,
    task_id: str,
    status: int,
    transport: str,
    recovered: bool = False,
    recovery_query_attempts: int = 0,
    recovery_elapsed_seconds: float = 0.0,
) -> dict[str, Any]:
    response = {
        "success": True,
        "status": status,
        "transport": transport,
        "task_id": _clean_string(result.get("task_id")) or task_id,
        "model": MODEL_ID,
        "fallback_used": False,
        "url": result["artifacts"]["depth.mp4"],
        "artifacts": result["artifacts"],
        "receipt": result["receipt"],
        "message": "ok",
    }
    if recovered:
        response.update(
            {
                "recovered": True,
                "gateway_task_id": task_id,
                "recovery_query_attempts": recovery_query_attempts,
                "recovery_elapsed_seconds": recovery_elapsed_seconds,
            }
        )
    return response


def _ambiguous_timeout_result(gateway_task_id: str, message: str, *, recovery_attempted: bool) -> dict[str, Any]:
    return {
        "success": False,
        "status": "pending",
        "classification": "ambiguous_timeout",
        "message": message,
        "error_type": "ambiguous_timeout",
        "timed_out": True,
        "retry_safe": False,
        "backend_may_still_be_running": True,
        "recovery_supported": True,
        "recovery_attempted": recovery_attempted,
        "gateway_task_id": gateway_task_id,
        "resume_gateway_task_id": gateway_task_id,
        "model": MODEL_ID,
        "fallback_used": False,
        "guidance": (
            "Run this script again with resume_gateway_task_id only; poll the existing task and never resubmit it."
        ),
    }


def poll_gateway_task_result(
    gateway_task_id: str,
    env: Mapping[str, str],
    *,
    timeout_seconds: int = RECOVERY_POLL_TIMEOUT_SECONDS,
    poll_interval_seconds: int = RECOVERY_POLL_INTERVAL_SECONDS,
) -> dict[str, Any]:
    task_id = _clean_string(gateway_task_id)
    if not task_id:
        raise ContractError("resume_gateway_task_id must be a non-empty string")
    started_at = time.monotonic()
    deadline = started_at + max(0, timeout_seconds)
    query_attempts = 0
    last_state = "not_found"
    while True:
        query_attempts += 1
        durable_result = query_durable_task_result(task_id)
        gateway_result = (
            {"success": False, "terminal": False, "state": "not_queried"}
            if durable_result.get("success") or durable_result.get("terminal")
            else query_gateway_task_result(task_id, env)
        )
        for transport_name, query_result in (
            ("durable_result", durable_result),
            ("gateway_task_result", gateway_result),
        ):
            if query_result.get("success"):
                validated = validate_runtime_response(query_result.get("data"))
                return _success_result(
                    validated,
                    task_id=task_id,
                    status=200,
                    transport=transport_name,
                    recovered=True,
                    recovery_query_attempts=query_attempts,
                    recovery_elapsed_seconds=round(time.monotonic() - started_at, 3),
                )
            if query_result.get("terminal"):
                raise ContractError(query_result.get("message") or "recovered video-depth task failed")
        last_state = "durable={0},gateway={1}".format(
            _clean_string(durable_result.get("state")) or "unknown",
            _clean_string(gateway_result.get("state")) or "unknown",
        )
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            result = _ambiguous_timeout_result(
                task_id,
                f"video-depth task is still {last_state}; continue polling the existing gateway task",
                recovery_attempted=True,
            )
            result.update(
                {
                    "recovery_query_attempts": query_attempts,
                    "recovery_elapsed_seconds": round(time.monotonic() - started_at, 3),
                }
            )
            return result
        time.sleep(min(poll_interval_seconds, remaining))


def execute(request: Mapping[str, Any], env: Mapping[str, str] | None = None) -> dict[str, Any]:
    values = os.environ if env is None else env
    resume_gateway_task_id = _clean_string(request.get("resume_gateway_task_id"))
    if resume_gateway_task_id:
        return poll_gateway_task_result(resume_gateway_task_id, values)

    normalized = normalize_request(request)
    task_id = normalized["task_id"]
    transport = resolve_transport(values, gateway_task_id=task_id)
    timeout_seconds = _timeout_seconds(values)
    if transport.kind == "agent_gateway":
        timeout_seconds = min(timeout_seconds, GATEWAY_SUBMIT_TIMEOUT_SECONDS)
    try:
        status, body = _post_json(
            transport,
            runtime_payload(normalized),
            timeout_seconds=timeout_seconds,
        )
    except RuntimeRequestTimeout as exc:
        if transport.kind != "agent_gateway":
            raise
        return _ambiguous_timeout_result(task_id, str(exc), recovery_attempted=False)
    body_code = body.get("code") if isinstance(body, dict) else None
    inner_body = body.get("data") if isinstance(body, dict) else None
    inner_code = inner_body.get("code") if isinstance(inner_body, dict) else None
    if transport.kind == "agent_gateway" and (status == 504 or body_code == 504 or inner_code == 504):
        return _ambiguous_timeout_result(
            task_id,
            f"gateway returned an ambiguous timeout: HTTP {status}: {body}",
            recovery_attempted=False,
        )
    result = validate_runtime_response(body)
    return _success_result(result, task_id=task_id, status=status, transport=transport.kind)


def _load_input(args: argparse.Namespace) -> dict[str, Any]:
    raw = os.environ.get(args.input_env, "") if args.input_env else args.json
    if not raw:
        raise ContractError("missing JSON input")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ContractError("input is not valid JSON") from exc
    if not isinstance(value, dict):
        raise ContractError("input must be a JSON object")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-env", default="VIDEO_DEPTH_INPUT", help="environment variable containing request JSON")
    parser.add_argument("--json", default="", help="request JSON; prefer --input-env to avoid shell quoting")
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args()
    try:
        request = _load_input(args)
        result = preflight(request) if args.preflight else execute(request)
        exit_code = 0 if result.get("status") != "blocked" else 2
    except ContractError as exc:
        result = {
            "success": False,
            "status": "failed",
            "classification": "contract_or_runtime_error",
            "model": MODEL_ID,
            "fallback_used": False,
            "message": str(exc),
        }
        exit_code = 2
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
