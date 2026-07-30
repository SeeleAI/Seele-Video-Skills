---
name: weekly-outfit-transition-video-prompts
description: "Plans and executes generation of weekly outfit transition reels, using model-ready English prompts only as internal production inputs: one consistent adult character in one fixed scene and camera setup changing through 5–7 daily looks with hard cuts, weekday captions, actions, props, and audio. Use for requests such as weekly outfit, outfit of the week, OOTW, 一周穿搭, 5天穿搭, 7-day outfits, daily lookbook transitions, or turning one adult character reference image into a multi-day vertical fashion reel. Do not use for general vlogs, travel diaries, interviews, narrative montages, unrelated multi-scene videos, or any sexualized-minor or explicit content."
---

# Weekly Outfit Transition Video Prompts

Turn one adult character reference into a coherent 5–7-day outfit-transition reel and, when the user requests a video deliverable, generate the final media in the same request flow. The compatibility name is retained, but prompts are never the final deliverable. Keep identity and production conditions locked while changing only the daily wardrobe, action, caption, and small local prop details.

## Operating Rules

- Treat one clear adult character reference image as the primary identity anchor. Extract only visible, persistent traits: facial structure, skin tone, hairstyle and color, body proportions, and distinctive non-sensitive features. Do not invent obscured details or identify a real person.
- Use an attached image only as visual reference evidence. Do not claim identity matching is guaranteed; phrase constraints as generation instructions.
- Infer all ordinary omissions. Do not ask the user to fill separate fields or specify every outfit. Ask at most one concise question only when adult age/identity safety is unclear, the core character anchor is absent and no usable adult text description exists, or requirements fundamentally conflict.
- If no image is available but a clear adult character description exists, proceed and state that identity consistency confidence is lower.
- Parse one optional natural-language instruction for location, day count, duration, aesthetic, palette, daily outfits, actions, captions, props, audio, and ending. Preserve explicit choices and fill the rest coherently.
- Default to **5 days, 12 seconds, 9:16 vertical, one fixed mid-long framing, hard cuts, weekday captions, low-volume upbeat instrumental BGM, and no dialogue**.
- Keep one character, one exact scene zone, one camera position, one focal treatment, one frame height, one aspect ratio, one lighting direction/intensity, and one background layout across every segment.
- Change only the daily outfit, pose/action, weekday caption, and small handheld or nearby prop. Prevent those props from altering the fixed scene geometry.
- Prefer looks that clearly differ in silhouette, layering, color placement, or accessory emphasis while remaining within one requested or inferred fashion story.
- Use hard cuts at matched body position or a repeated transition gesture. Do not introduce walk-through portals, morphs, spins, occlusion wipes, or camera moves unless explicitly requested and compatible with the fixed-shot format.
- Keep captions as clean post-production overlays, not physical text in the scene. Use Monday–Friday for 5 days, Monday–Saturday for 6, and Monday–Sunday for 7 unless the user provides labels.
- Do not drift into a general vlog narrative. If the request centers on travel, dialogue, an event, multiple locations, handheld coverage, or a story arc rather than outfit changes, route it to a general vlog/video-storyboard workflow instead.
- Do not claim that video, audio, or identity continuity has been generated or verified until the executor receipt and output have been checked.
- If the user asks only for planning or prompts, stop at the planning output. If the user asks to create, generate, render, or deliver the video, execution is mandatory after planning and any required approval.

## Safety Gate

- Require the depicted person to be clearly an adult. If age is ambiguous and styling could be sexualized, ask once for confirmation that the subject is 18+ before producing the prompt.
- Refuse sexualized depictions of minors or age-ambiguous subjects, explicit nudity, fetishized exposure, or sexual acts.
- For adult subjects, keep styling fashion-focused and non-explicit. Do not add transparent garments, exposed intimate anatomy, or sexualized poses unless a safe non-explicit interpretation fully resolves the request.
- Do not infer sensitive attributes, private identity, or personal history from the reference. Do not create deceptive claims that the real person performed an action.

## Workflow

### 1. Normalize the Brief

Extract and resolve:

- adult character reference or text anchor;
- location and exact fixed scene zone;
- 5–7 day count and total duration;
- 9:16 aspect ratio unless explicitly overridden;
- fashion aesthetic and palette;
- explicit daily outfits, actions, captions, or props;
- audio, dialogue preference, transition style, and final beat.

Clamp the format to 5–7 outfit segments. If a user requests a different count, ask one question only when that count is central; otherwise explain the nearest 5–7-day adaptation. If the user requests changing locations, camera angles, or lighting, ask once whether to preserve the weekly-outfit format or honor the incompatible multi-scene concept.

State only consequential assumptions. Do not repeat a long intake summary.

### 2. Build the Character Lock

Write one compact identity block that repeats visible anchors from the reference:

- adult status;
- face shape and stable facial features without naming a person;
- hairstyle, hair color, and length;
- skin tone and body proportions using neutral language;
- stable makeup/grooming baseline;
- identity preservation rules: same face, age, hair, proportions, hands, and number of people throughout.

Separate identity from clothing so wardrobe changes cannot rewrite the character. If parts of the body are not visible in the reference, use neutral defaults and mark them as inferred.

### 3. Lock Scene and Camera

Define one immutable setup:

- exact location zone and fixed background landmarks;
- time of day, light direction, color temperature, shadow direction, and exposure;
- locked tripod position, camera height, distance, lens perspective, and mid-long framing;
- 9:16 composition with full outfit and footwear visible when feasible;
- fixed focus/exposure/white balance and no zoom, pan, tilt, orbit, reframing, or angle changes;
- a repeatable neutral start/end pose or transition gesture.

The scene, camera, and light description must remain verbatim-compatible across segments.

### 4. Design the Daily Looks

Create one look per day. For each segment specify:

1. exact start and end time;
2. weekday caption;
3. complete clothing from outer layer to footwear plus 1–3 accessories;
4. color and material details that read clearly at mid-long distance;
5. one simple executable action with a stable start and end pose;
6. at most one small prop and its hand/state;
7. a hard-cut handoff aligned to the next segment.

When the user provides only some outfits, preserve them in their assigned order and design the missing looks around the same aesthetic. Avoid accidental garment carryover unless an explicitly recurring item is part of the concept.

Divide duration across all segments so timestamps are contiguous, non-overlapping, and sum exactly to the target. For the default, use five equal **2.4-second** segments: `0.0–2.4`, `2.4–4.8`, `4.8–7.2`, `7.2–9.6`, `9.6–12.0`.

### 5. Plan Audio and Ending

Use one continuous low-volume upbeat instrumental bed by default, with subtle fabric, footwear, and prop foley under it. Use no dialogue, lip-sync, narration, crowd voices, or caption readout unless explicitly requested. Keep music tempo and loudness consistent across cuts.

Make the final segment resolve cleanly with a held pose, small smile, wink, accessory adjustment, or user-specified action. Do not add logos, calls to action, or an outro card unless requested.

### 6. Compile the Internal Generation Prompt

Produce one self-contained English generation prompt that includes the character lock, immutable scene/camera/light setup, every timestamped segment, audio, captions, transitions, ending, and negatives. Repeat critical continuity language where useful, but do not bury actions in decorative prose.

Use concrete visible instructions instead of abstract quality claims. Explicitly distinguish intentional daily wardrobe changes from forbidden identity, camera, scene, and lighting changes. This prompt is an internal production artifact or optional appendix, not proof of completion.

### 7. Execute Requested Video Delivery

When the user requested a final video:

1. Load `ai-model-calling` and read its video reference before building the payload. Use one coherent video call for the full 5–12 second reel when the requested duration fits; otherwise split into ordered 5–12 second segments with identical identity, scene, camera, light, and transition anchors.
2. Resolve model, `generate_type`, prompt, public reference-image URLs, aspect ratio, duration, audio flag, and camera lock. Use reference images only when rights and adult-status requirements are satisfied.
3. If the execution policy requires approval for paid generation, show the prepared call count and cost-bearing action and obtain one explicit approval immediately before the calls. Do not ask again for the same approved batch. After approval, execute it; do not hand prompts to an unspecified caller.
4. Run each `ai-model-calling` video executor call in the foreground and parse its complete JSON stdout. A call succeeds only when `success: true` and `url` is a non-empty public URL. Record the model, parameters, call status, public URL, and provider message as the generation receipt.
5. If several clips were required and a compatible stitching/editing capability is available, assemble them and require a separate successful receipt plus public URL for the final cut. If no compatible stitcher exists, report the segment URLs and receipts, set final assembly to `blocked`, and do not call the segments a finished single video.
6. Treat missing tools, missing configuration, approval refusal, insufficient balance, policy rejection, model failure, malformed JSON, empty URL, and failed stitching as `blocked` or `error`. Never downgrade any of them to prompt-only success and never resubmit an indeterminate paid call automatically.

### 8. Review the Generated Artifact

Inspect the returned video or segment artifacts for adult safety, day order and captions, identity/wardrobe continuity, locked scene/camera/light, action completion, audio, duration, and visible model defects. Mark each check `pass`, `warn`, `fail`, or `not_reviewed`; a `fail` blocks success.

## Negative Constraints

Always exclude: minor or age-ambiguous sexualization, explicit nudity, identity drift, face replacement, age drift, hairstyle drift, body-shape drift, extra people, duplicate bodies, malformed face or hands, extra fingers or limbs, outfit changes inside a segment, clothing morphing, garments blending between days, unintended recurring garments, camera movement, angle changes, zoom, crop changes, focal-length changes, reframing, background changes, moving architecture, lighting shifts, time-of-day changes, exposure flicker, white-balance shifts, weather changes, jumpy body position, teleporting props, unreadable or misspelled weekday captions, captions attached to objects, extra text, logos, watermarks, dialogue, lip-sync, narration, abrupt music resets, glossy beauty-ad retouching, cinematic orbit shots, slow-motion glamour shots, collage layouts, split screens, fake app UI, and general vlog storytelling.

## Output Format

For a final-video request, return Markdown in exactly this order:

1. **Delivery Status** — `success`, `blocked`, or `error`; `success` is allowed only after generation returned `success: true`, a non-empty public artifact URL exists, and QA has no blocking failure.
2. **Video Artifact** — final public URL/file and duration; for an unstitched multi-clip result, label each as a segment and mark final stitching `blocked`.
3. **Generation Receipt** — model, modality, parameters, call count, per-call status/message, and every public URL; never include credentials.
4. **Artifact QA** — continuity, captions, motion, audio, safety, and final-assembly findings.
5. **Planning Appendix** — concise Character Lock, Global Scene/Camera, timeline, negatives, and internal model-ready English prompt.

For an explicitly planning-only request, return the planning appendix without claiming media delivery.

Before returning, verify: the person is clearly adult; day count is 5–7; timestamps total the requested duration; every day has a distinct complete outfit and one executable action; all captions are correct; identity, scene, camera, and light are locked; audio has no accidental dialogue; and every claimed artifact meets the receipt and URL success contract.


## Seele Workspace case preview

![Weekly Outfit Transitions case cover](../../assets/cases/weekly-outfit-transitions.webp)

[Open Film & CG in Seele Workspace](https://www.seeles.ai/workspace?category=film-cg)
