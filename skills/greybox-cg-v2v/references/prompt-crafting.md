# Writing the v2v restyle prompt (the part that decides everything)

The grey-box clip already carries the **structure, motion, camera move, and timing**.
The prompt's whole job is to tell Seedance **what skin to paint onto that skeleton** —
who the grey figure is, what the grey blocks are, and what world/style/light to render.
Get this right and a crude grey-box becomes the reference clip's polished twin; get it
vague and the model invents an inconsistent, flickering scene.

This guide is distilled from how people actually do this trend (Rory Flynn's
three.js→Runway workflow, Seedance 2.0 / Dreamina prompt libraries, Runway/Kling/Luma
official guides) and aligns with Seedance 2.5's official **白模预演 / white-model previz**
framing — the grey-box is a *staging blueprint*, the v2v pass is a *directed render* that
**replaces the subject** rather than keeping the geometry (that's why §1 matters). Read it
before writing any prompt.

Prompt roles are separate:

- `greybox_scene_prompt` drives the Three.js white-model revision and belongs in the manifest through
  `source_prompt_hash`.
- `final_v2v_prompt` is written only after the current revision is explicitly approved and the V2V
  wrapper passes. Do not treat a style tweak or ambiguous approval as permission to call V2V.

---

## 1. The one mental model

> **The reference video is a GREY-BOX: its geometry is a *stand-in*, not the target look.
> It carries only BEHAVIOR — camera move, body motion, timing, trajectory, composition.
> The prompt (and any reference image) carries EVERYTHING VISIBLE — who the subject is and
> what the world looks like. Preserve the behavior; REPLACE the appearance.**

### ⛔ The one rule you must never break

**The preserve / "keep" clause may contain ONLY behavior words** — camera movement, body
motion/footwork, timing/rhythm, trajectory/blocking, framing, composition, screen positions.
**It must NEVER contain an appearance noun** — not *the player, the ball, the character, the
subject, the clothes, the scene*. Every appearance noun belongs in the TRANSFORM clause
("… transforms into …", §4). Putting a subject into the keep clause is the single most common
way to ruin the result:

> ❌ `Keep the same players, ball, dribbling motion, running paths, and camera movement.`
> → "players" and "ball" are **appearance nouns in the keep clause**, so the model *preserves the
> grey primitives* and just re-materials them — you get an ugly glossy box-man in a nice scene,
> not a real footballer. (The camera/motion half was fine; the subject should have been
> **transformed**, not kept. "running paths" also mislabeled the action — juggling in place drifted
> into running forward. See §7.)
>
> ✅ `Keep the camera movement, the footwork and the timing exactly as in the source video. The
> grey figure transforms into a real footballer in a team kit; the grey sphere transforms into a
> leather football.` → behavior preserved, appearance replaced. This is what turns a crude box-man
> into the polished twin — and it's exactly the "组合参考 / combined reference" idea in Seedance's
> own demo (video = motion + camera; the subject is rendered as a *new* character, not the input geometry).

Two more consequences that drive every choice below:

- You barely need to describe motion — the video already encodes it. Spend your words on
  **identity ("the grey figure transforms into a young woman in a white dress") and look
  (style, light, material, era, mood)**.
- You still write ONE preserve sentence so the model doesn't "improve" the camera or re-block the
  scene — but it locks **behavior only** (camera + motion + timing + composition), never appearance.

---

## 2. Map the prompt to the Seedance v2v knobs

The actual call is `ai-model-calling`'s `video_skill.py` (task `seedance_generate`; the dedicated v2v
executor was removed — see `references/v2v-call.md` for the payload). The prompt cooperates with these fields:

| Field | Set it to | Why it matters for grey-box |
|---|---|---|
| `prompt` | the restyle prompt built below | the skin |
| `generate_type` | **always `multimodal_reference`** (with or without a character image) | one mode throughout; it treats any image as a look reference, not a first frame |
| `model_choice` | `seedance2_1080p` (quality) or `seedance2_fast_720p` (iterate) | must be a Seedance 2 choice for reference-video modes; resolution is encoded here |
| `aspect_ratio` | **match the recorded shot's aspect** (`16:9`/`9:16`/…; `ratio` is an alias) | a mismatch crops or re-frames, fighting your composition |
| `duration` | the clip length, **≤10s** | keep shots short; long shots drift/flicker more |
| `camera_fixed` | **`false`** | `true` locks the camera — the opposite of what we want (we want it to FOLLOW the grey-box's camera move) |
| `image_url` / `image_urls` | *(high-fidelity path, with `multimodal_reference`)* a look/character reference image | see §5 — the single biggest quality lever; the clean way to swap the subject |

There is no separate "strength" slider on this interface, so the **prompt's preserve
language + (optionally) a reference image are how you control preserve-vs-transform.**

---

## 3. Prompt anatomy — 6 parts, in this order

Order matters: lock the skeleton first, then describe the skin, then the technical finish.

```
[1 PRESERVE]   Lock motion, camera, blocking, timing, composition.
[2 SUBJECT]    Re-define the grey figure(s): who they are, clothing, hair, build.
[3 STYLE]      Target style + medium (cinematic live-action / 2D anime / 3D / claymation…).
[4 LIGHT]      Direction, colour temperature, time of day, contrast.
[5 SCENE]      Environment, materials, colour palette — what the grey blocks become.
[6 TECH]       Film look, lens, aspect, grain — the finish.
```

**Copy-ready bilingual skeleton** (replace the brackets):

EN:
```
Keep the camera movement, body motion and timing exactly as in the source video (behavior only —
do NOT keep the subject's grey appearance). The grey figure transforms into [subject: person +
clothing + hair + build]; the grey blocks transform into [scene objects + material]. Render as
[style + medium]. Light with [direction + colour temp + time of day]. Set in [environment],
[materials], [colour palette]. [film look + lens + aspect + grain].
```

ZH (Seedance/即梦 friendly):
```
保持源视频的运镜、动作与节奏完全不变（只保留运动，不要保留主体的灰模外观）；灰色人形替换为
[人物+服装+发型+体态]，灰色块替换为[场景物体+材质]；风格为[流派+媒介]；以[方向+色温+时间]布光；
场景设定在[环境]，材质[质感]，色调[调色板]；[片感+镜头+画幅+颗粒]。
```

Keep it **tight** (Seedance sweet spot ≈ 300–500 Chinese chars / a few English sentences).
Short prompts give the model room; overloaded prompts cause conflicts and flicker.

---

## 4. The grey-box move: "transforms into"

The model sees semantically-empty grey geometry. You must **name each placeholder as the
thing it represents** — otherwise it may decide "grey == the target look" and paint concrete.
This is the same technique Runway documents officially ("the pile of rocks transforms into a
humanoid made of volcanic rock").

Use the shot's **legend** (the one-line `SHOT.legend` string in `shot.js`, which lists what
every grey form stands for) as your checklist, and convert it to `transforms into` clauses:

```
The grey running figure transforms into a young woman in a flowing white summer dress, long dark hair.
The long grey deck becomes an old stone bridge. The grey side posts become a broken wooden railing.
The low grey boxes on the horizon become forested green hills. The grey box to the side becomes a red local train.
```

For multiple subjects, anchor by **position** to avoid mix-ups: "the figure on the left
becomes…", "the taller block in the back becomes…".

---

## 5. The high-fidelity path: add a look/character reference image (组合参考)

This is the single biggest quality jump — Seedance's own **多模态参考 / 组合参考 (combined reference)**
mode, and the clean way to genuinely SWAP the subject (图3) instead of re-materialing the grey-box.
You pass, alongside the grey-box clip, a **reference image of who the subject becomes** — via
**`image_url` / `image_urls`** (Ark's `reference_image` role):

1. Get a look/character still: restyle the recorder's `<mp4>_frame0.png` into the finished look, OR use a
   clean character portrait / design directly. (For frame 0, restyle with an image model — nanobanana /
   nanobanana_pro via `ai-model-calling` image generation, rich still-image prompt mapping grey → target.)
2. Upload the still to CDN → public `data.cdn_url`.
3. **Confirm with the user before the (expensive) v2v call.** Show the still inline with markdown image
   syntax — `![restyled look reference](https://static.seeles.ai/…)`, never a bare URL — and ask whether to
   proceed or adjust. If they want changes, revise the still-image prompt, regenerate, re-upload, show again.
   Proceed only once they approve.
4. Call v2v with `video_url` (the grey-box clip, for motion + camera) **and** `image_url` (the approved
   still, for the look/identity). `image_urls` if you have several characters, one ref each.

Now the model isn't guessing what the skin should look like — the reference image shows it, and it holds
across the whole clip along the motion the grey-box defines. Flicker and identity-drift drop sharply.
Offer this path whenever the user wants a polished result or the first plain-prompt pass looked unstable.

**Prompt phrasing — name each reference and its job (视频1 / 图片1 / 图片2 / 音频1).** This is how
Seedance's own examples are written: the prompt explicitly says *what each reference contributes*, and
addresses them by an indexed handle. The references are 1-indexed **per modality, in the order you pass
them**: `video_url` → **视频1 / video 1**; `image_urls[0]` (or `image_url`) → **图片1 / image 1**,
`image_urls[1]` → **图片2**, …; `audio_urls[0]` → **音频1 / audio 1**. So put multiple character refs in
`image_urls` in the order you name them.

Single character (video + one image), structure first then style:
```
参考视频1的运镜、人物动作和节奏；把主体渲染成图片1里的角色（不要保留灰模几何）；
图片1决定角色形象/服装/材质与整体观感；保持视频1的构图、走位与节奏不变。
[一句片感收口：胶片/调色/画幅]
```
```
Use video 1 for the camera move, body motion and timing. Render the subject as the character in image 1
(do NOT keep the grey geometry); image 1 sets the look — character, clothing, materials, colour. Preserve
video 1's framing, blocking and pacing. [one line of style finish].
```
Multiple characters — index each and bind by position (this is the 图3 "组合参考" case):
```
参考视频1的动作和运镜，把左边的主体渲染成图片1里的角色、右边的主体渲染成图片2里的角色；
保持视频1的构图与节奏；[风格/光线/色调]。
```
Keep it short — Seedance dislikes long prompts — don't re-describe the motion (video 1 has it), and note
"**render the subject as** 图片1" (transform), not "keep the subject" (preserve) — the §1 rule.

**Ark mode note — use `image_url`, not `first_frame_url`, as the look anchor.** Volcengine Ark separates
two reference modes: **multimodal-reference** (`reference_video` + `reference_image` + `reference_audio`)
and **first/last-frame** (`first_frame` / `last_frame`). Our `video_url` becomes `reference_video`, so the
mode-clean partner is `image_url` (`reference_image`) — they co-exist. `first_frame_url` is the *other*
mode (it makes the still the literal opening frame); since this skill always passes a reference video,
mixing it in can cause the video reference or the frame to be ignored. Use `first_frame_url` only
deliberately, and if the motion/camera then isn't respected, switch the still to `image_url`.

The still-image prompt is written like a photo caption — full target content, no "preserve"
language (there's nothing to preserve in a still):
```
Editorial film still, a young woman in a white summer dress running across an old stone bridge,
Japanese rural countryside in summer, deep blue sky with towering white cumulus, a red local
train crossing behind, lush green rice paddies, shot on 35mm, warm halation, soft grain, golden afternoon light.
```

---

## 6. Vocabulary library (high-frequency, copy-and-mix)

- **Film / texture**: 35mm film grain · shot on 35mm · 65mm photochemical contrast · warm halation · anamorphic lens flares · soft vignette · subtle grain · bloom · 1990s VHS color bleed · 胶片颗粒 · 漏光 · 宽银幕
- **Lens / DOF**: 35mm / 50mm / 85mm · shallow depth of field · soft background bokeh · 浅景深 · 虚化
- **Camera move** (describe to MATCH the grey-box's move, never to contradict it): slow dolly-in / push-in · tracking / follow · arc / orbit · crane · pan · tilt · handheld · steadicam · 推 / 拉 / 摇 / 移 / 跟 / 环绕
- **Light**: golden hour, warm side light, long shadows · overcast soft light · rim / backlight · chiaroscuro / Rembrandt · volumetric fog / god rays · neon rim · tungsten bounce · 黄金时刻 · 逆光 · 轮廓光 · 体积光
- **Color grade**: teal-and-orange · cool shadows warm highlights · muted / moody · cold blue · warm amber · 青橙调 · 低饱和 · 冷调
- **Style / medium**: cinematic photoreal · Studio Ghibli hand-drawn · clean cel-shaded anime · Moebius / French graphic novel · Blade Runner cyberpunk (neon, rain-slicked) · film noir B&W · Wes Anderson pastel symmetry · claymation / stop-motion · low-poly · 日系 · 吉卜力 · 赛博朋克 · 国风 · 写实电影感 · 黏土定格
- **Mood**: ethereal · dramatic · serene · intimate · nostalgic · mysterious · 宁静 · 怀旧 · 戏剧性
- **Specs**: 2.39:1 / 2.35:1 letterbox · 24fps · 4K · cinematic, stable picture

---

## 7. Pitfalls → how to avoid them

| Failure | Cause | Fix (write this / set this) |
|---|---|---|
| **Subject stays the grey-box (just re-materialed / glossy), NOT replaced by a real character** | **an appearance noun ("the player/subject/character/ball") was put in the *keep* clause** — e.g. "keep the same players" | **never keep the subject.** Move every subject/object to a `transforms into …` clause (§1, §4); for a hard swap add a **character reference image** via `image_url` (§5, 组合参考) and say "render the subject as the reference image" |
| Action drifts (e.g. juggling-in-place → running forward) | motion was *re-described* in words that fight the video (e.g. "running paths", "dribbling motion") | don't re-describe motion — the video carries it. If you must name it, name it **accurately** ("keepie-uppies in place, then the camera orbits"), and never add travel words to an in-place action |
| Camera move gets changed | `camera_fixed=true`, or no preserve line | set `camera_fixed=false`; add "keep the camera movement exactly as in the source" |
| Flicker / "boiling" textures | long clip, dense high-freq detail | shorten (≤10s, ideally 5–8s); add neg "no flickering, no shifting textures"; add a reference image (§5) |
| Structure breaks / composition drifts | prompt didn't lock composition | "do not change the layout, framing, or subject positions"; add a reference image |
| Subject identity drifts (face/clothes morph) | no fixed reference | add a `reference_image` via `image_url` (§5); keep subject description identical; (Seedance) "maintain consistent appearance throughout" |
| Grey skin / dull material survives | placeholder not named | name every grey form with "transforms into [content + material]" (§4) |
| Scene/clothes evolve mid-shot | missing constraints | neg: "morphing, evolving background, changing clothes" |
| Result ignores prompt | overloaded / contradictory (e.g. two light directions) | one light direction; one style; cut words; iterate one change at a time |
| Objects don't grow/shrink with the camera (a subject the camera pushes into stays the same size) | v2v copies motion but resolves scale/parallax weakly | prefer low-parallax camera moves; avoid shots whose whole point is a big scale change; verify by overlaying input over output at low opacity to check the camera/scale matches |

Seedance/即梦 accepts a short negative list; Runway-family models do NOT support negatives
(phrase as positives there). For Seedance, a reusable negative tail:
`不要闪烁、不要变形、不要漂移、不要文字水印、不要改变构图与服装`.

---

## 8. Worked example (the default bridge-runner shot → Japanese summer film)

Legend (from `shot.js`): *subject = young woman running; long deck = stone bridge; side posts
= broken railing; far boxes = forested hills; side box = passing train.*

**v2v prompt** (plain path):
```
Keep the camera movement, the runner's motion, blocking and timing exactly as in the source video.
The grey running figure is a young woman in a flowing white summer dress with long dark hair.
The long grey deck is an old stone bridge; the grey side posts are a weathered broken wooden railing;
the low grey boxes on the horizon are forested green hills; the grey box to the side is a red local train.
Cinematic Japanese countryside in summer — deep blue sky, towering white cumulus, lush green rice paddies.
Warm golden-afternoon light, soft long shadows. Shot on 35mm film, warm halation, teal-and-orange grade,
shallow depth of field, gentle grain, 16:9.
```
**Call**: `generate_type=multimodal_reference`, `model_choice=seedance2_1080p`, `aspect_ratio=16:9`, `duration=8`, `camera_fixed=false`.
For maximum fidelity, restyle frame 0 (or use a character portrait) with the §5 still prompt and pass it as `image_url` (still `multimodal_reference`).

### 8b. Anti-pattern → fix (the football case — a real failure)

Legend: *subject = figure juggling a ball / keepie-uppies in place; the camera orbits around them;
ground = street; blocks = buildings.*

❌ **What failed** (subject kept as grey-box, action drifted to running):
```
Keep the same players, ball, dribbling motion, running paths, and camera movement from the reference
clip. Restyle into a cinematic cyberpunk night street-football scene: rain-slicked asphalt … neon …
```
Two bugs: (1) "keep the same players, ball" → the model kept the grey primitives and just made them
glossy black — no real footballer. (2) "dribbling motion, running paths" → it invented forward running
instead of the in-place juggling the video actually showed.

✅ **Corrected** (behavior kept, subject transformed, action named accurately):
```
Keep the camera orbit, the body motion and the timing exactly as in the source video (behavior only).
The grey figure transforms into a real footballer in a modern team kit, athletic build; the grey
sphere transforms into a leather football; the figure is juggling the ball with their feet, staying
roughly in place while the camera orbits. The grey ground becomes rain-slicked asphalt; the grey
blocks become neon-lit cyberpunk buildings. Cinematic night, magenta-and-cyan neon rim light,
volumetric fog, filmic grade, shallow depth of field, 16:9.
```
**Even better (组合参考):** pass a footballer reference photo (or the restyled frame 0) as `image_url`
(Ark `reference_image`), then keep the prompt to: *"Reference the body motion and camera language from
the video; render the subject as the footballer in the reference image; in-place keepie-uppies while the
camera orbits; rain-slicked cyberpunk street at night, neon."*

### 8c. No character — an environment/camera-driven shot (a city fly-through)

There's no subject to swap; the **camera move is the shot** and every grey block is a building. The
"transform" clause targets the environment; the "preserve" clause still locks only the camera path.
Legend: *ground plane = street; grid of tall grey blocks = skyscrapers; small grey blocks = signage/props.*
```
Keep the camera fly-through path, speed and timing exactly as in the source video (behavior only).
The grey street becomes a rain-slicked asphalt avenue; the tall grey blocks become towering neon
skyscrapers with holographic billboards; the small grey blocks become street signage and traffic lights.
Blade Runner cyberpunk metropolis at night, dense magenta-and-cyan neon, volumetric fog, wet reflections,
anamorphic lens flares, filmic grade, 16:9. No flickering, no morphing, stable picture.
```
These subject-less flythroughs are often the most stable v2v results (no identity to drift). A reference
image (`image_url`) still helps — use it to pin the *architectural style / palette* of the city.

---

## 9. Seedance / 即梦 verbatim phrasings (copy-ready)

These are distilled from how Chinese creators actually write Seedance 2.0 v2v prompts. The core
idiom: **the reference video carries the camera + motion; the prompt mostly names the NEW
subject / scene / style plus one "keep the reference's camera move and rhythm" line — and does
NOT re-describe the motion.** (With our gateway interface the reference clip is the `video_url`,
so you don't need the app's `@视频1`/`@图片1` tags — just describe the new skin and the preserve line.)

**Core swap sentence (ZH, verbatim pattern):**
```
保持参考视频的镜头运动和节奏，将人物替换为[新角色：服装/发型/体态]；将场景替换为[新场景/材质]；
[风格 + 光线 + 色调 + 质感]。
```
More copy-ready ZH building blocks: `参考源视频的运镜和转场效果，利用镜头匹配人物的动作` ·
`其他维持原视频模样` · `让人物保持原视频中的动作` · `保持与源视频相同的镜头角度、光线氛围和背景布局`.

**English swap template (verbatim pattern — structurally identical to "bridge run → Japanese countryside"):**
```
Keep the motion and camera move from the reference video, but transform the grey figure into
[target character] and replace the [grey bridge/countryside] environment with [target scene];
[target lighting]; preserve the original pace, framing and camera tracking distance.
```
(Note: keep MOTION + camera — not "same character". The character is grey, so "same character" would
preserve the grey-box; always *transform* the subject. §1.)

**Quality + negative suffix (append to lock stability — Seedance/即梦 accept these; Runway-family don't):**
```
EN: 4K, ultra HD, rich detail, sharp clarity, cinematic texture, natural colour. No blur, no ghosting,
    no flickering, no identity drift, no distortion, stable picture.
ZH: 4K超高清，电影质感，画面稳定无抖动，面部清晰不变形，五官自然，无拖影无闪烁。
```

**审核 note (relevant because we output a realistic person from a non-real input):** a grey-box clip
is a non-real input, which is an advantage (post-2026 real-face restrictions). To render a realistic
person, describe them as `人物 / 写实 / 实拍 / 质感` rather than the literal word `真人`.

## 10. Checklist before calling v2v

- [ ] One preserve sentence locking camera + motion + composition — **behavior only**.
- [ ] **The preserve clause contains ZERO appearance nouns** — no "keep the same player / subject /
      ball / character / scene" (that keeps the grey-box; §1). Grep your own prompt for "keep the same".
- [ ] Every grey form named via "transforms into …" (cross-check against `SHOT.legend`) — subject included.
- [ ] The action is not re-described with words that fight the video (no "running" on an in-place shot).
- [ ] If the character's identity/look matters → add a **combined reference** image via `image_url`
      (Ark `reference_image`, §5) and phrase it "render the subject as the reference image".
- [ ] Exactly one style, one light direction, one palette.
- [ ] `ratio` matches the recorded aspect; `duration` ≤10; `camera_fixed=false`.
- [ ] Prompt is tight (no contradictions, no wall of text).
- [ ] If polish matters or the first pass was unstable → use the combined-reference path (`image_url`, §5).
