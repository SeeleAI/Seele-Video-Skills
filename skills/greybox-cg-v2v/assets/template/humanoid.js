// humanoid.js — a proportioned humanoid built from primitives, animated by code.
//
// No rigging, no asset files: just boxes/capsules/sphere parented into joint groups,
// posed every frame by sine-wave locomotion. The point is a SILHOUETTE the v2v model
// reads unmistakably as a walking/running person — correct human proportions
// (~7.5 heads tall), limbs that swing in opposition, a bobbing torso, a forward lean
// for running. Get the silhouette right and the model will paint a convincing person
// onto it; get it wrong (stiff, T-posed, wrong proportions) and the person drifts.
//
// Usage in shot.js:
//   const h = makeHumanoid(THREE);            // returns { root, pose }
//   stage.scene.add(h.root);
//   // each frame:
//   h.pose(t, { gait: 'run', cadence: 2.6, stride: 0.55 });
//   h.root.position.copy(somePathPoint);
//   h.root.rotation.y = headingAngle;

import { capsule, box, sphere } from './greybox.js';

export function makeHumanoid(THREE, value = 'subject') {
  const root = new THREE.Group();          // ground point between the feet
  const hips = new THREE.Group(); root.add(hips); hips.position.y = 0.95;

  const pelvis = capsule(THREE, 0.17, 0.16, value); pelvis.rotation.z = Math.PI / 2; hips.add(pelvis);
  const torso = capsule(THREE, 0.19, 0.42, value); torso.position.y = 0.42; hips.add(torso);
  const head = sphere(THREE, 0.14, value); head.position.y = 0.86; hips.add(head);
  const neck = capsule(THREE, 0.06, 0.08, value); neck.position.y = 0.72; hips.add(neck);

  // arm = shoulder group (pivot) -> upper + forearm
  function arm(side) {
    const sh = new THREE.Group(); sh.position.set(0.22 * side, 0.6, 0); hips.add(sh);
    const upper = capsule(THREE, 0.06, 0.26, value); upper.position.y = -0.16; sh.add(upper);
    const elbow = new THREE.Group(); elbow.position.y = -0.32; sh.add(elbow);
    const fore = capsule(THREE, 0.05, 0.24, value); fore.position.y = -0.15; elbow.add(fore);
    return { sh, elbow };
  }
  // leg = hip group (pivot) -> thigh + shin + foot
  function leg(side) {
    const hp = new THREE.Group(); hp.position.set(0.11 * side, 0, 0); hips.add(hp);
    const thigh = capsule(THREE, 0.085, 0.34, value); thigh.position.y = -0.24; hp.add(thigh);
    const knee = new THREE.Group(); knee.position.y = -0.48; hp.add(knee);
    const shin = capsule(THREE, 0.07, 0.32, value); shin.position.y = -0.2; knee.add(shin);
    const foot = box(THREE, 0.1, 0.06, 0.24, value); foot.position.set(0, -0.4, 0.06); knee.add(foot);
    return { hp, knee };
  }
  const armL = arm(+1), armR = arm(-1);
  const legL = leg(+1), legR = leg(-1);

  function pose(t, opts = {}) {
    const gait = opts.gait || 'run';
    const cadence = opts.cadence ?? (gait === 'run' ? 2.6 : 1.6); // steps/sec-ish
    const swing = gait === 'run' ? 0.95 : 0.5;                    // limb amplitude
    const phase = t * cadence * Math.PI * 2;
    const s = Math.sin(phase), c = Math.cos(phase);

    // legs swing in opposition; knees bend on the back-swing
    legL.hp.rotation.x = s * swing;
    legR.hp.rotation.x = -s * swing;
    legL.knee.rotation.x = Math.max(0, -s) * (gait === 'run' ? 1.5 : 0.9) + 0.15;
    legR.knee.rotation.x = Math.max(0, s) * (gait === 'run' ? 1.5 : 0.9) + 0.15;

    // arms counter-swing to the legs; elbows bent more when running
    armL.sh.rotation.x = -s * swing * 0.9;
    armR.sh.rotation.x = s * swing * 0.9;
    const elbowBend = gait === 'run' ? 1.1 : 0.4;
    armL.elbow.rotation.x = -elbowBend;
    armR.elbow.rotation.x = -elbowBend;

    // torso: vertical bob (twice per stride) + forward lean for running
    hips.position.y = 0.95 + Math.abs(c) * (gait === 'run' ? 0.06 : 0.03);
    hips.rotation.x = gait === 'run' ? 0.22 : 0.06;
    // subtle shoulder/hip counter-rotation makes it feel alive
    hips.rotation.y = s * 0.08;
  }

  return { root, hips, head, pose };
}
