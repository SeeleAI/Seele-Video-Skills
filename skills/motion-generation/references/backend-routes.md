# Backend Routes

The executor calls one of two Nerv MQ gateway tasks depending on payload shape.

## Text-to-motion

```
POST  {GATEWAY_BASE_URL}/gateway/mq
        ?abs_cuda_proxy_service_name=text2motion-atom
        &abs_cuda_proxy_func_name=create_motion_new
```

Request body:

```json
{
  "task_id": "<uuid>",
  "text_prompt": "<prompt>",
  "CUDA_VISIBLE_DEVICES": "<optional gpu-id>",
  "callback_url": "<optional callback url>",
  "call_back_url": "<optional callback url>"
}
```

Triggered when the payload carries a non-empty `prompt` and no `video_url`.
The executor maps `prompt` to backend `text_prompt`, auto-generates `task_id` when omitted, and forwards
`CUDA_VISIBLE_DEVICES` plus callback fields when provided.

## Video-to-motion (motion capture from video)

```
POST  {GATEWAY_BASE_URL}/gateway/mq
        ?abs_cuda_proxy_service_name=motion-video-capture-atom
        &abs_cuda_proxy_func_name=create_video_motion
```

Request body:

```json
{
  "task_id": "<uuid>",
  "input_video_url": "<video_url>",
  "CUDA_VISIBLE_DEVICES": "<gpu-id>",
  "callback_url": "<optional callback url>",
  "call_back_url": "<optional callback url>",
  "need_camera": true,
  "run_mode": "normal"
}
```

Triggered when the payload carries a non-empty `video_url` and no `prompt`.

`task_id` is generated when omitted and sent in the body. This matches the Nerv MQ task behavior described by
`model-rig`: gateway calls route to `/gateway/mq` with the task name in `abs_cuda_proxy_func_name`, while task
inputs remain in the JSON body. Both text-to-motion and video-to-motion now use this MQ route shape.

`input_video_url` is required by the motion-video-capture task and is derived from payload `video_url`.

`CUDA_VISIBLE_DEVICES` is accepted by the backend and sent by the script for deterministic GPU selection. The script
resolves it in this order:

1. payload `CUDA_VISIBLE_DEVICES`, if non-empty
2. payload `cuda_visible_devices`, if non-empty
3. random pick from env `MOTION_VIDEO_CAPTURE_GPU_IDS` (comma-separated)
4. random pick from default pool `0,1,2,3,4,5,6,7`

Optional fields supported by the backend and passed through when provided:

- `callback_url` / `call_back_url`
- `need_camera`
- `run_mode` (`normal` or `fast`)

For text-to-motion, `callback_url` / `call_back_url` and an explicit `CUDA_VISIBLE_DEVICES` are also forwarded when present.

## Shared request shape

- Method: `POST`
- Body: JSON (`Content-Type: application/json`)
- Headers: see `runtime-config.md`
- Timeout: 900 seconds per attempt

## Backend success detection

The script considers a response "backend-successful" when any of these is true on the top-level body or its nested `data`:

- `success: true`
- `code: 0`
- `error_code: 0`

Combined with HTTP 2xx and a non-empty primary URL, the executor reports `success: true`. Any single one of these failing flips the response to `success: false` (with empty-result retry triggered if HTTP was 2xx but URL was missing).
