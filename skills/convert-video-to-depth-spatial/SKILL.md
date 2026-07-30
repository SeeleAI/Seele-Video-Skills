---
name: convert-video-to-depth-spatial
description: Infer temporally consistent per-frame depth from an input VIDEO with Video Depth Anything-Small, producing a depth-map VIDEO and raw per-frame depth sequence. Route here only when the user explicitly asks for video depth estimation, 视频转深度图视频, or raw depth for every video frame. Exclude ordinary video trim/transcode/compress/format conversion, depth estimation from a still IMAGE, stereo/SBS/DIBR conversion, generative Seedance/depth-remix editing, and Apple spatial-video/MV-HEVC encoding; those are different or deferred capabilities.
---

# Convert Video to Depth Spatial

Convert exactly one uploaded/public video into a grayscale depth-map video with
`depth-anything/Video-Depth-Anything-Small`. This is a deterministic, GPU-only
inference workflow. It is not a general video editor and has no model or CPU
fallback.

## Hard contract

Always submit exactly:

```json
{
  "input_video": "https://static.seeles.ai/.../input.mp4",
  "task_id": "video-depth-<unique-id>",
  "mode": "depth",
  "model": "depth-anything/Video-Depth-Anything-Small",
  "raw_depth_format": "npz",
  "preserve_audio": true
}
```

Do not change `mode`, `model`, `raw_depth_format`, or `preserve_audio`. Do not
substitute another model, CPU execution, SBS, DIBR, MV-HEVC, Seedance, or a
local heuristic.

## Input attachment

The Canvas API sends uploaded files in `fileUrlList`; conversation history
exposes the same values as `fileList`. Use exactly one attached video URL.
The web client obtains that URL from `/api/v1/file/generateUploadUrl`, uploads
the bytes, then strips the query before `sendMessage`.

The runtime accepts only public HTTP(S) input on ports 80/443. A local path,
`file://`, private IP, or `s3://` URL is not usable. If the input is local and
has not already been uploaded, use `file-upload-to-cdn` first and pass its
public `https://static.seeles.ai/...` URL. Never invent an attachment path or
URL.

## Execute

The executor uses an approved video-depth gateway adapter. Do **not** put
private cluster service names in requests or committed configuration. Supply
the gateway URL, service token, request identifiers, and allowed hosts through
your deployment environment or secret manager.

PowerShell:

```powershell
$payload = @{
  input_video = "<the exact uploaded public video URL>"
  task_id = "video-depth-$([guid]::NewGuid().ToString('N'))"
  mode = "depth"
  model = "depth-anything/Video-Depth-Anything-Small"
  raw_depth_format = "npz"
  preserve_audio = $true
} | ConvertTo-Json -Depth 10
$env:VIDEO_DEPTH_INPUT = $payload
uv run python {{env_base_path}}/skills/convert-video-to-depth-spatial/scripts/depth_spatial_contract.py --input-env VIDEO_DEPTH_INPUT
```

The script exits nonzero on a non-2xx response, redirect, oversized response,
invalid JSON, `success=false`, missing artifact, non-CUDA receipt, fallback,
model substitution, or failed output validation. Treat any such result as a
hard failure. Never claim success from partial output.

The initial gateway request waits at most 540 seconds so the script can return
before the Agent tool's 600-second hard limit. If it returns
`error_type="ambiguous_timeout"`, do not run the original payload again. Poll
the already-submitted task with its exact `resume_gateway_task_id`:

```powershell
$resume = @{
  resume_gateway_task_id = "<exact ID returned by the first invocation>"
} | ConvertTo-Json
$env:VIDEO_DEPTH_INPUT = $resume
uv run python {{env_base_path}}/skills/convert-video-to-depth-spatial/scripts/depth_spatial_contract.py --input-env VIDEO_DEPTH_INPUT
```

Recovery is read-only. The executor first polls ImageGen's deterministic
completion record at
`video_depth/task_results/{resume_gateway_task_id}.json`; this survives a lost
gateway reply or gateway restart. It also queries `/syn-gateway/task/{task_id}`
as a compatibility fallback for tasks submitted before durable records were
deployed. It checks every 10 seconds for up to 480 seconds and never publishes
another MQ message. If it is still pending, run the same recovery payload again
with the same ID. Continue until it returns validated artifacts or an explicit
terminal failure. Never invent a new task ID or resubmit the source video after
an ambiguous timeout.

Direct `VIDEO_DEPTH_RUNTIME_URL` mode exists only for an approved same-cluster
TEST integration probe. It also requires `VIDEO_DEPTH_RUNTIME_ALLOWED_HOSTS`.
Do not set either variable in normal Agent execution.

## Required result

Return all six URLs and retain the receipt:

1. `depth.mp4` — grayscale depth video, same frame count/rate/duration;
2. `depth.npz` — raw per-frame depth;
3. `manifest.json`;
4. `metrics.json`;
5. `receipt.json`;
6. `execution.log`.

Before reporting success, verify the returned receipt says:

- `status=succeeded` and `classification=success`;
- exact model `depth-anything/Video-Depth-Anything-Small`;
- a non-empty CUDA/GPU device;
- `fallback_used=false`;
- `output_validation.passed=true`.

Present the top-level `url` (`depth.mp4`) as the primary result and include the
raw depth and receipt links from `artifacts`. Read `references/contract.md` for
transport, security, and failure details.


## Seele Workspace case preview

![Depth-Guided Motion Transfer case cover](../../assets/cases/depth-guided-motion-transfer.webp)

[Open Film & CG in Seele Workspace](https://www.seeles.ai/workspace?category=film-cg)
