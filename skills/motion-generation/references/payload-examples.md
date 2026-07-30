# Payload Examples

Each example is a complete `--input-file` JSON payload.

## Text-to-motion

```json
{
  "prompt": "a smooth looping walk cycle with relaxed arms"
}
```

Describe action type, loop / non-loop intent, body attitude, and force / timing / rhythm in the prompt for best results.
The text path calls the Nerv MQ gateway task `text2motion-atom/create_motion_new`. The executor maps `prompt`
to backend `text_prompt` and auto-generates `task_id` when omitted.

## Text-to-motion with explicit GPU pin

```json
{
  "prompt": "idle stance, slightly shifting weight, gentle breathing",
  "cuda_visible_devices": "3"
}
```

Useful when the caller needs to pin a text-to-motion generation to a specific GPU; otherwise the backend/runtime
may supply its own GPU context.

## Video-to-motion (motion capture from video)

```json
{
  "video_url": "https://example.com/source-action.mp4"
}
```

`video_url` must be an `http(s)://` URL pointing to a source action video the backend can fetch. The backend tracks the actor in the video and retargets the motion onto a humanoid rig, returning an FBX clip plus camera tracks.

## Video-to-motion with explicit GPU pin

```json
{
  "video_url": "https://example.com/source-action.mp4",
  "cuda_visible_devices": "3"
}
```

Useful when the caller needs to pin to a specific GPU; otherwise the script picks one at random from `MOTION_VIDEO_CAPTURE_GPU_IDS` or the default pool.

## Video-to-motion with MQ task options

```json
{
  "video_url": "https://example.com/source-action.mp4",
  "run_mode": "fast",
  "need_camera": true,
  "callback_url": "https://example.com/callback"
}
```

The video path calls the Nerv MQ gateway task `create_video_motion`. The executor maps `video_url` to backend
`input_video_url`, auto-generates `task_id` when omitted, and forwards supported task options when provided.

## With explicit task id

```json
{
  "prompt": "idle stance, slightly shifting weight, gentle breathing",
  "task_id": "user-supplied-id-123"
}
```

When omitted, the executor generates a UUID. The `task_id` is forwarded to the backend and echoed in the response — useful for cross-system tracing.

## Invalid: both fields

```json
{
  "prompt": "walk",
  "video_url": "https://..."
}
```

→ `{ "success": false, "message": "exactly one of prompt or video_url must be provided" }`

## Invalid: neither field

```json
{}
```

→ Same error.

## Field rules summary

| Field | Type | Required | Notes |
|---|---|---|---|
| `prompt` | non-empty string | xor with `video_url` | text-to-motion MQ task |
| `video_url` | non-empty `http(s)://` URL | xor with `prompt` | video-to-motion path |
| `task_id` | non-empty string | optional | UUID auto-generated when missing |
| `cuda_visible_devices` / `CUDA_VISIBLE_DEVICES` | non-empty string | optional | forwarded on text-to-motion when provided; video-to-motion uses it or picks from configured pool |
| `callback_url` / `call_back_url` | non-empty string | optional | forwarded to MQ task when supported |
| `need_camera` | boolean | optional | video-to-motion only |
| `run_mode` | `normal` or `fast` | optional | video-to-motion only |
