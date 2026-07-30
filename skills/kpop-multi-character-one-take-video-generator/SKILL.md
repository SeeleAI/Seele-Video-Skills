---
name: kpop-multi-character-one-take-video-generator
description: "Generate a finished K-pop multi-character one-take reveal video from 2-4 ordered unique reference images and an optional scene. Use for K-pop group one-take, single-take, one-shot, continuous-camera choreography, or multi-character idol reveal requests that require an actual 8-second 16:9 video. The Skill uploads local references, compiles and validates a gapless uninterrupted-take prompt internally, delegates model routing, billing, provider execution, task waiting, and final URL publicification to the production video executor, and returns a generated video URL with task status. Do not use for prompt-only requests, multi-shot montages, vlogs, gameplay capture, or edited storyboards."
---

# K-POP Multi-Character One-Take Video Generator

Generate the video end to end. Never stop after writing or validating a prompt.

## Input contract

Accept one JSON object with:

- `references`: required ordered list of 2–4 unique image references.
  Each entry is either a source string or
  `{"name": "<optional unique display name>", "source": "<public HTTP(S) URL or local image path>"}`.
  String entries receive stable names `Member 1`, `Member 2`, and so on.
  List order is identity order: reference 1 maps to `[image1]`, reference 2
  maps to `[image2]`, and so on.
- `scene`: optional location or mood string. When omitted or blank, use the
  neutral stage default from the internal prompt compiler.

Reject missing, blank, duplicate, or non-image reference entries; fewer than
2 or more than 4 entries; duplicate names; unsupported fields; and scene text
containing `[imageN]`. Do not accept user overrides for duration, aspect ratio,
model, generate type, audio, prompt, camera mode, or watermark.

Example:

```json
{
  "references": [
    {"name": "Ara", "source": "/workspace/refs/ara.png"},
    {"name": "Bora", "source": "https://example.test/bora.png"}
  ],
  "scene": "neon rooftop at dusk"
}
```

## Fixed generation contract

- Duration: exactly 8 seconds.
- Aspect ratio: exactly 16:9.
- Coverage: one gapless continuous camera take with no cuts, transitions,
  blackouts that hide edits, or stitched takes.
- Identity: one ordered image reference per member, 2–4 members, with no
  identity drift, swaps, extra people, or reference reordering.
- Audio: unspecified. Do not add `audio_urls`, `generate_audio`, music,
  lyrics, dialogue, or soundtrack instructions.
- Model: unspecified by this Skill. Let the production video executor
  auto-route the Seedance 2 multimodal-reference model.

## Execute

Build the input as an object, serialize it to JSON in an environment variable,
and run the generator in the foreground:

```powershell
$payload = @{
  references = @(
    @{ name = "Ara"; source = "./refs/ara.png" },
    @{ name = "Bora"; source = "https://example.test/bora.png" }
  )
  scene = "neon rooftop at dusk"
} | ConvertTo-Json -Depth 20
$env:KPOP_ONE_TAKE_INPUT = $payload

python {{env_base_path}}\skills\kpop-multi-character-one-take-video-generator\references\generate_video.py --input-env KPOP_ONE_TAKE_INPUT
```

For POSIX test runtimes:

```bash
export KPOP_ONE_TAKE_INPUT='{"references":[{"name":"Ara","source":"/workspace/refs/ara.png"},{"name":"Bora","source":"https://example.test/bora.png"}],"scene":"neon rooftop at dusk"}'
python {{env_base_path}}/skills/kpop-multi-character-one-take-video-generator/references/generate_video.py --input-env KPOP_ONE_TAKE_INPUT
```

Run it once, in the foreground, with a process timeout greater than 3660
seconds. Capture and parse the complete JSON stdout. Never detach the process
or automatically resubmit after lost output, timeout, or cancellation because
the original paid task may still complete.

The generator performs these mandatory steps:

1. Validate and preserve reference order and uniqueness.
2. Upload each local file with the existing
   `{{env_base_path}}/skills/file-upload-to-cdn/references/upload_file_to_cdn.py`.
   Reuse public HTTP(S) references without re-uploading them.
3. Compile the fixed prompt package internally and run the prompt validator.
   Do not expose either internal script as a prompt-only product path.
4. Invoke
   `{{env_base_path}}/skills/ai-model-calling/scripts/video_skill.py`
   exactly once with `generate_type=multimodal_reference`, ordered
   `image_urls`, `duration=8`, `aspect_ratio=16:9`, and no `model_choice` or
   audio fields.
5. Accept success only when that executor returns `success: true` and a
   non-empty public final-video `url`.

The reused executor owns model auto-routing, wallet preFreeze and quota
handling, runtime auth, the gateway task submit/poll/wait lifecycle, provider
errors, private-to-public video URL conversion, and the canonical final URL.
Do not copy or reimplement those concerns here.

## Success contract

Return a JSON object containing all of:

- `success: true`
- `status: "succeeded"`
- `task.id` and `task.status: "succeeded"`
- `video.url` plus compatibility `url` and `video_url`
- routed model/task metadata returned by the production executor

Never report success with only a prompt, a process ID, an HTTP status, or a
provider task ID. Never invent a URL or local file.

## Failure contract

Return `success: false`, a terminal top-level and task status, `error_type`,
and `error` with `type`, `stage`, and the unchanged actionable message.

| `error_type` | Meaning |
| --- | --- |
| `upload_failure` | A local reference upload failed or returned no public URL. Do not submit video generation. |
| `model_failure` | Production auto-routing or model compatibility failed. |
| `quota_failure` | Wallet preFreeze, balance, credits, quota, or billing rejected the task. |
| `provider_failure` | Provider policy, safety, copyright, input, transport, or generation failed. |
| `timeout_failure` | Upload/executor timeout or an ambiguous downstream timeout. Do not resubmit automatically. |
| `cancel_failure` | The foreground run was interrupted or cancelled. Do not resubmit automatically. |

Input, internal prompt validation, missing shared scripts, and malformed
executor output use their own explicit failure types. Surface the shared
executor's message unchanged. A missing or unparsable executor response is
indeterminate and must never be treated as permission to retry.

## Real test-environment invocation

After this renamed Skill is uploaded to the **test** environment and the old
prompt-only directory is removed there, provide real image references and set
the test runtime variables without printing their values:

- `SYN_BASE_URL`
- `APP_BASE_URL`
- `canvas_id`
- `trace_id`
- `s3_SecretId`
- `s3_SecretKey`
- any auth headers/tokens required by the existing `ai-model-calling` runtime

Then run the POSIX command above using
`{{env_base_path}}/skills/kpop-multi-character-one-take-video-generator/...`.
Success evidence is the returned public `video.url`, not validator output.
This is a paid real-generation check: run it only with authorized test
credentials, canvas/trace context, quota, and 2–4 non-sensitive references.

## Guardrails

- Do not use any former prompt-only identifier or runtime path.
- Do not call provider APIs directly and do not add provider credentials.
- Do not duplicate upload, model routing, billing, task execution/waiting,
  error mapping, or URL publicification logic.
- Do not hand-edit the internally compiled prompt package.
- Do not retry a prepared payload automatically.
- "Film & CG" is a frontend category label only; never send it to the model.


## Seele Workspace case preview

![K-POP One-Take Reveal case cover](../../assets/cases/kpop-one-take-reveal.png)

[Open Film & CG in Seele Workspace](https://www.seeles.ai/workspace?category=film-cg)
