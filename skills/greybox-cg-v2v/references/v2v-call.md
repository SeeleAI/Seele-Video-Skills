# Calling Seedance video-to-video (via ai-model-calling)

## Mandatory approval gate

Do not call this reference during the first greybox generation turn. Final V2V is allowed only after
the current `greybox_revision_id` is explicitly approved in `greybox_manifest.json`.

Before any downstream `video_skill.py` call, run the code-level wrapper. The preferred command has no
inline JSON and works unchanged in PowerShell, cmd.exe, and POSIX shells:

```bash
python {{env_base_path}}/skills/greybox-cg-v2v/scripts/run_final_v2v.py \
  --manifest <greybox_manifest.json> \
  --approved-revision-id <current_greybox_revision_id> \
  --current-latest-revision-id <current_greybox_revision_id> \
  --use-default-downstream
```

The controlled default resolves the checked-in sibling
`ai-model-calling/scripts/video_skill.py`. For a nonstandard installation, write the argv array to a
UTF-8 JSON file and pass `--downstream-argv-file <argv.json>`. The legacy `--downstream-argv-json` entry
point remains compatible, but should not be hand-written in PowerShell. All forms are validated to
contain `--input-env AI_MODEL_CALLING_INPUT` and execute with `subprocess.run(..., shell=False)`; shell
command strings, pipes, redirects, and `&&` are not supported.

The wrapper first reads the trusted runtime Canvas/session values from `CANVAS_ID`/`canvas_id` and
`X_SEELE_CANVAS_TRACE_ID`/`trace_id`. It requires a canonical Canvas UUID, a pipe-delimited session trace
whose first field is that UUID, and exact equality with the manifest. `game_id` remains an optional,
separate business identifier and is never forwarded as Canvas identity.

The wrapper exits non-zero and does not execute downstream if:

- trusted runtime Canvas/session identity is missing, conflicting, malformed, or differs from the manifest.
- `GREYBOX_REQUIRE_APPROVAL` is not safely enforcing approval.
- `state` is not `greybox_approved`, `rendering_final`, or `final_ready`.
- `approval.status` is not `approved`.
- the approved revision does not exactly match the manifest revision.
- the approved greybox video path differs from the V2V input path.
- the approved greybox video hash differs from the file contents or `final_render` hash.
- the manifest is already `failed`, because explicit retry or service-side reconciliation is required.

V2V input must come only from `final_render.v2v_input_video_url` / `final_render.v2v_input_video_path`
in the approved manifest. Never search for the newest `.mp4`, guess from filenames, or use chat history
as the source of truth.

Before invoking downstream, the wrapper validates the manifest schema, runtime identity/session binding,
approval/current-latest revision, structured argv, and the complete executor request. Invalid input cannot
create a worker request or downstream task. It then writes a deterministic `rendering_final` claim and
`final_render.dispatch_receipt`. Its `job_id` / downstream `task_id` derives from
`final_render.idempotency_key`, and its request hash is persisted before any billable call. It then starts
the checked-in `final_v2v_worker.py` as a detached, shell-free local worker. The deterministic
`<manifest-dir>/.greybox_v2v_jobs/<job-id>/` directory holds its request, status, stdout, stderr, helper
log, and atomic result envelope; receipt metadata stores those paths and PIDs.

If the foreground wait exceeds `--wait-timeout-seconds` (default 540), it returns without terminating the
worker, keeps `state=rendering_final`, and marks the receipt `wait_timeout`. This is not classified as a
render failure. Any later normal invocation first checks the result envelope: success downloads/registers
the artifact, explicit failure is persisted as V2V failure, and an incomplete worker suppresses another
dispatch. `--reconcile-result-file <result.json>` remains an optional external reconciliation path, not a
requirement for the persistent worker.

Every invocation also writes a secret-free diagnostic receipt (default:
`<manifest>.final-v2v-receipt.json`, override with `--diagnostic-receipt`) containing only Canvas/session/game
identity, revision, manifest digest, final job, stage, stable diagnostic code, retryability, and request/task
IDs when created. It never includes argv, prompts, tokens, headers, or provider credentials.

If downstream explicitly exits non-zero, the wrapper persists `state=failed`, `failed_stage=v2v`, a
sanitized error, and `requires_explicit_retry_or_reconciliation=true`. A normal repeated approval must
not launch another final job after that failure. This local manifest gate narrows the crash window, but
production still needs Koko to claim/create billable V2V jobs atomically with the same idempotency key;
this wrapper deliberately does not implement the Koko/Web state machine.

Do not reimplement or copy the gateway script. Load the `ai-model-calling` skill and call its
video executor; its `references/video.md` is the authoritative spec. This file is the just-enough
recipe for our use case.

> **⚠️ Interface note (2026-07):** the *dedicated* Seedance v2v task and its `seedance_video_to_video_skill.py`
> executor were **removed**. Reference-video work now goes through the **general video executor**
> `scripts/video_skill.py` (task `seedance_generate`) with a **`generate_type`**. Do not call the old
> `seedance_video_to_video_skill.py` / `seedance_video_to_video_generate` task even if the file lingers.

## The call

Use `video_skill.py`. Pass the payload as JSON in an env var:

```bash
export AI_MODEL_CALLING_INPUT='{ ...payload... }'
uv run python {{env_base_path}}/skills/ai-model-calling/scripts/video_skill.py --input-env AI_MODEL_CALLING_INPUT
```

It returns one JSON object; the styled video is `url` (already a public CDN link). On success the wrapper
also downloads that URL atomically to
`<manifest-dir>/final_videos/<deterministic-job-id>.mp4` (override with `--final-output-path`) and writes
path, URL, SHA-256, byte count, source revision, and delivery state into the final-video artifact
metadata. A download error is `failed_stage=delivery`, preserves the final URL, and blocks dispatch;
retry only delivery with `--resume-delivery`.

The wrapper deletes any inherited `GREYBOX_V2V_INPUT` and caller-provided `AI_MODEL_CALLING_INPUT`, then
constructs the real `video_skill.py` payload exclusively from the approved manifest and exports it as
`AI_MODEL_CALLING_INPUT`. Production Koko should also enforce the same current-latest revision, approved
URL/hash, and idempotency key server-side before creating a billable final job.

> **The one prompt rule (prompt-crafting.md §1).** The video is a GREY-BOX — structure only. The
> prompt's preserve/"keep" clause holds **behavior only** (camera, motion, timing, composition) and
> **no appearance noun**. Never "keep the same players / subject / ball" — that keeps the grey
> geometry and just re-materials it (glossy box-man). Every subject/object must be **transformed**
> ("the grey figure transforms into …"); for a clean character swap, anchor it with a reference image (path B).

## Payload — always `generate_type: multimodal_reference`

This skill is a combined-reference pipeline, so **always use `generate_type: "multimodal_reference"`**
— one mode throughout, whether or not a character image is present. Key field names for this executor:
**`model_choice`** (not `model`), **`generate_type`**, and **`aspect_ratio`** (`ratio` is accepted as an
alias). Resolution is encoded in `model_choice` (there is no separate `resolution` field). Choose a
**Seedance 2** model_choice: `seedance2_720p`, `seedance2_1080p`, `seedance2_fast_720p`, `seedance2_fast_1080p`.

### A. Video only (plain restyle)

The grey-box clip is the single reference. videoGen preserves/transforms subject, motion, camera, style
or scene per the prompt.

```json
{
  "generate_type": "multimodal_reference",
  "model_choice": "seedance2_720p",
  "prompt": "<the v2v restyle prompt from prompt-crafting.md>",
  "video_url": "<CDN url of the recorded grey-box mp4>",
  "aspect_ratio": "16:9",
  "duration": 8,
  "camera_fixed": false
}
```

### B. Video + character image (the combined reference — RECOMMENDED)

The canonical trend technique and the single biggest quality lever — Seedance's "多模态参考 / 组合参考"
(see prompt-crafting.md §5). The video is **structure only**; the image says **who the subject becomes**,
so the grey-box is genuinely swapped for a real/stylized character instead of re-materialed. Under
`multimodal_reference`, images in `image_url` / `image_urls` are treated as **references** (up to 9),
NOT as a first frame — which is exactly what we want.

```json
{
  "generate_type": "multimodal_reference",
  "model_choice": "seedance2_1080p",
  "prompt": "Use video 1 for the camera move, body motion and timing. Render the subject as the character in image 1 — do NOT keep the grey source geometry; image 1 sets the look. Preserve video 1's framing, pacing and composition; keep the same shot scale. <one line of style finish>",
  "video_url": "<CDN url of the grey-box mp4>",
  "image_url": "<CDN url of the character/style reference (e.g. the confirmed restyled still)>",
  "aspect_ratio": "16:9",
  "duration": 8,
  "camera_fixed": false
}
```

Use `image_urls` (a list) for several characters, one reference each. Do **not** switch to a first-frame
mode / `first_frame_url` for the look anchor: that makes the image the literal opening frame instead of a
reference identity, and drops the video's motion role. Keep the subject as a **reference**, not a first frame.

### Field notes

- **URLs must be public CDN links** — `https://static.seeles.ai/…`, i.e. the `data.cdn_url` returned by
  `file-upload-to-cdn`. videoGen fetches them over the public internet, so an S3 URL (`s3://…` /
  `…s3.amazonaws.com/…`) or a local path will FAIL. Upload the recorded mp4 (and any reference image) to CDN first.
- `generate_type`: **always `multimodal_reference`** for this skill (with or without a character image).
  Set it explicitly. Never use the removed dedicated v2v task.
- `model_choice`: `seedance2_1080p` for finals; `seedance2_fast_720p` while iterating (both are Seedance 2).
- `aspect_ratio` (alias `ratio`): **must match the recorded shot's aspect** — `16:9` / `9:16` / `1:1` / `4:3` / `3:4` / `21:9`.
- `duration` (alias `seconds`): a positive integer; this skill's requested clip policy is **≤10s**. The
  checked-in `ai-model-calling` executor does not prove a model-specific duration ceiling, so do not infer
  that `seedance2_1080p + 10s` is invalid from a provider `PARAMS_ERROR`. When runtime/provider limits are
  known, encode them in `--validation-policy-file` as
  `{"duration_seconds_by_model":{"seedance2_1080p":{"min":1,"max":8}}}` rather than changing several
  request variables or inventing a hard-coded restriction.
- `camera_fixed`: **`false`** — we want the camera to follow the grey-box's move. `true` locks it.
- `image_url` / `image_urls`: **character/style reference image(s)** — "render the subject as this" (组合参考).
  Only meaningful under `multimodal_reference`; the prompt must say *transform / render as*, not *keep*.
- `video_url` / `video_urls`: the grey-box reference clip (Seedance accepts up to 3 videos for multimodal).
- **Name each reference in the prompt.** Seedance lets the prompt address references by an indexed handle,
  1-indexed **per modality in pass order**: `video_url` → 视频1 / video 1; `image_urls[0]` (or `image_url`)
  → 图片1, `image_urls[1]` → 图片2, …; `audio_urls[0]` → 音频1. Say what each does ("参考视频1的运镜和动作；
  把主体渲染成图片1里的角色"). With multiple characters, put them in `image_urls` in the order you name them
  and bind by position (图片1=左, 图片2=右). See prompt-crafting.md §5.
- `generate_audio`: optional; `true` lets Seedance add audio (costs more). Default off while iterating.
- `seele_canvas_trace_id` / `canvas_id`: usually supplied by the runtime env; pass through if you have them.

## Producing the look/character reference still (path B, step before the v2v call)

1. Get frame 0 of the grey-box clip: `record_greybox.py` emits it as `<mp4-name>_frame0.png` next to the
   mp4 (its `frame0` output field) unless `--no-frame0` was passed; or extract with `ffmpeg -i shot.mp4 -frames:v 1 frame0.png`.
   (You can also use a clean character portrait / design as the reference instead of the restyled frame.)
2. Restyle that still with `ai-model-calling`'s **image** generation in image-edit mode —
   model `nanobanana_pro` (or `nanobanana`), input image = `frame0.png`, prompt = the still-image
   prompt from prompt-crafting.md §5 (full target content, no "preserve" language). See
   `ai-model-calling`'s image reference for the exact image payload. **If it returns a system error
   (`SYSTEM_ERROR` / gen fail — a transient model-service issue, not your prompt), fall back to a
   `seedream` model** (e.g. `seedream4.5`) rather than aborting; the pipeline shouldn't hard-depend on one image model.
3. Upload the result to CDN (`file-upload-to-cdn`) → pass that URL as **`image_url`** in the
   `multimodal_reference` payload above.

## Alignment with Volcengine Ark (the upstream Seedance API)

`ai-model-calling` is a thin wrapper over videoGen → Volcengine Ark. In Ark terms our two paths are:
`multimodal_reference` maps onto Ark's reference-video generation, where the video is the motion/camera
reference and any image is a **reference image** (subject/look), NOT a first frame. That's why we always
use `multimodal_reference` rather than a first-frame mode. Generation
controls (`aspect_ratio`, `duration`, `camera_fixed`, `watermark`) are **JSON fields**, not `--flags` in
the prompt. Output is **24fps** (record at 24fps); the reference video should be **2–15s**.

## Discipline

When the user asked for a finished video, this call is the final-stage deliverable after approval. Before
approval, stop at the recorded greybox clip and review manifest. If the result needs work, the cheapest
post-approval fix is almost always the **prompt**; before approval, motion / camera / composition /
silhouette changes must create a new greybox revision instead of calling V2V.
