---
name: greybox-cg-v2v
description: >-
  Make a finished, stylized CG video by first building a fast GREY-BOX / white-model
  (白模/灰模) animated shot in Three.js — primitive boxes/capsules + code-driven motion and a
  deliberate camera move — recording it to video, then restyling it with Seedance 2.0
  video-to-video (v2v) so the camera move and structure are preserved while the subject is
  swapped and background, lighting and style are repainted into the look the user wants. This
  is the "Unreal Engine / Blender white-model → AI Rendering" trend and exactly Seedance 2.5's
  official "3D 白模预演 / white-model previz" path (the runner-on-a-bridge clips): the grey-box
  is a staging blueprint carrying motion + camera + composition; the v2v pass adds all the
  materials/lighting/style AND replaces the subject — turning generation from a slot machine
  into a directed render. Use this WHENEVER the user wants to: turn a self-made/quick 3D
  animation or previz into a polished stylized video; "把白模/灰模动画用 AI 重绘成 XX 风格";
  do a greybox→AI-render / previz→final restyle / 白模预演; make a short cinematic shot where
  the look comes from v2v rather than from real assets; or recreate the Seedance/即梦
  video-to-video / 组合参考 restyle trend. Triggers (EN/中文): grey-box / whitebox / white-model /
  白模 / 白膜 / 灰模 / 占位模型 + cg / animation / 动画 / 运镜 / 演绎 / shot; previz /
  previsualization / 预演 / 白模预演 / storyboard-to-video / 分镜转视频 / directed render / 定向渲染;
  restyle / 重绘 / 风格化 / v2v / 视频转视频 / 视频重绘 / video-to-video / 组合参考 / 多模态参考;
  "make a quick animation then let AI repaint it", "白模跑一段再 v2v".
  Do NOT use this to build a real, playable game (use threejs-game-builder) — this is a
  non-interactive camera-driven SHOT whose final image is produced by AI v2v, not a game.
---

# Grey-box → v2v restyle (greybox-cg-v2v)

Build a rough grey-box animated shot fast, record it, show the user a previewable Three.js scene
and grey-box mp4, then wait for explicit approval before Seedance video-to-video may turn it into a
finished, styled video. **Two things are everything: the approved recorded input clip and the v2v
prompt.** Everything in this skill serves those two.

## P0 two-stage confirmation gate

This skill is now a two-stage pipeline. The default and required first turn is **greybox review only**:
generate a previewable Three.js white-model scene, record the white-model mp4, write a revision
manifest, deliver those artifacts, and stop for user review. Do not call V2V in the same turn.

Hard rules:

- `GREYBOX_REQUIRE_APPROVAL` is a safety flag and defaults to required. The final V2V wrapper refuses
  unsafe execution when approval is missing or the flag is disabled unexpectedly.
- Every grey-box attempt must create or update a manifest with
  `schema_version`, `state`, `greybox_revision_id`, `parent_greybox_revision_id` (canonical; `parent_revision_id` is a read/write compatibility alias), `source_prompt_hash`,
  Three.js Preview artifact, greybox video artifact, `approval`, and `final_render`.
- Canvas identity is runtime-owned. `canvas_id` must be a canonical UUID, `session_canvas_id` must be the
  runtime pipe-delimited trace beginning with that UUID, and optional `game_id` is a separate business
  identifier. The create helper reads Canvas/session identity from runtime env; legacy identity CLI flags
  only assert equality. The final wrapper re-binds both fields to runtime before constructing any request.
- The first generated revision ends in `greybox_ready_for_review`, with `approval.status=pending` and
  `final_render.allowed=false`.
- If the user requests changes, treat the current manifest revision as canonical `parent_greybox_revision_id`, create a
  new `greybox_revision_id`, generate a new Three.js Preview and greybox video, and stop again in
  `greybox_ready_for_review`. Modification requests never trigger V2V.
- Only an explicit confirmation of the current revision may change state to `greybox_approved`.
  Ambiguous language such as "还行吧", "差不多", "looks ok-ish", or "maybe" is not approval; ask for a
  clear approval or the requested modifications. Explicit negation such as "不同意", "不要确认",
  "not approved", or "do not confirm" always wins over approval-looking words.
- V2V input must come from the approved manifest for the approved revision. Never infer the input from
  "latest mp4", directory listing, chat history, or filename guesses.
- Use `scripts/run_final_v2v.py` as the mandatory code-level gate before any downstream V2V call. It
  exits non-zero and does not call downstream when the manifest is unapproved, the approved revision
  does not match, or the approved video path/hash differs from the manifest.
- Repeated approval uses the stable final idempotency key in `final_render.idempotency_key`. The wrapper
  writes deterministic `rendering_final/job_id` plus a dispatch receipt, then starts its controlled
  `final_v2v_worker.py` with `shell=False`. The receipt records worker/downstream PIDs and deterministic
  request/status/result/stdout/stderr paths adjacent to the manifest. If a final job is already recorded
  as `rendering_final` or `final_ready`, report that existing job/output and do not start another
  downstream call. A local wait timeout leaves that detached worker running, stays `rendering_final`, and
  is automatically reconciled from its result envelope on a later invocation; it is not a render failure.
  If downstream fails explicitly,
  the wrapper writes `state=failed`, `failed_stage=v2v`, sanitized error metadata, and
  `requires_explicit_retry_or_reconciliation=true`; a normal repeated confirmation must not auto-start
  another billable job.
- Artifact metadata must keep the three deliverables distinct:
  `artifact_type=greybox_threejs_preview`, `role=review_preview`, `name=Greybox Three.js Preview ...`;
  `artifact_type=greybox_video`, `role=v2v_input_candidate`, `name=Greybox Preview Video ...`;
  `artifact_type=final_video`, `role=final_output`, `name=Final Cinematic Video from Greybox ...`.
- Three.js Preview artifacts must set `engine=threejs`, `entrypoint=index.html`, `urls` when available,
  `path`, and revision metadata. Skill-only output still needs host artifact sync/metadata ingestion
  before Workspace Preview can automatically render it.
- The bundled Three.js template exposes debug-only `window.__GREYBOX_REVISION_ID__`,
  `window.__GREYBOX_MANIFEST_URL__`, and `window.__GREYBOX_MANIFEST_PATH__` from runtime-injected URL
  params or host globals. These values help preview/debug artifact lineage but are not a security source
  and never replace the approved manifest gate.

Skill-only boundary: this package has no service-side database, lock, SSE, Web button, or Canvas asset
registry. The manifest is the local contract, code gate, dispatch receipt, and local artifact metadata;
Koko/Web must provide durable service state, structured approve/revise actions, atomic idempotent final
job creation, and Canvas artifact sync for production.

**Positioning.** This is exactly Seedance 2.5's official **"3D 白模预演 / white-model previz"**
path: the grey-box is a **staging blueprint** that locks *space, composition, camera and motion*;
the v2v pass adds *materials, lighting and style* AND **replaces the subject** (a grey box-man
becomes a real/stylized character). That's the whole value — it turns AI video from a "generative
slot machine" into a **directed render**: you decide the staging, AI does the rendering. The
subject is *swapped*, never *kept* (see the one prompt rule in step 6).

## Why this exists / what it is NOT

The grey-box does NOT need to look good. It needs to be **legible**: clear masses/silhouettes, a
clear camera move, and distinct grey values so the v2v model can separate the forms in frame. All
the beauty — textures, characters, lighting, world — is painted on by the v2v pass. So building the
grey-box should be **fast and primitive-based**, never an asset-gathering or game-building exercise.

**A character subject is optional.** The shot can be **environment- / camera-driven with no character
at all** — e.g. a grey-box cyberpunk city with the camera pushing/craning through it, restyled into a
neon metropolis. These subject-less flythroughs are often the *most* reliable v2v results (nothing to
suffer identity drift). "Subject" below just means *the main forms in frame*; for a cityscape the
buildings ARE the subject. Everything else in the skill (legend → "transforms into", preserve the
camera move, combined-reference image) applies unchanged — the hero is simply the camera move + the
transformed environment. When there's no character, the camera move must carry the shot, so make it
deliberate (push-in, crane, orbit, fly-through).

This is deliberately the opposite of `threejs-game-builder`:

| greybox-cg-v2v (this) | threejs-game-builder |
|---|---|
| one non-interactive camera-driven shot, ≤10s | a complete, playable game |
| primitives + code-driven motion, zero real assets | retrieve/generate real models, textures, audio |
| final look comes from AI v2v | final look comes from the engine render |
| no game loop, UI, input, win/lose | full game systems |

If the user actually wants a playable game, stop and use `threejs-game-builder` instead.

## Mandatory request state machine

Apply this state machine to **every new request routed to this skill**, even when the user's prompt never
mentions “greybox”, “白膜”, or “白模”. Never skip or reorder a state:

1. **CURRENT_REVISION** — create a new current `greybox_revision_id`, or refresh it after any prompt or
   attachment change. Entering this state invalidates every approval for the previous revision.
2. **GREYBOX_SCENE_PREVIEW** — build and publish the current revision's previewable Three.js scene.
3. **GREYBOX_VIDEO_PREVIEW** — record and publish the current revision's greybox video. This state is
   forbidden until the scene preview for the same revision exists.
4. **AWAIT_EXPLICIT_APPROVAL** — deliver both previews, stop, and ask the user to approve the displayed
   `greybox_revision_id`. Do not invoke any final-video executor in this turn.
5. **FINAL_VIDEO** — only after explicit approval matching the unchanged current revision, invoke
   `scripts/run_final_v2v.py`; never call `video_skill.py` directly.

A new or revised prompt, changed attachment, or requested scene change always returns to
`CURRENT_REVISION`. Approval from an older revision is stale by definition.

## Pipeline

Work through these in order. Steps 1–5 create the current revision and its two previews; step 6 is the
mandatory approval stop; steps 7–10 are allowed only after the unchanged current revision is explicitly
approved.

1. **Clarify the shot.** Pin down: the main forms + any action (**a character is optional** — an
   environment/camera-driven shot like a city fly-through is fully valid), the camera move, the
   **target style/aesthetic**, aspect ratio, and duration (**≤10s** — this skill's clip policy; 5–8s is the sweet
   spot). If there's no character, the **camera move is the shot** — make sure it's a deliberate one.
   If the user gave a reference image/video for the style, note it. Ask only what you truly need.
2. **Write the legend.** Decide what each grey form will represent (subject, ground, props, background)
   and record it as the one-line `SHOT.legend` in `shot.js`. This legend is the bridge to the prompt:
   every grey form you place, you will later name in the v2v prompt via "transforms into …".
3. **Build the grey-box shot in Three.js.** Copy the template and edit `shot.js` (and reuse
   `humanoid.js` / `greybox.js`). Compose primitives, drive motion + a camera move from code,
   keep distinct grey values, keep it ≤10s and at the target aspect. See
   `{{env_base_path}}/skills/greybox-cg-v2v/references/building-shots.md`.
4. **Record to mp4.** Run the recorder; it deterministically steps the animation, captures it, and
   transcodes to H.264 mp4. See `{{env_base_path}}/skills/greybox-cg-v2v/references/recording.md`.
   On success, consume the structured JSON fields `video_path`, `duration_ms`, `fps`, and `sha256`
   when building the manifest. On failure, honor the recorder's stable error JSON and exit code:
   invalid CLI/input is non-retryable exit 2; capture/encode failures are retryable exit 3; missing
   Python runtime dependencies or unavailable ffmpeg are non-retryable exit 4. Do not retry forever.
   **Inspect a couple of extracted frames** to confirm the silhouette/camera read clearly before spending a v2v call.
5. **Upload/register review artifacts and write the manifest.** Upload the clip to CDN when available
   and take the public CDN URL, never the S3 URL. The downstream v2v model
   fetches the clip over the public internet, so it must be served via the CDN, not S3.
   `record_greybox.py` only writes a local mp4; upload it with `file-upload-to-cdn`:
   `python {{env_base_path}}/skills/file-upload-to-cdn/references/upload_file_to_cdn.py --file <shot.mp4> --content-type video/mp4`
   From the returned JSON take **`data.cdn_url`** — the `https://static.seeles.ai/…` link. Do NOT use
   `data.s3_uri` or `data.origin_url` (`s3://…` / `…s3.amazonaws.com/…`): the v2v model cannot fetch those.
   The `video_url` you pass to v2v must start with `https://static.seeles.ai/`.
   **Then register the grey-box clip as an asset** (so it is visible on the canvas and reusable — you can
   re-run v2v with a new prompt / reference image later without re-recording). Call `asset-json-writer`:
   category **`videos`**, `urls` = `[the grey-box CDN url]`, `name`/`description` naming it a grey-box previz,
   `tags` including **`greybox-previz`** (and `intermediate`), `status: ready`. Keep its `asset_id` — the
   final v2v output (step 9) will reference it via `derived_from`. `asset-json-writer` only fires on an
   explicit write request, so ask it to "Generate the asset JSON for the grey-box previz video".
   Then run the manifest helper (it reads `CANVAS_ID`/`canvas_id` and
   `X_SEELE_CANVAS_TRACE_ID`/`trace_id` from the trusted runtime; do not substitute a game ID):
   `python {{env_base_path}}/skills/greybox-cg-v2v/scripts/greybox_manifest.py create-ready --source-prompt "<prompt>" --threejs-path <build_dir_or_index.html> --greybox-video-path <shot.mp4> --greybox-video-url <cdn-url> --threejs-url <index-url> --game-id <optional_business_game_id> --out <greybox_manifest.json>`.
6. **Deliver the review and stop.** Show the Three.js Preview artifact/path, greybox video artifact/path,
   revision id, and manifest path. Ask the user to either explicitly approve this revision for final V2V
   or request changes. Do not load or execute `references/v2v-call.md` yet.
7. **After explicit approval, approve the manifest.** Only for a clear confirmation of the current
   `greybox_revision_id`, run:
   `python {{env_base_path}}/skills/greybox-cg-v2v/scripts/greybox_manifest.py approve --manifest <greybox_manifest.json> --revision-id <current_revision_id> --approved-by "$USER_ID"`.
   If the user asks for changes instead, create a new revision from the current revision as parent,
   regenerate the Three.js scene and greybox video, then return to step 5.
8. **Craft the v2v prompt.** This is the core craft. Build it from the user's style intent + the legend.
   Read `{{env_base_path}}/skills/greybox-cg-v2v/references/prompt-crafting.md` and follow it — lock the
   camera/motion, name every grey form ("transforms into …"), then style/light/scene/finish.
   **The one rule that decides success (prompt-crafting §1):** the preserve/"keep" clause holds
   **behavior only** — camera, body motion, timing, composition — and contains **NO appearance noun**.
   Never write "keep the same players / subject / ball / character": that makes the model keep the
   grey-box and merely re-material it (a glossy box-man in a nice scene, not a real character). Every
   subject/object must be **transformed** ("the grey figure transforms into a real footballer …"). The
   video is *structure only*; the prompt (plus an optional reference image in step 8) supplies *who/what*.
   When you pass reference media, **name each one and its job in the prompt** — Seedance addresses them by
   an indexed handle, 1-indexed per modality in pass order: `video_url`→视频1/video 1, `image_urls`→图片1/图片2…,
   `audio_urls`→音频1 (e.g. "参考视频1的运镜和动作，把主体渲染成图片1里的角色"). With multiple characters, bind by
   position (图片1=左, 图片2=右). See prompt-crafting §5.
9. **Prepare the look/character reference, then CONFIRM it with the user (recommended — the biggest
   quality lever).** Get a reference image of *who the subject becomes*: restyle the recorder's
   `<mp4>_frame0.png` into the target look (nanobanana / nanobanana_pro image edit via `ai-model-calling`),
   or use a clean character portrait / design. Upload it to CDN (`file-upload-to-cdn` → `data.cdn_url`).
   **Before spending the full v2v call, show it to the user and get their sign-off:** reply in normal chat
   with the image shown inline via markdown image syntax — `![restyled look reference](https://static.seeles.ai/…)`,
   **never a bare URL** — and ask whether to proceed or adjust. If they want changes, tweak the still-image
   prompt, regenerate, re-upload, and show again. Only once they approve, continue to step 8 passing the
   approved image as **`image_url`** (see step 8 for why not `first_frame_url`). See prompt-crafting.md §5.
   (Skip this only if the user explicitly wants the fast plain-prompt pass.)
10. **Run v2v through the approval gate.** Load `ai-model-calling` and call its general
   video executor **`video_skill.py`** (the dedicated `seedance_video_to_video_skill.py` was removed).
   **Always use `generate_type: "multimodal_reference"`** (this skill is a combined-reference pipeline —
   use one mode throughout). Pass `video_url` (the CDN clip) + your prompt + **`model_choice`**
   (`seedance2_1080p` final / `seedance2_fast_720p` iterating) + **`aspect_ratio`** (match the shot;
   `ratio` is an accepted alias) + `duration` + `camera_fixed=false`. For the character swap (the
   "组合参考 / combined reference" pattern — video = motion + camera, image = *who*) also pass the approved
   reference from step 7 as **`image_url` / `image_urls`**. Under `multimodal_reference` the image is a
   *reference* (identity/look), not a first frame — exactly what we want; do **not** use a first-frame
   mode / `first_frame_url` for the look anchor (that drops the video's motion role). With no image it is
   still `multimodal_reference` with only the video reference.

   Prefer the shell-neutral wrapper command
   `scripts/run_final_v2v.py --manifest <greybox_manifest.json> --approved-revision-id <current_revision_id> --current-latest-revision-id <current_revision_id> --use-default-downstream`.
   For a nonstandard executor location, pass a UTF-8 argv JSON file with `--downstream-argv-file`; the
   inline `--downstream-argv-json` form remains validated legacy compatibility and must not be hand-written
   in PowerShell. All forms validate the executor protocol and run with `shell=False`. Every invocation
   writes a secret-free `<manifest>.final-v2v-receipt.json` with Canvas/session/revision binding, manifest
   digest, final job, stage, diagnostic code, retryability, and request/task IDs when available. The video is structure
   only; the image decides identity. See
   `{{env_base_path}}/skills/greybox-cg-v2v/references/v2v-call.md` for timeout reconciliation, delivery
   resume, and configurable provider parameter policy.
11. **Register the final result as an asset.** The wrapper downloads the v2v URL to its deterministic
   `final_videos/<job-id>.mp4` path and records local SHA-256/size/source metadata. The URL is already a
   public CDN link, but for it
   to land as a first-class, reusable asset (visible on the canvas / discoverable by `asset-retrieval`),
   register it with `asset-json-writer`: category **`videos`**, `urls` = `[the v2v output CDN URL]`, plus
   `name` / `description` / `tags`, `status: ready`, and **`derived_from` = the grey-box previz asset id
   from step 5** (so the previz → final lineage is recorded). This is the same finishing convention as
   `visual-concept-design` / `slide-deck`. `asset-json-writer` only fires on an explicit write request, so
   ask it to "Generate the asset JSON for the video". Then return the styled video URL (and its asset id).

**Stop at the grey-box clip until approval.** Even when the user ultimately wants a finished video, the
first turn's deliverable is the reviewable Three.js Preview + greybox mp4 + manifest. After explicit
approval, do not stop at the grey-box clip; proceed through the approval-gated final V2V and register the
final video asset.

## Iterating

Before approval, iteration means creating a child greybox revision and regenerating the Three.js Preview
and greybox video, with no V2V call. After approval and final render, prompt-only V2V iteration is a new
approved final job for the same revision and must still use the manifest idempotency gate.

## Bundled resources

- `assets/template/` — the Three.js grey-box starter you copy & edit: `index.html`, `main.js`
  (recording orchestration + the `window.__cap` capture contract), `greybox.js` (the grey-box look:
  value-separated palette, matte materials, lighting, camera, primitive builders), `humanoid.js`
  (a proportioned humanoid from primitives with a code-driven walk/run cycle), `shot.js` (the
  editable scene — defaults to the bridge-runner reference shot).
- `scripts/record_greybox.py` — deterministic recorder: drives the page headless, captures, transcodes
  to mp4, and emits structured success/error JSON for manifest generation.
- `scripts/greybox_manifest.py` — revision manifest creation, validation, approval, artifact separation,
  and stable idempotency fields.
- `scripts/run_final_v2v.py` — mandatory approval gate wrapper for final V2V. It refuses unapproved,
  mismatched-revision, mismatched-path/hash, and invalid executor parameters before downstream can run;
  persists a deterministic dispatch receipt; launches `scripts/final_v2v_worker.py` without a shell;
  separates foreground wait timeout, render failure, and delivery failure; auto-reconciles completed
  worker envelopes; and atomically downloads final output with artifact metadata.
- `scripts/final_v2v_worker.py` — detached local worker that performs exactly one controlled executor
  invocation and atomically persists result/status envelopes plus stdout/stderr in the deterministic job
  directory. It is local orchestration only, not a Koko/Web job-state implementation.
- `references/building-shots.md` — how to author `shot.js` (primitives, humanoid, camera, value separation, timing).
- `references/recording.md` — how recording works, the command, runtime deps, and fallbacks.
- `references/prompt-crafting.md` — **the v2v prompt methodology (read this every time).**
- `references/v2v-call.md` — exactly how to call `ai-model-calling`'s Seedance v2v (payload, params, return).


## Seele Workspace case preview

![Greybox Previz case cover](../../assets/cases/greybox-previz.jpg)

[Open Film & CG in Seele Workspace](https://www.seeles.ai/workspace?category=film-cg)
