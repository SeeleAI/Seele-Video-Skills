# Response Shape

## Success (text-to-motion)

```json
{
  "success": true,
  "status": 200,
  "mode": "text_to_motion",
  "url": "https://static.seeles.ai/.../motion.fbx",
  "urls": {
    "fbx": "https://.../motion.fbx",
    "fbx_url": "https://.../motion.fbx",
    "mp4": "https://.../preview.mp4",
    "mp4_url": "https://.../preview.mp4",
    "png": "https://.../thumb.png",
    "png_url": "https://.../thumb.png"
  },
  "data": { ... raw backend response, with S3 URLs publicified ... },
  "attempts": 1,
  "message": "ok"
}
```

`mode` is `text_to_motion` or `video_to_motion`.

## Success (video-to-motion)

`urls` may additionally include:

| Key | Meaning |
|---|---|
| `fbx` / `fbx_url` | Retargeted motion clip (primary deliverable) |
| `camera_url` | Camera animation track |
| `camera_rootmotion_url` | Camera + root-motion combined track |
| `camera_info_url` | Camera metadata JSON |
| `mp4` / `mp4_url` | Preview video |
| `png` / `png_url` | Preview thumbnail |

All collected URLs are kept in the `urls` dictionary so the caller can pick whichever asset they need.

## Primary URL selection

`url` is picked from `urls` in this order — first non-empty wins:

```
fbx_url -> fbx -> motion_url -> camera_rootmotion_url -> camera_url -> url -> mp4_url -> mp4 -> png_url -> png
```

When no key matches, the script falls back to a generic recursive URL scan (`pick_url`). If nothing usable surfaces and HTTP was 2xx, the empty-result retry kicks in (see `runtime-config.md`).

## Failure modes

| Trigger | `success` | `status` | `url` | `message` (representative) |
|---|---|---|---|---|
| Both / neither of `prompt`, `video_url` | `false` | `null` | `""` | `"exactly one of prompt or video_url must be provided"` |
| Missing required env vars | `false` | `null` | `""` | `"missing required environment variables for runtime config: SYN_BASE_URL, ..."` |
| Missing `canvas_id` / `trace_id` after env load | `false` | `null` | `""` | `"missing required input fields: canvas_id, trace_id"` |
| Network / transport error | `false` | `null` | `""` | `"request failed: ..."` |
| Private S3 URL but no `s3_SecretId` / `s3_SecretKey` | `false` | `<status>` | `""` | `"missing required environment variables for public url conversion: ..."` |
| HTTP non-2xx | `false` | `<status>` | `""` | `"HTTP <status>"` |
| HTTP 200 but no URL after retries | `false` | `200` | `""` | `"HTTP 200: backend returned no final motion url (<backend message>)"` |

## Empty-result retry

When transport succeeds (2xx) but no primary URL surfaces, the script retries up to `MAX_EMPTY_RESULT_RETRIES = 2` more times (3 total). `attempts` reflects the actual count. Payload is unchanged across retries — there is no query rewriting at this layer.

If retries are exhausted, the last attempt's data, status, and backend message are returned with `success: false`.

## `data` field

Carries the full raw backend response after S3 publicification. Callers usually do not need to inspect it — `url` + `urls` are the contract. It is exposed for debugging and for callers that want fields outside the URL collection (e.g. backend-side task IDs, durations, frame counts).
