---
name: authentic-camcorder-vlog-video-prompts
description: "Plans and executes generation of connected 5–8-shot authentic personal camcorder, phone, or compact-camera vlog footage from a simple real-world premise; model-ready prompts are internal production inputs, while final-video requests return generated media, receipts, and QA. Use when creating casual MiniDV, iPhone 4S, iPhone 7, modern iPhone, Ricoh compact-camera, selfie, handheld, friend-follow, propped-camera, candid, or mixed-recording video storyboards with strong identity, prop, space, light, device, action, and audio continuity. Do not use for gameplay capture, game UI/HUD footage, glossy commercials, or generic cinematic trailers."
---

# Authentic Camcorder Vlog Video Prompts

Turn a minimal real-world premise into a production-ready connected sequence and, when requested, generated media. The compatibility name is retained, but a prompt pack is never completion for a final-video request. Default to personal, casual, unscripted footage with believable handling and device behavior—not a polished ad or cinematic montage.

## Operating Rules

- Infer ordinary missing details when they do not alter the premise. Do not interrogate the user about wardrobe, room layout, minor props, exact dialogue, or shot order.
- Ask one concise question only when a missing fact changes identity, safety, rights, or the core event. Otherwise state the few creative assumptions made.
- Treat recording method and recording device as separate dimensions. A MiniDV can be propped or friend-operated; an iPhone can be selfie, POV, fixed, candid, or mixed.
- Use an attachment as visual evidence for identity, wardrobe, props, location, palette, or device treatment. State what it anchors; do not invent details hidden by the reference.
- Preserve the premise. Add connective actions and mundane details, not a different story.
- Default to 5–8 shots with narrative progression: arrival/setup, development, a human micro-beat, payoff, and exit/aftermath. Vary shot function without creating random montage cuts.
- Keep dialogue sparse and natural: breath, half-sentences, off-camera remarks, laughter, room tone, handling noise, and event-specific sound. Do not write polished ad copy unless asked.
- Do not use game UI, HUD, screen-recording language, player-control artifacts, or the workflow from `authentic-gameplay-video-prompts`.
- Do not claim footage was generated or stitched until executor receipts and public artifact URLs have been checked.
- Planning-only requests may stop at a prompt pack. Requests to create, generate, render, or deliver video must proceed to execution in the same request flow after planning and any required approval.

## Workflow

### 1. Normalize the Brief

Extract:

- premise: person, place, event, intended feeling, and any explicit beats;
- recording method: Auto, handheld first-person, selfie, friend follow, fixed/propped, observational/candid, or mixed;
- recording device: Auto, MiniDV, iPhone 4S, iPhone 7, modern iPhone, or Ricoh compact camera;
- attachment anchors and hard constraints.

When method is Auto, choose a plausible method or a restrained mix that supports the event. When device is Auto, choose one coherent capture family; do not switch device signatures between shots unless the premise explicitly uses multiple devices.

### 2. Build the Continuity Bible

Define one global bible before the shot list:

- **Character:** stable identity markers, hair, face, build, wardrobe layers, footwear, emotional baseline, and who holds the camera.
- **Location:** compact spatial map, entrances, landmarks, surfaces, background objects, and plausible movement path.
- **Recurring objects:** 2–4 ordinary props with starting position and state.
- **Light/time:** time of day, practical sources, direction, color behavior, and any gradual change.
- **Device signature:** selected profile, aspect/orientation if implied, focus/exposure behavior, motion behavior, texture, and audio behavior.
- **State ledger:** starting action, object positions, wardrobe state, body state, and ambient/audio state.

Prefer a few specific anchors repeated across shots over many decorative details.

### 3. Design a Connected 5–8-Shot Arc

Give every shot a reason to exist and a physical handoff from the previous shot. Alternate perspectives only when camera ownership or placement can plausibly change. Useful functions include propped context, selfie reaction, walking POV, tactile detail, brief event payoff, close personal beat, and exit—but adapt them to the premise rather than copying a fixed sequence.

For each shot specify:

1. shot number and duration;
2. narrative purpose;
3. framing, camera owner/placement, lens behavior, and movement;
4. visible action, including start state and end state;
5. environment details that remain consistent with the location map;
6. natural audio, dialogue, breath, room tone, and handling sound;
7. transition/handoff into the next shot;
8. continuity anchors: identity, wardrobe, props, space, light/time, device signature, action/state, and audio;
9. one standalone executable generation prompt containing all visual, temporal, motion, audio, and continuity requirements needed for that shot;
10. shot-specific negative constraints.

Durations must add up to a plausible total. Keep each shot long enough to complete its action. Use hard cuts by default; use glitches, dropouts, whip movement, or exposure bumps only when motivated and sparingly.

### 4. Write Executable Prompts

Each per-shot prompt must stand on its own while repeating the compact global anchors necessary for continuity. Include:

- real-world subject and stable identity description;
- wardrobe and recurring prop state;
- exact location zone and light/time;
- recording method and camera ownership;
- concrete selected-device behavior;
- action from beginning through end;
- framing, movement, focus/exposure response, and texture;
- audio/dialogue intent when supported by the generation workflow;
- transition endpoint and exclusions.

Do not rely on brand labels alone. Replace “shot on iPhone 7” with observable behavior from the relevant profile. Avoid overloaded defect lists; authentic footage is not synonymous with damaged footage.

### 5. Plan Sequence Assembly and QA

Provide:

- ordered clip list and target total duration;
- cut points based on matched action, camera handoff, gaze, sound, or prop movement;
- audio bed continuity and where dialogue/room tone overlaps cuts;
- trim handles or overlap guidance for stitching;
- optional single motivated finishing artifact, if appropriate;
- final negative constraints shared by the sequence;
- continuity QA against every bible category.

If a generator cannot preserve audio, identity, or state reliably, mark that risk and prescribe separate sound design or reference-frame/character-reference handling rather than pretending it is guaranteed.

### 6. Execute Requested Video Delivery

When the user requested final media:

1. Load `ai-model-calling` and read its video reference. Build one foreground video-generation payload per approved 5–12 second shot, repeating the continuity bible and using public reference URLs when authorized. If the entire concept can be truthfully generated as one 5–12 second clip, one call is allowed; otherwise preserve the ordered shot plan.
2. Resolve model, `generate_type`, prompt, references, ratio, duration, audio behavior, and camera behavior before calling. The per-shot prompt remains internal or an appendix.
3. If paid-generation policy requires approval, present the prepared call count and cost-bearing action once immediately before execution. After explicit approval, execute the approved calls without a second planning handoff and without delegating them to an unspecified caller.
4. Parse complete JSON stdout from each foreground call. A clip succeeds only when the executor returns `success: true` and a non-empty public `url`; store one receipt per shot with shot ID, model, parameters, status, URL, and provider message.
5. For a requested single finished cut, use an available compatible editing/stitching capability (including an applicable `ai-model-calling` video operation) and require its own `success: true`, non-empty public URL, and receipt. If no compatible stitcher exists, deliver only explicitly labeled segment artifacts and set final stitching to `blocked`; never describe segments as a finished film.
6. Missing tools/configuration, no approval, insufficient balance, policy or rights rejection, failed or indeterminate executor output, empty URL, and failed stitching are `blocked` or `error`. Do not report prompt-only success and do not automatically resubmit a paid call whose result is indeterminate.

### 7. Artifact QA

Review the returned clips and, when present, final cut against identity, wardrobe, prop, spatial, light/time, device, action, audio, duration, ordering, and authentic-handling continuity. Record `pass`, `warn`, `fail`, or `not_reviewed` with evidence. Any safety/rights failure, missing required clip, or severe continuity defect blocks success.

## Device Profiles

Apply one profile consistently. These are tendencies, not defects that must appear in every shot.

### Auto

Infer the device from era, premise, intimacy, and requested look. State the chosen profile. Prefer the least stylized device that supports the story; do not blend incompatible signatures.

### MiniDV

Use a small consumer camcorder feel: 4:3 when era/context supports it, interlaced-era motion cadence or mild field-like motion texture, limited highlight latitude, modest low-light chroma noise, consumer auto white-balance drift, autofocus searching only during difficult reframing, optical zoom behavior when used, tape/transport character only when motivated, and camera-body handling noise. Do not add constant scanlines, timecode, tape damage, chromatic tearing, or glitches to every shot. A subtle end dropout may be used once when it fits.

### iPhone 4S

Use early-2010s phone-video behavior: small-sensor depth of field, constrained dynamic range, clipped practical highlights, visible low-light noise and color loss, slower exposure/white-balance settling after reframes, occasional focus pumping in difficult contrast, modest stabilization, and compressed built-in-mic sound. Avoid modern computational HDR, extreme stabilization, synthetic portrait blur, or ultra-wide views.

### iPhone 7

Use mid-2010s phone-video behavior: cleaner detail and color than iPhone 4S, improved but not current HDR, believable optical/electronic stabilization, quick auto exposure with occasional brightness stepping, phone-like deep focus, controlled highlights that can still clip, and compact built-in-mic sound. Avoid modern Action-mode smoothness, aggressive multi-lens transitions, or contemporary computational night-video quality.

### Modern iPhone

Use current phone-video behavior: strong stabilization, fast face/exposure tracking, broad computational dynamic range, clean daylight detail, plausible low-light denoising, and clear phone-mic speech with environmental ambience. Preserve human hand movement and exposure decisions; do not make every shot gimbal-smooth, perfectly noise-free, heavily sharpened, or automatically “cinematic.” Use lens switching, HDR halos, focus breathing, or stabilization warping only when the shot conditions plausibly trigger them.

### Ricoh Compact Camera

Treat “Ricoh” honestly as an unspecified Ricoh compact camera, not a named model. Use a compact-camera feel: wider fixed-lens or compact-lens perspective when plausible, deep focus at ordinary distances, crisp center detail, modest handheld stabilization, exposure shifts during movement, practical highlight clipping, and camera-body/built-in-mic handling character. Do not invent a focal length, sensor, film simulation, model-specific color science, or universal GR-series behavior without a supplied model/reference.

## Shared Negative Constraints

Unless explicitly requested, exclude glossy commercial lighting, beauty-ad retouching, heroic slow motion, crane/drone/orbit shots, impossible camera paths, perfect gimbal motion, shallow-focus cinema-lens glamour, trailer montage rhythm, excessive bloom, synthetic film burns, omnipresent VHS overlays, constant glitches, fake timecode, logos/watermarks, identity drift, wardrobe changes, teleporting props, impossible room geometry, time-of-day jumps, mismatched device signatures, reset actions, and discontinuous ambient sound.

## Output Format

For a final-video request, return Markdown in this order:

1. **Delivery Status** — `success`, `blocked`, or `error`; success requires the final requested artifact to have executor `success: true`, a non-empty public URL, and no blocking QA failure.
2. **Video Artifact** — final URL/file and duration, or ordered segment URLs clearly labeled with final stitching `blocked`.
3. **Generation Receipts** — per shot and final assembly: model, parameters, status/message, and public URL; no credentials.
4. **Artifact QA** — continuity, authenticity, safety/rights, audio, and assembly results.
5. **Planning Appendix** — normalized brief, continuity bible, storyboard, internal prompts, stitching plan, and negatives.

For an explicitly planning-only request, return the planning appendix and state that no media was generated. The final sequence may be called complete only after the artifact, receipt, and QA contract is satisfied.


## Seele Workspace case preview

![Authentic Camcorder Vlog case cover](../../assets/cases/authentic-camcorder-vlog.jpg)

[Open Film & CG in Seele Workspace](https://www.seeles.ai/workspace?category=film-cg)
