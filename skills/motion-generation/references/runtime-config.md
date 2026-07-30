# Runtime Config

The script reads runtime configuration from environment variables.

## Required environment variables

| Variable | Purpose | Failure mode |
|---|---|---|
| `SYN_BASE_URL` | Fallback gateway base when `NEW_SYNC_GATE` is not set | `RuntimeError: missing required environment variables for runtime config: SYN_BASE_URL` |
| `APP_BASE_URL` | Asset / app base; retained for shared runtime consistency even though this script only calls the gateway path | Same `RuntimeError` if missing |
| `canvas_id` | Per-call canvas / project identifier | Same `RuntimeError` if missing or whitespace-only |
| `trace_id` | Per-call trace / observability identifier | Same `RuntimeError` if missing or whitespace-only |
| `s3_SecretId` | AWS key for private to public S3 copy; only required when the backend response contains private-bucket URLs | `RuntimeError: missing required environment variables for public url conversion: ...` |
| `s3_SecretKey` | AWS secret for the same path | Same |

`SYN_BASE_URL` / `APP_BASE_URL` / `canvas_id` / `trace_id` are checked at the start of every call. `s3_SecretId` / `s3_SecretKey` are checked lazily when private S3 URLs need to be made public.

## Optional environment variables

| Variable | Effect |
|---|---|
| `NEW_SYNC_GATE` | Preferred gateway base URL. When set, it takes precedence over `SYN_BASE_URL`. For test, use `https://your-approved-gateway.example`. |
| `MOTION_VIDEO_CAPTURE_GPU_IDS` | Comma-separated GPU id pool used as fallback for video-to-motion (default `0,1,2,3,4,5,6,7`). |
| `X_AUTH` / `AUTH_TOKEN` / `KOKO_AUTH_TOKEN` / `KOKO_AUTH` | Forwarded as `x-auth` header when present (first non-empty wins). `KOKO_AUTH` is JSON-decoded to extract `authToken`. |
| `COOKIE` / `Cookie` | Forwarded as `Cookie` header when present. If absent but `KOKO_AUTH` is set, a `KOKO_AUTH=<value>` cookie is constructed automatically. |
| `X_CHANNEL`, `X_CLIENT`, `X_VERSION`, `REQUEST_ID`, `REFERER`, `USER_AGENT` | Pass-through headers (`x-channel`, `x-client`, `x-version`, `request_id`, `referer`, `user-agent`) when present. |

## Gateway base URL resolution

```
NEW_SYNC_GATE, if non-empty  -> use directly (trailing slash stripped)
otherwise                    -> SYN_BASE_URL (trailing slash stripped)
```

This matches the image-generation gateway selection rule: prefer `NEW_SYNC_GATE`; otherwise fall back to `SYN_BASE_URL`.

For the test cluster:

```bash
NEW_SYNC_GATE=https://your-approved-gateway.example
```

## Token

Configure the service token through the environment:

```python
TOKEN = os.environ["MOTION_SERVICE_TOKEN"]
```

Sent as the `token` header on every request. Do not commit this value; provide it through your deployment secret manager.

## Headers

| Header | Value |
|---|---|
| `token` | value from `MOTION_SERVICE_TOKEN` |
| `Content-Type` | `application/json` |
| `x-canvas-id` | `canvas_id` from runtime config |
| `x-seele-canvas-trace-id` | `trace_id` from runtime config |
| `x-auth` | extracted from `X_AUTH` / `AUTH_TOKEN` / `KOKO_AUTH_TOKEN` / parsed `KOKO_AUTH` (only when present) |
| `Cookie` | from `COOKIE` / `Cookie` or built from `KOKO_AUTH` (only when present) |
| pass-through | `x-channel`, `x-client`, `x-version`, `request_id`, `referer`, `user-agent` from matching env vars |

## Timeout

900 seconds per HTTP call. Long because video-to-motion is a heavy backend job (decode to tracking to retarget to encode FBX); text-to-motion typically returns much faster but shares the same timeout.

## Empty-result retry

`MAX_EMPTY_RESULT_RETRIES = 2` means up to 3 total attempts. A retry is triggered only when:

- HTTP transport succeeded (status in 2xx range)
- AND backend body did not surface a usable primary URL after URL collection

Network errors, HTTP non-2xx, validation failures, and S3 publicify errors all surface immediately. They are not retried. The retry repeats the same payload; there is no query rewriting at this layer.

`attempts` in the response carries the actual count.

## Private to Public S3 Conversion

The executor recursively walks the gateway response and, for any URL in the `seelemedia-private` bucket, copies the object to the public `seelemedia` bucket (`us-east-1`) and rewrites the URL to the public CDN host `https://static.seeles.ai`. Already-public bucket URLs are normalized to the same CDN host; other hosts are passed through unchanged.

Requires `s3_SecretId` / `s3_SecretKey`; missing creds at this stage fail the call with `success: false`. `boto3` is imported lazily, so installations that never trigger private to public conversion do not need it on the path.
