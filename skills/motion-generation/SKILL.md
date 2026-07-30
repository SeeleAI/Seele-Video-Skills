---
name: motion-generation
description: "Generate character motions and animations through the Seele motion generation gateway, returning a primary FBX URL plus all detected motion artifact URLs (fbx / mp4 preview / png thumb / camera tracks for video mode). Supports text-to-motion (describe the action in prose) and video-to-motion / video motion capture (mocap from a source action video the backend tracks and retargets). Use as the generation executor invoked by higher-level game / scene skills (threejs-game, unity-game, unreal-game-builder, unreal-scene-builder, promo-video-generator) when retrieval returned no usable result, or directly when the user explicitly asks to generate a new motion clip. Trigger on English or Chinese phrasings: generate / create / produce / make / synthesize / animate + motion / animation / animation clip / mocap / walk cycle / idle / attack / dance / 生成 / 创建 / 制作 / 做一个 / 合成 / 文生 / 视频生 + 动作 / 动画 / 动作片段 / mocap / 动捕 / 走路循环 / 待机 / 攻击 / 舞蹈; plus text-to-motion / video-to-motion / motion capture / video motion capture / 文生动作 / 视频转动作 / 视频生动作 / 视频动捕 / 动捕 / 动捕生成. Trigger especially when the user supplies a source action video URL and asks for a motion / animation derived from it, or names the two operation families (text-to-motion, video-to-motion). Skip for: retrieving an existing motion clip from the asset library (use asset-retrieval — categories basic_motion / loop_motion / non_loop_motion / dance_motion), generating a character mesh / avatar / 3D model (use model-generation), rigging or skinning a mesh (use bind-bone-skinning), generating a 2D image / video / sprite sheet (use ai-model-calling)."
---

# Motion Generation Executor

Generate a motion / animation clip via the bundled Python script and return
a primary FBX URL plus the full per-artifact URL dictionary.

## Script

```bash
uv run python {{env_base_path}}/skills/motion-generation/scripts/motion_skill.py --input-file tmp/skill-payloads/motion-generation.json
```

The script reads JSON from `--input-file`, routes to the text-to-motion or
video-to-motion Nerv MQ gateway task based on payload shape, publicifies any
private S3 URLs in the response, and prints the result JSON to stdout.

Create throwaway payload JSON under `tmp/skill-payloads/` in the active
workspace/cwd. Do not write one-off payload files in the workspace root.

## Payload shape

```json
{
  "prompt": "<action description, for text-to-motion>",
  "video_url": "<http(s):// source action video, for video-to-motion>",
  "task_id": "<optional; UUID auto-generated when omitted>",
  "cuda_visible_devices": "<optional>",
  "CUDA_VISIBLE_DEVICES": "<optional>",
  "callback_url": "<optional>",
  "call_back_url": "<optional>",
  "need_camera": "<optional boolean; video-to-motion only>",
  "run_mode": "<optional normal|fast; video-to-motion only>"
}
```

## Field rules quick reference

- `prompt` xor `video_url`: provide **exactly one**. Both or neither fails validation before any HTTP call.
- `prompt`: non-empty string. Describe action type, loop / non-loop intent, body attitude, force / timing / rhythm.
- `video_url`: non-empty `http(s)://` URL the backend can fetch. Used for motion-capture-from-video.
- `task_id`: optional. UUID auto-generated when missing; forwarded to the backend and echoed back.
- `cuda_visible_devices` / `CUDA_VISIBLE_DEVICES`: optional. Text-to-motion forwards an explicit value when provided. Video-to-motion uses it when provided, otherwise falls back to a random pick from `MOTION_VIDEO_CAPTURE_GPU_IDS` env (or `0-7` if unset).
- `callback_url` / `call_back_url`: optional. Forwarded to the Nerv MQ task when provided.
- `need_camera`: optional boolean. Video-to-motion only; backend default is `true`.
- `run_mode`: optional. Video-to-motion only; backend accepts `normal` or `fast`.

## Runtime requirements

Set via environment (script reads env directly):

- `NEW_SYNC_GATE` - preferred gateway base URL when set; for test use `https://your-approved-gateway.example`
- `SYN_BASE_URL` - fallback gateway base URL when `NEW_SYNC_GATE` is not set
- `APP_BASE_URL` - retained for shared runtime consistency
- `canvas_id`, `trace_id` - required; the script aborts if missing
- `s3_SecretId`, `s3_SecretKey` - required for private-to-public S3 URL conversion (checked lazily when private bucket URLs appear in the response)

See `references/runtime-config.md` for gateway base URL priority, headers,
auth pass-through, timeout, retry, and the S3 publicification path.

## Response shape

Success:

```json
{
  "success": true,
  "status": 200,
  "mode": "text_to_motion",
  "url": "https://.../motion.fbx",
  "urls": {
    "fbx": "...",
    "fbx_url": "...",
    "mp4": "...",
    "mp4_url": "...",
    "png": "...",
    "png_url": "..."
  },
  "data": { ... raw backend response (S3 URLs publicified) ... },
  "attempts": 1,
  "message": "ok"
}
```

Failure: `success: false`, `url` empty, `message` carries the diagnostic.

Primary `url` selection order: `fbx_url -> fbx -> motion_url -> camera_rootmotion_url -> camera_url -> url -> mp4_url -> mp4 -> png_url -> png`.
Video mode additionally surfaces `camera_url / camera_rootmotion_url / camera_info_url`
in `urls`. Full schema and failure modes in `references/response-shape.md`.

## Hard rules

1. Provide exactly one of `prompt` or `video_url`; both-or-neither fails validation before any HTTP call.
2. The primary `url` is the contract — return only after confirming `success: true` AND a non-empty `url`. The full `urls` dictionary is available for callers needing alternates (camera tracks, preview mp4, thumbnail).
3. This executor never performs retrieval. If the caller wants to prefer existing motion clips, they invoke `asset-retrieval` first (categories `basic_motion` / `loop_motion` / `non_loop_motion` / `dance_motion`) and only fall back here on empty results — that policy belongs to the upstream caller, not this executor.

## Reference index

| File | Read when |
|---|---|
| `references/backend-routes.md` | Looking up MQ gateway task paths, request body fields, and the GPU-id resolution order for video-to-motion. |
| `references/payload-examples.md` | Building a text-to-motion or video-to-motion payload, GPU pin usage, validation edge cases. |
| `references/runtime-config.md` | Env vars (required + optional), gateway base URL priority (`NEW_SYNC_GATE` then `SYN_BASE_URL`), headers, auth pass-through, S3 publicification, HTTP timeout, empty-result retry. |
| `references/response-shape.md` | Inspecting the full response, video-mode camera tracks, URL selection priority, failure modes. |


## Seele Workspace case preview

![Motion Generation case cover](../../assets/cases/motion-generation.jpg)

[Open Film & CG in Seele Workspace](https://www.seeles.ai/workspace?category=film-cg)
