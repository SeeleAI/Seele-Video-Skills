from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
import urllib.parse
from dataclasses import dataclass
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request
from uuid import uuid4

TOKEN = str(os.environ.get("MOTION_SERVICE_TOKEN") or "").strip()


@dataclass(slots=True)
class RuntimeConfig:
    syn_base_url: str
    app_base_url: str
    canvas_id: str
    trace_id: str
    new_sync_gate: str = ""


DEFAULT_RUNTIME_CONFIG: RuntimeConfig | None = None

REQUIRED_RUNTIME_ENV_VARS = (
    "SYN_BASE_URL",
    "APP_BASE_URL",
    "canvas_id",
    "trace_id",
)

REQUIRED_PUBLIC_URL_ENV_VARS = (
    "s3_SecretId",
    "s3_SecretKey",
)

S3_PRIVATE_BUCKET = "seelemedia-private"
S3_PUBLIC_BUCKET = "seelemedia"
S3_PUBLIC_REGION = "us-east-1"
S3_PUBLIC_CDN_BASE_URL = "https://static.seeles.ai"

_URL_PREFIXES = ("http://", "https://", "s3://")


def _read_env_values(names: tuple[str, ...]) -> tuple[dict[str, str], list[str]]:
    values: dict[str, str] = {}
    missing: list[str] = []
    for name in names:
        value = str(os.environ.get(name) or "").strip()
        if value:
            values[name] = value
        else:
            missing.append(name)
    return values, missing


def format_missing_env_message(names: list[str], *, purpose: str) -> str:
    return f"missing required environment variables for {purpose}: {', '.join(names)}"


def resolve_runtime_config(runtime: RuntimeConfig | None = None) -> RuntimeConfig:
    if runtime is not None:
        return runtime
    values, missing = _read_env_values(REQUIRED_RUNTIME_ENV_VARS)
    if missing:
        raise RuntimeError(format_missing_env_message(missing, purpose="runtime config"))
    return RuntimeConfig(
        syn_base_url=values["SYN_BASE_URL"],
        app_base_url=values["APP_BASE_URL"],
        canvas_id=values["canvas_id"],
        trace_id=values["trace_id"],
        new_sync_gate=str(os.environ.get("NEW_SYNC_GATE") or "").strip(),
    )


def require_canvas_and_trace(*, canvas_id: str, trace_id: str) -> None:
    missing: list[str] = []
    if not str(canvas_id).strip():
        missing.append("canvas_id")
    if not str(trace_id).strip():
        missing.append("trace_id")
    if missing:
        raise RuntimeError("missing required input fields: " + ", ".join(missing))


def resolve_gateway_base_url(runtime: RuntimeConfig) -> str:
    return (runtime.new_sync_gate or runtime.syn_base_url).rstrip("/")


def load_public_url_env() -> dict[str, str]:
    values, missing = _read_env_values(REQUIRED_PUBLIC_URL_ENV_VARS)
    if missing:
        raise RuntimeError(format_missing_env_message(missing, purpose="public url conversion"))
    return values


def _parse_koko_auth(raw_koko_auth: str) -> dict[str, Any] | None:
    if not raw_koko_auth:
        return None
    try:
        parsed = json.loads(urllib.parse.unquote(raw_koko_auth))
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def _extract_auth_token_from_env() -> str:
    for name in ("X_AUTH", "AUTH_TOKEN", "KOKO_AUTH_TOKEN"):
        value = str(os.environ.get(name) or "").strip()
        if value:
            return value

    raw_koko_auth = str(os.environ.get("KOKO_AUTH") or "").strip()
    parsed = _parse_koko_auth(raw_koko_auth)
    if isinstance(parsed, dict):
        return str(parsed.get("authToken") or "").strip()
    return raw_koko_auth


def _build_cookie_header_from_env() -> str:
    raw_cookie = str(os.environ.get("COOKIE") or os.environ.get("Cookie") or "").strip()
    if raw_cookie:
        return raw_cookie

    raw_koko_auth = str(os.environ.get("KOKO_AUTH") or "").strip()
    if not raw_koko_auth:
        return ""
    parsed = _parse_koko_auth(raw_koko_auth)
    if parsed is not None:
        raw_koko_auth = urllib.parse.quote(json.dumps(parsed, separators=(",", ":")))
    return f"KOKO_AUTH={raw_koko_auth}"


def build_headers(runtime: RuntimeConfig, canvas_id: str, trace_id: str) -> dict[str, str]:
    headers = {
        "token": TOKEN,
        "Content-Type": "application/json",
        "x-canvas-id": canvas_id,
        "x-seele-canvas-trace-id": trace_id,
    }

    auth_token = _extract_auth_token_from_env()
    if auth_token:
        headers["x-auth"] = auth_token

    cookie_header = _build_cookie_header_from_env()
    if cookie_header:
        headers["Cookie"] = cookie_header

    for env_name, header_name in (
        ("X_CHANNEL", "x-channel"),
        ("X_CLIENT", "x-client"),
        ("X_VERSION", "x-version"),
        ("REQUEST_ID", "request_id"),
        ("REFERER", "referer"),
        ("USER_AGENT", "user-agent"),
    ):
        value = str(os.environ.get(env_name) or "").strip()
        if value:
            headers[header_name] = value

    return headers


def extract_trace_part(trace_id: str, index: int) -> str:
    if not isinstance(trace_id, str) or not trace_id:
        return ""
    parts = [part.strip() for part in trace_id.split("|")]
    if index < len(parts) and parts[index]:
        return parts[index]
    return ""


def extract_turn_id(trace_id: str) -> str:
    return extract_trace_part(trace_id, 1)


def extract_agent_name(trace_id: str) -> str:
    return extract_trace_part(trace_id, 2)


def extract_tool_name(trace_id: str) -> str:
    return extract_trace_part(trace_id, 3)


def extract_step_id(trace_id: str) -> str:
    return extract_trace_part(trace_id, 4) or str(uuid4())


async def post_json(
    request_url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    *,
    timeout_seconds: int,
) -> tuple[int | None, Any]:
    def _send() -> tuple[int | None, Any]:
        req = urllib_request.Request(
            request_url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib_request.urlopen(req, timeout=timeout_seconds) as resp:
                status = getattr(resp, "status", None) or resp.getcode()
                body = resp.read()
                try:
                    return status, json.loads(body)
                except Exception:
                    return status, {"text": body.decode("utf-8", errors="replace")}
        except urllib_error.HTTPError as exc:
            body = exc.read()
            try:
                parsed = json.loads(body)
            except Exception:
                parsed = {"text": body.decode("utf-8", errors="replace")}
            return exc.code, parsed

    try:
        return await asyncio.to_thread(_send)
    except Exception as exc:
        return None, exc


def _is_url(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(_URL_PREFIXES)


def _cdn_replace_host(url: str, *, public_bucket: str, public_region: str, public_cdn_base_url: str) -> str:
    if not url:
        return url
    candidates = [f"https://{public_bucket}.s3.amazonaws.com"]
    if public_region:
        candidates.append(f"https://{public_bucket}.s3.{public_region}.amazonaws.com")
    for src in candidates:
        if url.startswith(src):
            return url.replace(src, public_cdn_base_url, 1)
    return url


def _parse_s3_url(url: str) -> tuple[str, str]:
    if url.startswith("s3://"):
        rest = url[5:]
        if "/" not in rest:
            raise ValueError("invalid s3 url: missing key")
        bucket, key = rest.split("/", 1)
        if not bucket or not key:
            raise ValueError("invalid s3 url: missing bucket or key")
        return bucket, key
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc
    path = parsed.path.lstrip("/")
    if not host:
        raise ValueError("invalid url: missing host")
    if host == "s3.amazonaws.com" or host.startswith("s3.") or host.startswith("s3-"):
        bucket, sep, key = path.partition("/")
        if not sep or not bucket or not key:
            raise ValueError("invalid path-style s3 url: missing bucket/key")
        return bucket, key
    if ".s3.amazonaws.com" in host or ".s3." in host:
        bucket = host.split('.s3')[0]
        key = path
        if not bucket or not key:
            raise ValueError("invalid virtual-hosted s3 url: missing bucket/key")
        return bucket, key
    raise ValueError("not an s3 url")


def _build_public_origin_url(key: str, *, public_bucket: str, public_region: str) -> str:
    if public_region == "us-east-1":
        return f"https://{public_bucket}.s3.amazonaws.com/{key}"
    return f"https://{public_bucket}.s3.{public_region}.amazonaws.com/{key}"


def _copy_to_public_bucket(source_url: str, env: dict[str, str], *, tag: str = "assets") -> str:
    import boto3

    private_bucket = S3_PRIVATE_BUCKET
    public_bucket = S3_PUBLIC_BUCKET
    public_region = S3_PUBLIC_REGION
    public_access_key_id = env["s3_SecretId"]
    public_secret_access_key = env["s3_SecretKey"]
    public_cdn_base_url = S3_PUBLIC_CDN_BASE_URL

    bucket, object_key = _parse_s3_url(source_url)
    if bucket == public_bucket:
        return _cdn_replace_host(
            _build_public_origin_url(object_key, public_bucket=public_bucket, public_region=public_region),
            public_bucket=public_bucket,
            public_region=public_region,
            public_cdn_base_url=public_cdn_base_url,
        )
    if bucket != private_bucket:
        return source_url

    public_client = boto3.client(
        "s3",
        region_name=public_region,
        aws_access_key_id=public_access_key_id,
        aws_secret_access_key=public_secret_access_key,
    )
    file_name = object_key.rsplit("/", 1)[-1]
    target_key = f"media/{tag}/{uuid4().hex}_{time.time_ns()}_{file_name}"
    public_client.copy_object(Bucket=public_bucket, Key=target_key, CopySource={"Bucket": bucket, "Key": object_key})
    return _cdn_replace_host(
        _build_public_origin_url(target_key, public_bucket=public_bucket, public_region=public_region),
        public_bucket=public_bucket,
        public_region=public_region,
        public_cdn_base_url=public_cdn_base_url,
    )


async def to_public_url(url: str, *, tag: str = "assets") -> str:
    if not _is_url(url):
        return ""
    env = load_public_url_env()
    private_bucket = S3_PRIVATE_BUCKET
    public_bucket = S3_PUBLIC_BUCKET
    public_region = S3_PUBLIC_REGION
    public_cdn_base_url = S3_PUBLIC_CDN_BASE_URL
    if url.startswith(("http://", "https://")):
        try:
            bucket, _ = _parse_s3_url(url)
        except ValueError:
            return _cdn_replace_host(url, public_bucket=public_bucket, public_region=public_region, public_cdn_base_url=public_cdn_base_url)
        if bucket == private_bucket:
            return await asyncio.to_thread(_copy_to_public_bucket, url, env, tag=tag)
        return _cdn_replace_host(url, public_bucket=public_bucket, public_region=public_region, public_cdn_base_url=public_cdn_base_url)
    if url.startswith("s3://"):
        return await asyncio.to_thread(_copy_to_public_bucket, url, env, tag=tag)
    return url


async def publicify_payload_urls(data: Any, *, tag: str = "assets") -> Any:
    if isinstance(data, dict):
        result: dict[str, Any] = {}
        for key, value in data.items():
            if isinstance(value, str) and _is_url(value):
                result[key] = await to_public_url(value, tag=tag)
            else:
                result[key] = await publicify_payload_urls(value, tag=tag)
        return result
    if isinstance(data, list):
        return [await publicify_payload_urls(item, tag=tag) for item in data]
    return data


def pick_url(data: Any) -> str:
    if isinstance(data, str):
        return data if _is_url(data) else ""
    if isinstance(data, dict):
        for key in ["video_url_public", "image_url_public", "video_url", "image_url", "url", "output_url", "result_url", "resource_url"]:
            value = data.get(key)
            if _is_url(value):
                return value
        for value in data.values():
            picked = pick_url(value)
            if picked:
                return picked
    if isinstance(data, list):
        for item in data:
            picked = pick_url(item)
            if picked:
                return picked
    return ""


def load_json_input() -> dict[str, Any]:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-file", required=True)
    args = parser.parse_args()
    with open(args.input_file, "r", encoding="utf-8") as f:
        return json.load(f)


def dump_json_output(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
