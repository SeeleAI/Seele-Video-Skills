# Recording the grey-box shot to mp4

The recorded clip is one of the two things that decide the result, so capture it cleanly.

## How it works

The template renders ITSELF deterministically: opened with `?record=1`, `main.js` advances the
shot clock by exactly `1/fps` per step and renders each frame — so the clip is smooth and
reproducible regardless of machine speed. There are two capture paths (`--mode`):

- **`frames` (DEFAULT).** The page exposes `window.__frame.grab(i)` — it renders frame `i` and
  returns it as a PNG data URL. `scripts/record_greybox.py` pulls each frame, saves the PNGs, and
  ffmpeg assembles the **H.264 mp4**. This is **robust on headless, GPU-less servers** (software
  WebGL / SwiftShader), where `MediaRecorder` + `captureStream` are unreliable.
- **`stream` (opt-in, `--mode stream`).** The page records itself with `MediaRecorder` and exposes
  the encoded webm on `window.__cap`; the driver transcodes it to mp4. Only use where MediaRecorder
  is known to work.

**GPU-aware, no config needed (`--gl`, default `auto`).** The driver **tries the GPU first**
(`--use-gl=angle --ignore-gpu-blocklist`) and, if the page can't create a WebGL context (e.g. a
GPU-less server), **automatically relaunches with software WebGL / SwiftShader**
(`--use-gl=angle --use-angle=swiftshader --enable-unsafe-swiftshader …`). So the same build is fast
on a GPU box (production) and still works on a GPU-less sandbox (test) — the output JSON's `gl` field
reports which backend actually ran. Force it with `--gl hardware` / `--gl software` if needed. If WebGL
can't init under any mode, `main.js` publishes a clear error on `window.__frame`/`window.__cap` and the
driver fails fast with that message instead of hanging.

## Command

```bash
uv run --with playwright --with imageio-ffmpeg \
  python {{env_base_path}}/skills/greybox-cg-v2v/scripts/record_greybox.py \
  --dir <build_dir_with_index.html> \
  --out <out.mp4> \
  --fps 24 --seconds 8 --width 1280 --height 720
```

Success output is a JSON line. It keeps the legacy `mp4` and `seconds` fields and also emits
machine-readable metadata for the manifest:

```json
{
  "success": true,
  "mp4": "/abs/out.mp4",
  "video_path": "/abs/out.mp4",
  "duration_ms": 8000,
  "fps": 24,
  "sha256": "sha256:...",
  "frame0": "/abs/out_frame0.png",
  "mode": "frames",
  "bytes": 123456,
  "frames": 192
}
```

It also emits **`frame0`** — the first frame as a PNG, ready to restyle into the look/character
reference image (`image_url`, the 组合参考 path — see "Producing the look/character reference still"
in `v2v-call.md`). Pass `--no-frame0` to skip. Add `--mode stream` only if you specifically want the
MediaRecorder path (default is the robust `frames` path).

Failure output is also structured JSON:

```json
{
  "success": false,
  "retryable": true,
  "error_code": "recording_failed",
  "message": "browser crashed",
  "error": { "code": "recording_failed", "retryable": true, "exit_code": 3 }
}
```

Stable exit codes:

- `2`: non-retryable invalid input, such as missing required CLI args, invalid option choices,
  missing `index.html`, or invalid dimensions. `--help` keeps normal argparse help semantics.
- `3`: retryable capture/encode/server startup failure.
- `4`: non-retryable deterministic runtime dependency/environment failure, such as missing
  `playwright` / `imageio_ffmpeg`, or an unavailable/non-executable ffmpeg binary.

The recorder does not perform blind infinite retries. Callers should use `retryable` and the manifest
state to decide whether to retry, ask for a new revision, or reconcile manually.

After recording, write or update the revision manifest with `scripts/greybox_manifest.py`. The greybox
video artifact must include `artifact_type=greybox_video`, `role=v2v_input_candidate`, the local `path`,
the public CDN `url` when available, `duration_ms`, `fps`, and `sha256` of the exact local mp4. The final
V2V wrapper later recomputes this hash and refuses to call downstream if the path or contents changed.

### Settings that matter

- **`--fps 24`** — Seedance renders at 24fps; match it so motion aligns cleanly. (Default is 24.)
- **`--seconds` ≤ 10** — the v2v limit; 5–8s is the sweet spot (longer = more drift/flicker).
- **`--width`/`--height`** — pick the aspect you'll pass to v2v as `ratio`. 1280×720 (16:9) is a good
  default; 720×1280 for 9:16. 720p input is plenty — v2v repaints all the detail.

## Always inspect before spending a v2v call

A v2v generation costs money and minutes. Before calling it, extract a couple of frames and look:

```bash
# reuse the ffmpeg imageio-ffmpeg fetched:
FF=$(uv run --with imageio-ffmpeg python -c "import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())")
"$FF" -y -ss 0.0 -i out.mp4 -frames:v 1 frame0.png      # (the recorder already emits <mp4>_frame0.png — restyle it into the image_url look reference)
"$FF" -y -ss 3.0 -i out.mp4 -frames:v 1 mid.png
```

Confirm: the **subject silhouette reads clearly**, the **camera move is smooth and is the move you
intended**, and **sky/ground/subject are distinct values**. If not, fix `shot.js` and re-record —
v2v preserves these, so it cannot fix them later.

## Runtime / dependencies

Proven path: headless Chromium (Playwright) + `imageio-ffmpeg`'s bundled ffmpeg (it has libx264;
Playwright's own ffmpeg does NOT, so don't use it for mp4). Both are pulled on demand by
`uv run --with …`, so no repo dependency is added.

Pre-install these in the runtime to avoid per-run downloads (see "If recording is slow" below);
`_find_cached_chromium()` picks up a `PLAYWRIGHT_BROWSERS_PATH` / standard-cache Chromium automatically.

If a runtime has no Playwright / can't fetch packages, the page is the same in any browser and the
driver is swappable (the render logic lives in the page): open it with `?record=1`, then either loop
`window.__frame.grab(i)` for `i` in `0..__frame.total-1` (save each PNG, ffmpeg-assemble) — the default
`frames` contract — or, with `&mode=stream`, read `window.__cap.b64` once ready and transcode the webm.
Any ffmpeg with libx264 works (`imageio-ffmpeg`'s bundled one has it; Playwright's own ffmpeg does NOT).

## If recording is slow (esp. online / in the sandbox)

Three costs dominate, in order of impact:

1. **Dependency download per run — usually the biggest.** `uv run --with playwright --with
   imageio-ffmpeg` fetches, on a cold/ephemeral env, Playwright's **Chromium (~150MB)** and
   `imageio-ffmpeg`'s ffmpeg binary — every run. Fix: **pre-install these in the service runtime**
   (bake `playwright` + its Chromium and `imageio-ffmpeg` into the image, or point
   `PLAYWRIGHT_BROWSERS_PATH` at a persistent cache) so the command reuses them instead of
   re-downloading. The script already probes a cached Chromium via `_find_cached_chromium()`
   (checks `PLAYWRIGHT_BROWSERS_PATH` and the standard caches), so a warm cache is used automatically.
   Per this repo's AGENT.md, skill commands should rely on deps already present in the service env.
2. **Rendering.** With a GPU (`--gl auto` picks hardware), rendering is fast. On a GPU-less box it
   falls back to **SwiftShader** (software WebGL), where the shadow pass and MSAA cost the most — and
   v2v repaints all of it, so the template keeps rendering cheap regardless: **antialias off**, a
   **512² shadow map**, plain (not soft) shadow filtering. If software rendering is still slow, drop
   capture size (e.g. `--width 960 --height 540` — v2v upsamples/repaints detail anyway).
3. **Per-frame readback (frames mode).** The `frames` path does one CDP round-trip + PNG readback per
   frame, so it scales with frame count; shorten the shot (`--seconds 5`) or lower resolution to cut it.
   (The old `stream` path additionally sleeps `~1000/fps` per frame, making capture ≥ real-time — another
   reason `frames` is the default.)

None of items 2–3 hurt the v2v result (the grey-box only needs to be *legible*, not pretty). Item 1
is the real lever online and is an infra/runtime change, not a prompt change.
