from __future__ import annotations

import asyncio
import os
import random
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common import (  # noqa: E402
    DEFAULT_RUNTIME_CONFIG,
    RuntimeConfig,
    build_headers,
    dump_json_output,
    load_json_input,
    pick_url,
    post_json,
    publicify_payload_urls,
    require_canvas_and_trace,
    resolve_gateway_base_url,
    resolve_runtime_config,
)

TEXT_TO_MOTION_PATH = "/gateway/mq?abs_cuda_proxy_service_name=text2motion-atom&abs_cuda_proxy_func_name=create_motion_new"
VIDEO_TO_MOTION_PATH = "/gateway/mq?abs_cuda_proxy_service_name=motion-video-capture-atom&abs_cuda_proxy_func_name=create_video_motion"
DEFAULT_VIDEO_GPU_IDS = [str(index) for index in range(8)]
MAX_EMPTY_RESULT_RETRIES = 2
VIDEO_TO_MOTION_OPTIONAL_STRING_KEYS = ("callback_url", "call_back_url", "run_mode")
TEXT_TO_MOTION_OPTIONAL_STRING_KEYS = ("callback_url", "call_back_url")

MOTION_URL_KEYS = (
    "fbx",
    "fbx_url",
    "mp4",
    "png",
    "motion_url",
    "camera_url",
    "camera_rootmotion_url",
    "camera_info_url",
    "mp4_url",
    "video_url",
    "png_url",
    "preview_url",
    "url",
)


def _non_empty_string(value: Any) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else ""


def resolve_motion_mode(input_data: dict[str, Any]) -> dict[str, str] | str:
    prompt = _non_empty_string(input_data.get("prompt"))
    video_url = _non_empty_string(input_data.get("video_url"))
    if bool(prompt) == bool(video_url):
        return "exactly one of prompt or video_url must be provided"
    if video_url:
        return {"mode": "video_to_motion", "video_url": video_url}
    return {"mode": "text_to_motion", "prompt": prompt}


def _gpu_candidates_from_env() -> list[str]:
    raw = str(os.environ.get("MOTION_VIDEO_CAPTURE_GPU_IDS") or "").strip()
    if not raw:
        return DEFAULT_VIDEO_GPU_IDS
    candidates = [item.strip() for item in raw.split(",") if item.strip()]
    return candidates or DEFAULT_VIDEO_GPU_IDS


def resolve_cuda_visible_devices(input_data: dict[str, Any]) -> str:
    explicit = _non_empty_string(input_data.get("CUDA_VISIBLE_DEVICES")) or _non_empty_string(
        input_data.get("cuda_visible_devices")
    )
    if explicit:
        return explicit
    return random.choice(_gpu_candidates_from_env())


def build_motion_request(resolved: dict[str, str], input_data: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    task_id = _non_empty_string(input_data.get("task_id")) or str(uuid4())
    if resolved["mode"] == "video_to_motion":
        payload: dict[str, Any] = {
            "task_id": task_id,
            "input_video_url": resolved["video_url"],
            "CUDA_VISIBLE_DEVICES": resolve_cuda_visible_devices(input_data),
        }
        for key in VIDEO_TO_MOTION_OPTIONAL_STRING_KEYS:
            value = _non_empty_string(input_data.get(key))
            if value:
                payload[key] = value
        if isinstance(input_data.get("need_camera"), bool):
            payload["need_camera"] = input_data["need_camera"]
        return VIDEO_TO_MOTION_PATH, payload
    payload = {
        "task_id": task_id,
        "text_prompt": resolved["prompt"],
    }
    cuda_visible_devices = _non_empty_string(input_data.get("CUDA_VISIBLE_DEVICES")) or _non_empty_string(
        input_data.get("cuda_visible_devices")
    )
    if cuda_visible_devices:
        payload["CUDA_VISIBLE_DEVICES"] = cuda_visible_devices
    for key in TEXT_TO_MOTION_OPTIONAL_STRING_KEYS:
        value = _non_empty_string(input_data.get(key))
        if value:
            payload[key] = value
    return TEXT_TO_MOTION_PATH, payload


def collect_motion_urls(data: Any) -> dict[str, str]:
    urls: dict[str, str] = {}

    def _walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key in MOTION_URL_KEYS:
                    url = _non_empty_string(item)
                    if url:
                        urls.setdefault(key, url)
                _walk(item)
        elif isinstance(value, list):
            for item in value:
                _walk(item)

    _walk(data)
    if "url" not in urls:
        picked = pick_url(data)
        if picked:
            urls["url"] = picked
    return urls


def _backend_message(data: Any) -> str:
    if not isinstance(data, dict):
        return ""
    for key in ("message", "msg", "error", "error_message"):
        value = _non_empty_string(data.get(key))
        if value:
            return value
    nested = data.get("data")
    if isinstance(nested, dict):
        return _backend_message(nested)
    return ""


def _body_success(data: Any) -> bool:
    if not isinstance(data, dict):
        return False
    if data.get("success") is True:
        return True
    if data.get("code") == 0:
        return True
    if data.get("error_code") == 0:
        return True
    nested = data.get("data")
    return isinstance(nested, dict) and (
        nested.get("success") is True or nested.get("code") == 0 or nested.get("error_code") == 0
    )


async def motion_gen(input_data: dict[str, Any], *, runtime: RuntimeConfig | None = DEFAULT_RUNTIME_CONFIG) -> dict[str, Any]:
    resolved = resolve_motion_mode(input_data)
    if isinstance(resolved, str):
        return {"success": False, "message": resolved}

    try:
        runtime = resolve_runtime_config(runtime)
    except RuntimeError as exc:
        return {"success": False, "message": str(exc)}

    canvas_id = runtime.canvas_id.strip()
    trace_id = runtime.trace_id.strip()
    try:
        require_canvas_and_trace(canvas_id=canvas_id, trace_id=trace_id)
    except RuntimeError as exc:
        return {"success": False, "message": str(exc)}

    gateway_base_url = resolve_gateway_base_url(runtime)
    last_result: dict[str, Any] | None = None
    for attempt in range(MAX_EMPTY_RESULT_RETRIES + 1):
        path, payload = build_motion_request(resolved, input_data)
        status, data = await post_json(
            f"{gateway_base_url}{path}",
            payload,
            build_headers(runtime, canvas_id, trace_id),
            timeout_seconds=900,
        )
        if isinstance(data, Exception):
            return {
                "success": False,
                "status": None,
                "mode": resolved["mode"],
                "urls": {},
                "url": "",
                "data": None,
                "attempts": attempt + 1,
                "message": f"request failed: {data}",
            }

        try:
            public_data = await publicify_payload_urls(data, tag="assets")
        except RuntimeError as exc:
            return {
                "success": False,
                "status": status,
                "mode": resolved["mode"],
                "urls": {},
                "url": "",
                "data": data,
                "attempts": attempt + 1,
                "message": str(exc),
            }

        urls = collect_motion_urls(public_data)
        primary_url = (
            urls.get("fbx_url")
            or urls.get("fbx")
            or urls.get("motion_url")
            or urls.get("camera_rootmotion_url")
            or urls.get("camera_url")
            or urls.get("url")
            or urls.get("mp4_url")
            or urls.get("mp4")
            or urls.get("png_url")
            or urls.get("png")
            or ""
        )
        http_ok = status is not None and 200 <= status < 300
        success = http_ok and _body_success(data) and bool(primary_url)
        backend_message = _backend_message(data)
        last_result = {
            "success": success,
            "status": status,
            "mode": resolved["mode"],
            "url": primary_url,
            "urls": urls,
            "data": public_data,
            "attempts": attempt + 1,
            "message": "ok" if success else (
                f"HTTP {status}: backend returned no final motion url"
                + (f" ({backend_message})" if backend_message else "")
                if http_ok
                else f"HTTP {status}"
            ),
        }
        if success or not http_ok or primary_url or attempt >= MAX_EMPTY_RESULT_RETRIES:
            return last_result

    assert last_result is not None
    return last_result


async def _main() -> None:
    dump_json_output(await motion_gen(load_json_input()))


if __name__ == "__main__":
    asyncio.run(_main())
