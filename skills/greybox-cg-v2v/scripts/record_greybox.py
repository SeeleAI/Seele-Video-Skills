#!/usr/bin/env python3
"""
record_greybox.py — Record a deterministic Three.js grey-box shot to an mp4 file.

The companion Three.js template (assets/template/) renders itself deterministically: opened
with ?record=1 it advances the shot clock by exactly 1/fps per step and renders each frame.
There are two capture paths, selected by --mode:

  • frames (DEFAULT): the page exposes `window.__frame.grab(i)` which renders frame i and
    returns it as a PNG data URL. This driver pulls each frame and lets ffmpeg assemble the
    mp4. Robust on headless servers with or without a GPU.
  • stream: the page records itself with MediaRecorder and exposes the encoded clip on
    `window.__cap`. Only use where MediaRecorder + captureStream are reliable (often NOT on
    GPU-less headless servers).

GPU handling (--gl, default `auto`): try to use the GPU first, and if the page can't create a
WebGL context (e.g. a GPU-less server), automatically relaunch with software WebGL (SwiftShader).
So the SAME build is fast on a GPU box and still works on a GPU-less sandbox — no per-env config.
Force a mode with `--gl hardware` or `--gl software` if needed.

Capture contracts (what the page exposes):
    window.__frame = { ready, total, fps, error, grab(i) -> "data:image/png;base64,..." }   # frames mode
    window.__cap   = { ready, b64, mime, frames, error }                                      # stream mode
    Page URL params: ?record=1&mode=<frames|stream>&fps=<int>&seconds=<num>&w=<int>&h=<int>

Run (deps fetched on demand; pre-install them in the runtime to avoid per-run downloads):
    uv run --with playwright --with imageio-ffmpeg \
      python {{env_base_path}}/skills/greybox-cg-v2v/scripts/record_greybox.py \
      --dir <build_dir> --out <out.mp4> --fps 24 --seconds 8 --width 1280 --height 720

Success output is a single JSON line on stdout:
    {"success": true, "mp4": "<abs>", "video_path": "<abs>", "duration_ms": 8000,
     "sha256": "sha256:...", "frame0": "<abs>_frame0.png", "mode": "frames", "gl": "hardware",
     "bytes": 123456, "fps": 24, "seconds": 8.0, "width": 1280, "height": 720, "frames": 192}
    `gl` reports which GL backend actually worked. `frame0` is the first frame as a PNG — the source
    still for the combined-reference path (restyle it, then pass as image_url). Pass --no-frame0 to skip.
Failure output is also JSON. Invalid input exits 2 with `retryable=false`; capture/encode failures exit
3 with `retryable=true`; non-retryable runtime failures reserve exit 4. The script does not retry
internally forever; callers decide retry/reconciliation from the structured error.
"""

from __future__ import annotations

import argparse
import base64
import functools
import glob
import hashlib
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# Prefer the GPU: let ANGLE pick the platform hardware backend; ignore the blocklist so a headless
# GPU isn't refused. On a GPU box this renders in hardware (fast).
GL_HARDWARE_ARGS = ["--use-gl=angle", "--ignore-gpu-blocklist"]

# Software WebGL fallback (no GPU needed). --use-gl=angle + --use-angle=swiftshader is the key pair:
# ANGLE alone still tries the hardware backend (D3D11 on Windows) and fails on a GPU-less server with
# "Error creating WebGL context". This forces the SwiftShader software backend.
GL_SOFTWARE_ARGS = [
    "--use-gl=angle",
    "--use-angle=swiftshader",
    "--enable-unsafe-swiftshader",
    "--ignore-gpu-blocklist",
    "--disable-gpu-sandbox",
    "--disable-features=Vulkan",
]


class _GLInitError(RuntimeError):
    """Raised when the page cannot initialize a WebGL context under a given GL mode (triggers fallback)."""


class _RecordingError(RuntimeError):
    """Machine-readable recorder failure."""

    def __init__(self, code: str, message: str, *, retryable: bool, exit_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.exit_code = exit_code


EXIT_INVALID_INPUT = 2
EXIT_RETRYABLE_FAILURE = 3
EXIT_NON_RETRYABLE_FAILURE = 4


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def _json_success(payload: dict) -> None:
    print(json.dumps({"success": True, **payload}, sort_keys=True))


def _json_error(code: str, message: str, *, retryable: bool, exit_code: int) -> None:
    print(json.dumps({
        "success": False,
        "message": message,
        "retryable": retryable,
        "error_code": code,
        "error": {
            "code": code,
            "message": message,
            "retryable": retryable,
            "exit_code": exit_code,
        },
    }, sort_keys=True))


def _invalid_input(message: str) -> _RecordingError:
    return _RecordingError("invalid_input", message, retryable=False, exit_code=EXIT_INVALID_INPUT)


def _retryable_failure(message: str, code: str = "recording_failed") -> _RecordingError:
    return _RecordingError(code, message, retryable=True, exit_code=EXIT_RETRYABLE_FAILURE)


def _dependency_unavailable(message: str) -> _RecordingError:
    return _RecordingError(
        "dependency_unavailable",
        message,
        retryable=False,
        exit_code=EXIT_NON_RETRYABLE_FAILURE,
    )


class _JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise _invalid_input(message)


def _validate_args(args: argparse.Namespace) -> None:
    if args.fps <= 0:
        raise _invalid_input("--fps must be > 0")
    if args.seconds <= 0:
        raise _invalid_input("--seconds must be > 0")
    if args.width <= 0 or args.height <= 0:
        raise _invalid_input("--width and --height must be > 0")
    build_dir = os.path.abspath(args.dir)
    index = os.path.join(build_dir, "index.html")
    if not os.path.exists(index):
        raise _invalid_input(f"no index.html in {build_dir}")


def _resolve_ffmpeg_exe() -> str:
    try:
        import imageio_ffmpeg  # noqa: PLC0415
    except ModuleNotFoundError as exc:
        raise _dependency_unavailable("missing Python dependency: imageio_ffmpeg") from exc

    try:
        ff = imageio_ffmpeg.get_ffmpeg_exe()
    except (FileNotFoundError, PermissionError) as exc:
        raise _dependency_unavailable(f"ffmpeg executable unavailable: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise _dependency_unavailable(f"ffmpeg executable unavailable: {exc}") from exc

    if not ff or not os.path.exists(ff):
        raise _dependency_unavailable(f"ffmpeg executable unavailable: {ff or '<empty>'}")
    if not os.access(ff, os.X_OK):
        raise _dependency_unavailable(f"ffmpeg executable is not executable: {ff}")
    return ff


def _preflight_dependencies() -> None:
    if importlib.util.find_spec("playwright") is None:
        raise _dependency_unavailable("missing Python dependency: playwright")
    if importlib.util.find_spec("imageio_ffmpeg") is None:
        raise _dependency_unavailable("missing Python dependency: imageio_ffmpeg")
    _resolve_ffmpeg_exe()


def _gl_attempts(gl: str) -> list[tuple[str, list[str]]]:
    if gl == "hardware":
        return [("hardware", GL_HARDWARE_ARGS)]
    if gl == "software":
        return [("software", GL_SOFTWARE_ARGS)]
    return [("hardware", GL_HARDWARE_ARGS), ("software", GL_SOFTWARE_ARGS)]  # auto: GPU first, then SwiftShader


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _serve(directory: str, port: int) -> ThreadingHTTPServer:
    handler = functools.partial(SimpleHTTPRequestHandler, directory=directory)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def _find_cached_chromium() -> str | None:
    """Locate a Playwright-cached Chromium so we don't depend on `playwright install` at runtime."""
    roots = [
        os.environ.get("PLAYWRIGHT_BROWSERS_PATH", ""),
        os.path.expanduser("~/Library/Caches/ms-playwright"),
        os.path.expanduser("~/.cache/ms-playwright"),
        os.path.expanduser("~/AppData/Local/ms-playwright"),
    ]
    patterns = [
        "chromium_headless_shell-*/chrome-*/headless_shell",
        "chromium_headless_shell-*/chrome-*/headless_shell.exe",
        "chromium-*/chrome-*/chrome",
        "chromium-*/chrome-*/chrome.exe",
        "chromium-*/chrome-*/Chromium.app/Contents/MacOS/Chromium",
        "chromium-*/chrome-*/headless_shell",
    ]
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        for pat in patterns:
            hits = sorted(glob.glob(os.path.join(root, pat)), reverse=True)
            for h in hits:
                if os.path.exists(h):
                    return h
    return None


def _launch_browser(p, args: list[str]):
    launch_kwargs = {"headless": True, "args": args}
    try:
        return p.chromium.launch(**launch_kwargs)
    except Exception:
        exe = _find_cached_chromium()
        if not exe:
            raise
        return p.chromium.launch(executable_path=exe, **launch_kwargs)


def _wait_for(page, expr: str, timeout_s: float, errors: list[str]):
    deadline = time.time() + timeout_s
    state = None
    while time.time() < deadline:
        state = page.evaluate(expr)
        if state and (state.get("ready") or state.get("error")):
            return state
        time.sleep(0.2)
    # never initialized — treat as a GL init failure so `auto` can fall back to software
    raise _GLInitError(f"page never initialized the capture contract (pageerrors: {errors[:3]})")


def _clear_dir(path: str) -> None:
    for f in glob.glob(os.path.join(path, "*")):
        try:
            os.remove(f)
        except OSError:
            pass


def _capture_with_fallback(gl: str, inner):
    """Run `inner(p, args)` under each GL mode in order, falling back on _GLInitError. Returns
    (label, result)."""
    try:
        from playwright.sync_api import sync_playwright  # noqa: PLC0415
    except ModuleNotFoundError as exc:
        raise _dependency_unavailable("missing Python dependency: playwright") from exc

    attempts = _gl_attempts(gl)
    last: Exception | None = None
    with sync_playwright() as p:
        for label, args in attempts:
            try:
                return label, inner(p, args)
            except _GLInitError as e:
                last = e
                continue
    raise RuntimeError(f"WebGL failed to initialize under GL mode(s) {[a[0] for a in attempts]}: {last}")


def _capture_frames(url: str, width: int, height: int, timeout_s: float, frames_dir: str, gl: str) -> tuple[str, int]:
    """frames mode: render + read back each frame as a PNG. Returns (gl_label, frame_count)."""

    def inner(p, args) -> int:
        _clear_dir(frames_dir)  # clean between attempts so a fallback doesn't mix partial frames
        browser = _launch_browser(p, args)
        try:
            page = browser.new_context(viewport={"width": width, "height": height}).new_page()
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(url, wait_until="load")
            info = _wait_for(
                page,
                "() => window.__frame ? {ready: !!window.__frame.ready, error: window.__frame.error, total: window.__frame.total} "
                ": (window.__cap && window.__cap.error ? {ready:false, error: window.__cap.error} : null)",
                timeout_s,
                errors,
            )
            if info.get("error"):
                raise _GLInitError(str(info["error"]))  # WebGL/render error → let `auto` try software
            total = int(info.get("total") or 0)
            if total <= 0:
                raise RuntimeError("page reported zero frames to grab")
            for i in range(total):
                data_url = page.evaluate("(i) => window.__frame.grab(i)", i)
                if not data_url or "," not in data_url:
                    raise RuntimeError(f"frame {i} produced no image data")
                with open(os.path.join(frames_dir, f"f_{i:05d}.png"), "wb") as fh:
                    fh.write(base64.b64decode(data_url.split(",", 1)[1]))
            return total
        finally:
            browser.close()

    return _capture_with_fallback(gl, inner)


def _capture_stream_b64(url: str, width: int, height: int, timeout_s: float, gl: str) -> tuple[str, dict]:
    """stream mode: read the MediaRecorder-encoded webm off window.__cap. Returns (gl_label, payload)."""

    def inner(p, args) -> dict:
        browser = _launch_browser(p, args)
        try:
            page = browser.new_context(viewport={"width": width, "height": height}).new_page()
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(url, wait_until="load")
            cap = _wait_for(
                page,
                "() => window.__cap ? {ready: !!window.__cap.ready, error: window.__cap.error, frames: window.__cap.frames||0} : null",
                timeout_s,
                errors,
            )
            if cap.get("error"):
                raise _GLInitError(str(cap["error"]))
            return page.evaluate("() => ({b64: window.__cap.b64, mime: window.__cap.mime, frames: window.__cap.frames})")
        finally:
            browser.close()

    return _capture_with_fallback(gl, inner)


def _encode_from_frames(frames_dir: str, mp4_path: str, fps: int) -> None:
    ff = _resolve_ffmpeg_exe()
    cmd = [
        ff, "-y",
        "-framerate", str(fps),
        "-i", os.path.join(frames_dir, "f_%05d.png"),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-profile:v", "high", "-crf", "18",
        "-movflags", "+faststart",
        mp4_path,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True)
    except (FileNotFoundError, PermissionError) as exc:
        raise _dependency_unavailable(f"ffmpeg executable unavailable: {exc}") from exc
    if r.returncode != 0 or not os.path.exists(mp4_path):
        raise RuntimeError(f"ffmpeg encode-from-frames failed: {r.stderr[-600:]}")


def _transcode_to_mp4(webm_path: str, mp4_path: str, fps: int) -> None:
    ff = _resolve_ffmpeg_exe()
    cmd = [
        ff, "-y", "-i", webm_path,
        "-r", str(fps),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-profile:v", "high", "-crf", "18",
        "-movflags", "+faststart",
        mp4_path,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True)
    except (FileNotFoundError, PermissionError) as exc:
        raise _dependency_unavailable(f"ffmpeg executable unavailable: {exc}") from exc
    if r.returncode != 0 or not os.path.exists(mp4_path):
        raise RuntimeError(f"ffmpeg transcode failed: {r.stderr[-600:]}")


def main() -> int:
    ap = _JsonArgumentParser(description="Record a deterministic Three.js grey-box shot to mp4.")
    ap.add_argument("--dir", required=True, help="build directory containing index.html")
    ap.add_argument("--out", required=True, help="output mp4 path")
    ap.add_argument("--mode", choices=["frames", "stream"], default="frames",
                    help="frames = per-frame PNG grab (default, robust); stream = MediaRecorder")
    ap.add_argument("--gl", choices=["auto", "hardware", "software"], default="auto",
                    help="auto = GPU first then SwiftShader fallback (default); hardware = GPU only; software = SwiftShader only")
    ap.add_argument("--fps", type=int, default=24)  # Seedance renders at 24fps; match it for clean alignment
    ap.add_argument("--seconds", type=float, default=8.0)
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--port", type=int, default=0, help="0 = auto-pick a free port")
    ap.add_argument("--keep-webm", action="store_true")
    ap.add_argument("--no-frame0", action="store_true", help="skip emitting frame0.png (the combined-reference source still)")
    try:
        args = ap.parse_args()
        _validate_args(args)
        _preflight_dependencies()
    except _RecordingError as exc:
        _json_error(exc.code, str(exc), retryable=exc.retryable, exit_code=exc.exit_code)
        return exc.exit_code

    build_dir = os.path.abspath(args.dir)
    out_mp4 = os.path.abspath(args.out)
    Path(os.path.dirname(out_mp4) or ".").mkdir(parents=True, exist_ok=True)

    port = args.port or _free_port()
    httpd = None
    try:
        httpd = _serve(build_dir, port)
    except Exception as exc:  # noqa: BLE001
        err = _retryable_failure(f"failed to start local preview server: {exc}", code="server_start_failed")
        _json_error(err.code, str(err), retryable=err.retryable, exit_code=err.exit_code)
        return err.exit_code
    url = (f"http://127.0.0.1:{port}/index.html?record=1&mode={args.mode}&fps={args.fps}"
           f"&seconds={args.seconds}&w={args.width}&h={args.height}")
    timeout_s = args.seconds * 4 + 45  # generous: capture + encode headroom

    frames_dir = None
    try:
        if args.mode == "frames":
            frames_dir = tempfile.mkdtemp(prefix="gbx_frames_", dir=build_dir)
            gl_used, frame_count = _capture_frames(url, args.width, args.height, timeout_s, frames_dir, args.gl)
            _encode_from_frames(frames_dir, out_mp4, args.fps)
            frame0_src = os.path.join(frames_dir, "f_00000.png")
        else:
            gl_used, payload = _capture_stream_b64(url, args.width, args.height, timeout_s, args.gl)
            if not payload or not payload.get("b64"):
                raise _retryable_failure("page produced no video data", code="empty_capture")
            data = base64.b64decode(payload["b64"])
            with tempfile.NamedTemporaryFile(suffix=".webm", delete=False, dir=build_dir) as tf:
                tf.write(data)
                webm_path = tf.name
            _transcode_to_mp4(webm_path, out_mp4, args.fps)
            if not args.keep_webm:
                try:
                    os.remove(webm_path)
                except OSError:
                    pass
            frame_count = payload.get("frames")
            frame0_src = None

        frame0_path = None
        if not args.no_frame0:
            candidate = os.path.splitext(out_mp4)[0] + "_frame0.png"
            try:
                if frame0_src and os.path.exists(frame0_src):
                    shutil.copyfile(frame0_src, candidate)
                else:
                    ff = _resolve_ffmpeg_exe()
                    subprocess.run(
                        [ff, "-y", "-i", out_mp4, "-frames:v", "1", "-update", "1", candidate],
                        capture_output=True,
                        text=True,
                        check=True,
                    )
                frame0_path = candidate if os.path.exists(candidate) else None
            except Exception:  # noqa: BLE001 - frame0 is a convenience, never fail the record over it
                frame0_path = None

        duration_ms = int(round(args.seconds * 1000))
        video_sha256 = _sha256_file(out_mp4)
        _json_success({
            "mp4": out_mp4,
            "video_path": out_mp4,
            "frame0": frame0_path,
            "mode": args.mode,
            "gl": gl_used,
            "bytes": os.path.getsize(out_mp4),
            "fps": args.fps,
            "seconds": args.seconds,
            "duration_ms": duration_ms,
            "width": args.width,
            "height": args.height,
            "frames": frame_count,
            "sha256": video_sha256,
            "metadata": {
                "artifact_type": "greybox_video",
                "role": "v2v_input_candidate",
                "video_path": out_mp4,
                "duration_ms": duration_ms,
                "fps": args.fps,
                "sha256": video_sha256,
            },
        })
        return 0
    except _RecordingError as exc:
        _json_error(exc.code, str(exc), retryable=exc.retryable, exit_code=exc.exit_code)
        return exc.exit_code
    except Exception as exc:  # noqa: BLE001
        err = _retryable_failure(str(exc))
        _json_error(err.code, str(err), retryable=err.retryable, exit_code=err.exit_code)
        return err.exit_code
    finally:
        if httpd:
            httpd.shutdown()
        if frames_dir and not args.keep_webm:
            shutil.rmtree(frames_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
