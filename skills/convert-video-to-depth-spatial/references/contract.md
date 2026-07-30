# Video-depth runtime contract

## Scope

One public video URL goes to the isolated TEST `video_depth` task. The task
runs only `depth-anything/Video-Depth-Anything-Small`, emits grayscale depth,
preserves source audio when present, uploads six artifacts, and returns a
signed execution receipt.

## Request

| Field | Required value |
|---|---|
| `input_video` | one public HTTP(S) video URL, port 80/443 |
| `task_id` | non-empty unique string |
| `mode` | `depth` |
| `model` | `depth-anything/Video-Depth-Anything-Small` |
| `raw_depth_format` | `npz` |
| `preserve_audio` | `true` |

`video_url` is accepted only as an input alias. Canvas attachments may be
provided to the helper through `fileUrlList`, `fileList`, or their snake-case
forms; there must be exactly one unless the same URL is also named as
`input_video`.

The adapter copies `task_id` to the internal `client_task_id` field because
Nerv consumes the reserved MQ correlation field before invoking ImageGen.
ImageGen uses `client_task_id` only to key the deterministic completion record;
callers must not supply a different value.

Local paths are rejected. The Agent upload flow is:

1. `GET /api/v1/file/generateUploadUrl?fileName=<uuid>.mp4`;
2. `PUT` bytes to the returned upload URL;
3. send the returned `readUrl` in Canvas `fileUrlList`;
4. the Skill passes that public URL as `input_video`.

## Transport boundary

### Gateway execution

Public deployments must not resolve or connect to private cluster services.
The helper uses a deployment-supplied gateway adapter:

```text
POST <approved Agent gateway>/gateway/mq
  ?abs_cuda_proxy_service_name=imagegen
  &abs_cuda_proxy_func_name=video_depth
```

The deployment supplies gateway discovery, `canvas_id`, `trace_id`, and auth
headers. No runtime hostname or credential is stored in this Skill.

### Same-cluster TEST probe

For deployment verification only, set both:

```text
VIDEO_DEPTH_RUNTIME_URL=http://<approved-service>:8080/tasks/video_depth/execute
VIDEO_DEPTH_RUNTIME_ALLOWED_HOSTS=<exact-hostname>
```

The second variable is mandatory and prevents an overridden endpoint from
becoming arbitrary SSRF. Direct mode rejects credentials, query/fragment, and
any path except `/tasks/video_depth/execute`.

## Security and resource limits

- Input must be HTTP(S), have no credentials/fragment, and use port 80/443.
- Literal private/special IP input is rejected by the adapter. The imageGen
  downloader independently resolves DNS, rejects private/special destinations,
  pins the validated address, and revalidates every redirect.
- Adapter redirects are disabled for both direct runtime and gateway calls.
- Runtime response body is capped at 4 MiB.
- The initial Agent gateway wait is capped at 540 seconds, below the outer
  600-second tool limit. A gateway timeout is ambiguous, not a terminal model
  failure.
- After an ambiguous timeout, first query ImageGen's public, deterministic
  completion record at
  `video_depth/task_results/{task_id}.json`. A missing record is pending, while
  a completed success or failure is terminal. Query
  `GET {SYN_BASE_URL}/syn-gateway/task/{task_id}` only as a compatibility
  fallback for older tasks. Poll every 10 seconds for up to 480 seconds per
  recovery invocation, reuse the same task ID, and never republish MQ.
- Direct same-cluster probes default to 1250 seconds and can only be configured
  between 10 and 1800 seconds.
- Non-2xx, invalid JSON, `success=false`, missing receipt/artifacts, model
  mismatch, CPU/no-GPU receipt, fallback, or failed output validation is fatal.
- There is no CPU, alternate-model, local-runner, or degraded-output path.

## Response acceptance

The HTTP service may be returned directly or wrapped by the existing gateway.
The helper unwraps only `data`/`result` objects and requires a payload containing
both `artifacts` and `receipt`.

The artifact map must contain exactly:

- `depth.mp4`
- `depth.npz`
- `manifest.json`
- `metrics.json`
- `receipt.json`
- `execution.log`

Each value must be an HTTP(S) URL. The receipt must prove exact model identity,
GPU execution, `fallback_used=false`, classified success, and passed output
validation.

## Media acceptance

`metrics.json` must show identical input/depth frame counts. If the source has
audio, output audio is required. Reported A/V start-time drift must be at most
40 ms. `depth.mp4` is the primary user result; retain all other artifacts for
reproducibility and audit.
