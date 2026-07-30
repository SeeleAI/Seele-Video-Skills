// greybox.js — the grey-box LOOK and reusable builders.
//
// The render quality here does NOT need to be pretty — the final image comes from
// the video-to-video pass. What it DOES need is to be *legible* to that model:
//
//   1. VALUE SEPARATION. Sky, ground, the subject, and props each get a distinct
//      grey value. A v2v model segments the frame by edges and value; if everything
//      is the same flat grey it cannot tell the runner from the road. So we ship a
//      small palette of greys and use them on purpose.
//   2. CLEAR SILHOUETTES. One soft key light + fill + ambient so forms read as 3D
//      volumes with gentle shading, plus a contact shadow to anchor things to the
//      ground. Avoid pure-flat shading (no depth cues) and avoid harsh black shadows
//      (the model paints detail into mid-tones, not crushed blacks).
//   3. A REAL HORIZON. A ground plane + a sky background give the model a floor and
//      a sky to reinterpret (grass/water/asphalt and clouds/sunset). Without them it
//      invents an inconsistent background that flickers shot-to-shot.
//
// You rarely need to edit this file; compose scenes in shot.js using these helpers.

export const PALETTE = {
  sky:     0xdfe3e8, // lightest — reads as "sky / bright background"
  ground:  0xc4c6c9, // light-mid — reads as "floor / road / terrain"
  prop:    0xaab0b6, // mid — set dressing, architecture
  subject: 0x949aa1, // mid-dark — the hero; darker so it pops against ground+sky
  accent:  0x7c828a, // darkest — small focal details
};

export function createStage(THREE, { width, height }) {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(PALETTE.sky);
  // gentle depth haze so distant geometry melts toward the sky value (helps the
  // model read depth and keeps far props from looking like hard cardboard cutouts)
  scene.fog = new THREE.Fog(PALETTE.sky, 22, 90);

  const camera = new THREE.PerspectiveCamera(38, width / height, 0.1, 500);
  camera.position.set(0, 1.6, 6);

  // Key (sun) — angled for readable form modeling. A small shadow map is deliberate:
  // headless software-WebGL (SwiftShader) spends most of its time on the shadow pass, and
  // v2v repaints all lighting anyway — we only need a soft contact shadow to anchor the
  // subject to the ground and keep subject/ground values distinct. 512 is plenty; 2048 was
  // ~16x the fill cost for zero benefit to the restyle. (Tune up only if grounding reads poorly.)
  const key = new THREE.DirectionalLight(0xffffff, 2.4);
  key.position.set(6, 10, 4);
  key.castShadow = true;
  key.shadow.mapSize.set(512, 512);
  key.shadow.camera.near = 1; key.shadow.camera.far = 60;
  const s = 24;
  key.shadow.camera.left = -s; key.shadow.camera.right = s;
  key.shadow.camera.top = s; key.shadow.camera.bottom = -s;
  key.shadow.bias = -0.0004;
  scene.add(key);
  // Fill + ambient so shadow sides still show form (no crushed blacks).
  const fill = new THREE.DirectionalLight(0xffffff, 0.6);
  fill.position.set(-5, 4, -2);
  scene.add(fill);
  scene.add(new THREE.HemisphereLight(0xffffff, 0x9098a0, 0.7));

  return { scene, camera, THREE, lights: { key, fill }, handles: {} };
}

// ---- primitive builders -------------------------------------------------------
// Matte, non-metal materials. `value` picks a grey from PALETTE (or pass a hex).

function mat(THREE, value) {
  const color = typeof value === 'number' ? value : (PALETTE[value] ?? PALETTE.prop);
  return new THREE.MeshStandardMaterial({ color, roughness: 0.92, metalness: 0.0 });
}

export function box(THREE, w, h, d, value = 'prop') {
  const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat(THREE, value));
  m.castShadow = true; m.receiveShadow = true;
  return m;
}
export function cyl(THREE, rTop, rBot, h, value = 'prop', seg = 16) {
  const m = new THREE.Mesh(new THREE.CylinderGeometry(rTop, rBot, h, seg), mat(THREE, value));
  m.castShadow = true; m.receiveShadow = true;
  return m;
}
export function sphere(THREE, r, value = 'prop', seg = 24) {
  const m = new THREE.Mesh(new THREE.SphereGeometry(r, seg, seg), mat(THREE, value));
  m.castShadow = true; m.receiveShadow = true;
  return m;
}
export function capsule(THREE, r, len, value = 'subject') {
  const m = new THREE.Mesh(new THREE.CapsuleGeometry(r, len, 6, 14), mat(THREE, value));
  m.castShadow = true; m.receiveShadow = true;
  return m;
}
export function ground(THREE, size = 400, value = 'ground') {
  const m = new THREE.Mesh(new THREE.PlaneGeometry(size, size), mat(THREE, value));
  m.rotation.x = -Math.PI / 2; m.receiveShadow = true;
  return m;
}

// Smooth ease + tiny helpers shots use for hand-authored motion.
export const ease = (x) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);
export const lerp = (a, b, t) => a + (b - a) * t;
export const clamp01 = (x) => Math.min(1, Math.max(0, x));
