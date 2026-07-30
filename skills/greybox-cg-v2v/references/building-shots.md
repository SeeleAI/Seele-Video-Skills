# Building the grey-box shot (editing the template)

Copy `assets/template/` to a build dir and edit **`shot.js`** — that's the shot. You rarely touch
`main.js` (recording), `greybox.js` (look + builders), or `humanoid.js` (the figure). Keep the
build dir self-contained so the recorder can serve it.

Goal: a clip that is **legible**, not pretty. Make the subject, the action, and the camera move
unmistakable; everything else is the v2v pass's job.

## The contract

`shot.js` exports three things the engine uses:

```js
export const SHOT = {
  seconds: 8,            // duration (≤10); the recorder can override via ?seconds=
  aspect: '16:9',        // pick the aspect you'll record + pass to v2v as ratio
  legend: 'subject = ... ; long deck = ... ; side posts = ...',  // what each grey form REPRESENTS
};
export function buildShot(THREE, stage) { /* create geometry once; stash handles on stage.handles */ }
export function updateShot(t, stage)    { /* pose subject + camera at time t (seconds), deterministic */ }
```

**Keep `SHOT.legend` accurate** — it is your bridge to the prompt. Every grey form you place, you
will name in the v2v prompt via "transforms into …" (see prompt-crafting.md §4). If it's not in the
legend, you'll forget to restyle it and the model will leave it grey.

For a user-requested modification, build from the current manifest revision as canonical `parent_greybox_revision_id` (`parent_revision_id` remains a compatibility alias) and
record the change text in the new manifest's revision request metadata. Do not overwrite an approved or
review-ready revision in place; create a child revision, regenerate the Three.js Preview and greybox
video, and return to review without V2V.

`updateShot(t)` must be a pure function of `t`: derive every position/rotation from `t`, never from
frame deltas or wall-clock. That determinism is what makes the recording smooth.

## Building blocks (from greybox.js)

- **Palette with value separation** — `PALETTE.sky / ground / prop / subject / accent`, lightest→darkest.
  Use them on purpose so v2v can segment the frame (subject darker than ground, sky lightest).
- **Primitive builders** — `box(THREE,w,h,d,value)`, `cyl(...)`, `sphere(...)`, `capsule(...)`,
  `ground(THREE,size,value)`. All matte, shadow-casting.
- **Helpers** — `lerp(a,b,t)`, `ease(t)` (smooth in/out), `clamp01(x)`.

## The humanoid (from humanoid.js)

```js
import { makeHumanoid } from './humanoid.js';
const hero = makeHumanoid(THREE, 'subject');   // { root, hips, head, pose }
stage.scene.add(hero.root);
// each frame:
hero.root.position.set(x, 0.2, z);             // root = ground point between the feet
hero.root.rotation.y = heading;                // 0 faces +Z; rotate to face travel direction
hero.pose(t, { gait: 'run', cadence: 2.7 });   // gait 'run'|'walk', cadence ≈ steps/sec
```

`pose()` drives a walk/run cycle (opposed limb swing, knee bend, torso bob, forward lean for run).
For other actions, build them the same way: parent primitives into joint groups and rotate the
groups from `t` with sines/eases. Correct human proportions + a back/side view give v2v the clearest
"this is a person" signal — keep the figure clearly lit and distinct from the ground.

## Camera moves (deterministic, drive from t)

Author the camera the same way — set `stage.camera.position` and `camera.lookAt(...)` from `t`.
Common moves:

- **Follow / tracking** (default): place the camera at a fixed offset from the subject each frame
  (behind + slightly above) and `lookAt` the subject. Add a tiny `sin(t*…)` bob/sway for a handheld feel.
- **Dolly / push-in**: `lerp` the follow distance over the shot.
- **Orbit**: `camera.position = center + (cos θ, h, sin θ)` with `θ = lerp(θ0, θ1, ease(t/dur))`.
- **Crane / reveal**: `lerp` the camera height while looking at a fixed point.

Prefer **low-parallax moves** if a clean restyle matters: v2v copies camera motion well but resolves
big scale changes weakly (a subject the camera pushes hard into may stay the same apparent size).

## Checklist for a good grey-box clip

- [ ] One clear subject with a readable silhouette (use the humanoid or proportioned primitives).
- [ ] One clear action and one clear camera move, both derived purely from `t`.
- [ ] Distinct grey values: subject vs ground vs sky vs props.
- [ ] A ground plane + sky background (gives v2v a floor and sky to reinterpret).
- [ ] `SHOT.seconds` ≤ 10, `SHOT.aspect` set, `SHOT.legend` matches every grey form you placed.
- [ ] Previewed (open the page without `?record=1`) or frame-checked after recording.
