// shot.js — THE shot. This is the file you rewrite for each new request.
//
// A shot is just: some grey-box geometry + a function that poses everything at a
// given time `t` (seconds). Keep it SHORT (<= 10s — the v2v limit) and make three
// things unmistakable, because they are the only things the v2v model can preserve:
//   • the SUBJECT and its silhouette,
//   • the ACTION / motion,
//   • the CAMERA move.
// Everything else (textures, real geometry, lighting polish) is the v2v pass's job.
//
// Two exports the engine calls:
//   buildShot(THREE, stage)      — create geometry once
//   updateShot(t, stage)         — pose subject + camera at time t  (t in [0, SHOT.seconds])
// SHOT.seconds is the default duration; the recorder can override via ?seconds=.
//
// ---------------------------------------------------------------------------
// DEFAULT SHOT (matches the reference clip): a runner crosses a ruined bridge over
// a gorge toward distant hills; the camera follows from behind, slightly high, with
// a gentle hand-held bob and a slow push-in. Back view = a clean running silhouette.
// ---------------------------------------------------------------------------

import { makeHumanoid } from './humanoid.js';
import { box, cyl, ground, lerp, ease, clamp01 } from './greybox.js';

export const SHOT = {
  seconds: 8,
  aspect: '16:9',
  // A one-line description of what each grey form REPRESENTS. Keep this in sync with
  // the geometry — the v2v prompt is written from it (see references/prompt-crafting.md).
  legend: 'subject = young woman running; long deck = stone bridge; side posts = broken railing; far low boxes = forested hills; low side box = a passing train',
};

const RUN_FROM = -3;   // start Z of the runner
const RUN_TO = 34;     // end Z   (≈ distance covered in SHOT.seconds)

export function buildShot(THREE, stage) {
  const { scene } = stage;

  // valley floor far below the bridge -> reads as a gorge / river bed
  const floor = ground(THREE, 600, 'ground');
  floor.position.y = -7;
  scene.add(floor);

  // bridge deck: a long box the subject runs along
  const deck = box(THREE, 4, 0.4, 90, 'prop');
  deck.position.set(0, 0, 38);
  scene.add(deck);

  // broken railing: posts down both sides, a few deliberately missing ("ruined")
  const missing = new Set([3, 4, 11, 18, 19]);
  for (let i = 0; i < 26; i++) {
    if (missing.has(i)) continue;
    const z = -6 + i * 3.4;
    for (const side of [-1, 1]) {
      const post = box(THREE, 0.16, lerp(0.9, 1.1, (i % 3) / 2), 0.16, 'accent');
      post.position.set(side * 1.9, 0.6, z);
      scene.add(post);
    }
  }

  // distant forested hills near the horizon (sit in the fog so they read as far)
  for (let i = 0; i < 7; i++) {
    const hill = box(THREE, lerp(14, 26, Math.random()), lerp(5, 11, (i % 4) / 3), 8, 'prop');
    hill.position.set(lerp(-40, 40, i / 6) + (i % 2 ? 6 : -6), -3, lerp(70, 92, (i % 3) / 2));
    scene.add(hill);
  }

  // a passing train low to the side (set dressing — gives the v2v a recognizable object)
  const train = box(THREE, 2.2, 1.6, 22, 'accent');
  train.position.set(13, -4.2, 50);
  scene.add(train);

  // the subject
  const hero = makeHumanoid(THREE, 'subject');
  scene.add(hero.root);

  stage.handles.hero = hero;
  stage.handles.train = train;
}

export function updateShot(t, stage) {
  const { camera, handles } = stage;
  const dur = SHOT.seconds;
  const p = clamp01(t / dur);

  // --- subject: run forward along +Z (eased start so she accelerates into frame) ---
  const hero = handles.hero;
  const z = lerp(RUN_FROM, RUN_TO, ease(clamp01(t / dur)));
  hero.root.position.set(0, 0.2, z);   // 0.2 = bridge deck top
  hero.root.rotation.y = 0;            // facing +Z, i.e. away from camera (back view)
  hero.pose(t, { gait: 'run', cadence: 2.7, stride: 0.6 });

  // train drifts slowly the other way
  handles.train.position.z = 50 - t * 1.5;

  // --- camera: follow from behind + slightly above, hand-held bob, slow push-in ---
  const bobY = Math.sin(t * 6.5) * 0.04;
  const swayX = Math.sin(t * 2.1) * 0.12;
  const dist = lerp(3.6, 2.9, p);      // gentle push-in over the shot
  camera.position.set(
    hero.root.position.x + swayX,
    hero.root.position.y + 1.55 + bobY,
    hero.root.position.z - dist,        // behind (smaller Z)
  );
  camera.lookAt(hero.root.position.x, hero.root.position.y + 1.05, hero.root.position.z + 1.5);
}
