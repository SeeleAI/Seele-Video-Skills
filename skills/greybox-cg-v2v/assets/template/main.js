// main.js — orchestrator + recording.
//
// Modes (URL params):
//   • preview (default):  /                                          → real-time loop, eyeball the staging
//   • record, frame-grab: /?record=1&fps=24&seconds=8&w=1280&h=720   → DEFAULT record path
//   • record, stream:     …&mode=stream                              → MediaRecorder (opt-in)
//
// Frame-grab is the DEFAULT recording path: the driver asks the page to render one
// deterministic frame at a time and reads it back as a PNG (window.__frame.grab(i)). This is
// robust on headless, GPU-less servers (software WebGL / SwiftShader) where MediaRecorder +
// captureStream are unreliable. `mode=stream` keeps the old MediaRecorder path (window.__cap)
// for environments that prefer it.
//
// WebGL / render failures are surfaced explicitly on window.__cap AND window.__frame so the
// driver reports a clear error instead of hanging until timeout.
//
// You normally edit shot.js (the staging) and greybox.js (the look), not this file.

import * as THREE from 'three';
import { createStage } from './greybox.js';
import { buildShot, updateShot, SHOT } from './shot.js';

const params = new URLSearchParams(location.search);
const RECORD = params.get('record') === '1';
const MODE = params.get('mode') || 'frames'; // 'frames' (default, robust) | 'stream' (MediaRecorder)
const FPS = Math.max(1, parseInt(params.get('fps') || '24', 10));
const SECONDS = parseFloat(params.get('seconds') || String(SHOT.seconds || 8));
const W = parseInt(params.get('w') || '1280', 10);
const H = parseInt(params.get('h') || '720', 10);

// Debug-only revision metadata. These values may be injected by URL params, a host wrapper,
// or a manifest-aware build step. They are not a security source; final V2V must use the
// approved greybox_manifest.json gate instead.
window.__GREYBOX_REVISION_ID__ = params.get('greybox_revision_id') || window.__GREYBOX_REVISION_ID__ || null;
window.__GREYBOX_MANIFEST_URL__ = params.get('greybox_manifest_url') || window.__GREYBOX_MANIFEST_URL__ || null;
window.__GREYBOX_MANIFEST_PATH__ = params.get('greybox_manifest_path') || window.__GREYBOX_MANIFEST_PATH__ || null;
window.__GREYBOX_DEBUG_METADATA__ = {
  revision_id: window.__GREYBOX_REVISION_ID__,
  manifest_url: window.__GREYBOX_MANIFEST_URL__,
  manifest_path: window.__GREYBOX_MANIFEST_PATH__,
  security_source: false,
};

const canvas = document.getElementById('stage');

function publishError(msg) {
  window.__cap = { ready: false, b64: null, mime: null, frames: 0, error: msg };
  window.__frame = { ready: false, total: 0, fps: FPS, error: msg, grab: null };
}

// Create the renderer defensively: on a GPU-less headless server WebGL context creation can
// fail — surface that immediately rather than letting the page hang until the driver times out.
let renderer = null;
let initError = null;
try {
  renderer = new THREE.WebGLRenderer({
    canvas,
    antialias: false, // v2v repaints everything; MSAA is wasted and costly under software WebGL
    preserveDrawingBuffer: true, // required to read pixels back (toDataURL / captureStream)
    failIfMajorPerformanceCaveat: false, // allow software (SwiftShader) rendering, don't bail on "slow"
  });
  if (!renderer || !renderer.getContext()) throw new Error('no WebGL context');
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFShadowMap; // cheap contact shadow; a grey-box needs no soft edges
} catch (e) {
  initError = 'WebGL context creation failed (GPU-less runtime without software WebGL enabled? '
    + 'launch Chromium with --use-gl=angle --use-angle=swiftshader --enable-unsafe-swiftshader): '
    + (e && (e.message || e));
}

if (initError) {
  publishError(initError);
} else {
  const stage = createStage(THREE, { width: RECORD ? W : window.innerWidth, height: RECORD ? H : window.innerHeight });
  buildShot(THREE, stage);

  const resize = (w, h) => {
    renderer.setSize(w, h, false);
    stage.camera.aspect = w / h;
    stage.camera.updateProjectionMatrix();
  };

  const renderFrame = (t) => {
    updateShot(t, stage);
    renderer.render(stage.scene, stage.camera);
  };

  // Frame-grab: render one frame at a time on demand; the driver reads each back as a PNG.
  const setupFrameGrab = () => {
    const total = Math.max(1, Math.round(FPS * SECONDS));
    try {
      renderFrame(0); // render frame 0 now so any WebGL/render failure surfaces before the driver loops
    } catch (e) {
      publishError('render failed on first frame: ' + (e && (e.stack || e)));
      return;
    }
    window.__frame = {
      ready: true,
      total,
      fps: FPS,
      error: null,
      grab(i) {
        renderFrame(i / FPS);
        return canvas.toDataURL('image/png');
      },
    };
  };

  // MediaRecorder path (opt-in via mode=stream) — kept for environments that support it.
  const startStreamRecording = async () => {
    window.__cap = { ready: false, b64: null, mime: null, frames: 0, error: null };
    const stream = canvas.captureStream(0); // 0 = we drive frames manually
    const track = stream.getVideoTracks()[0];
    let mime = 'video/webm;codecs=vp9';
    if (!('MediaRecorder' in window)) throw new Error('MediaRecorder unavailable');
    if (!MediaRecorder.isTypeSupported(mime)) mime = 'video/webm;codecs=vp8';
    if (!MediaRecorder.isTypeSupported(mime)) mime = 'video/webm';
    const rec = new MediaRecorder(stream, { mimeType: mime, videoBitsPerSecond: 12_000_000 });
    const chunks = [];
    rec.ondataavailable = (e) => { if (e.data && e.data.size) chunks.push(e.data); };
    const stopped = new Promise((res) => { rec.onstop = res; });
    rec.start();
    const total = Math.round(FPS * SECONDS);
    for (let i = 0; i < total; i++) {
      renderFrame(i / FPS);
      if (track.requestFrame) track.requestFrame();
      else if (stream.requestFrame) stream.requestFrame();
      window.__cap.frames = i + 1;
      await new Promise((r) => setTimeout(r, Math.max(8, 1000 / FPS)));
    }
    rec.stop();
    await stopped;
    const blob = new Blob(chunks, { type: mime });
    const buf = new Uint8Array(await blob.arrayBuffer());
    let bin = '';
    const CHUNK = 0x8000;
    for (let i = 0; i < buf.length; i += CHUNK) bin += String.fromCharCode.apply(null, buf.subarray(i, i + CHUNK));
    window.__cap.b64 = btoa(bin);
    window.__cap.mime = mime;
    window.__cap.ready = true;
  };

  if (!RECORD) {
    resize(window.innerWidth, window.innerHeight);
    addEventListener('resize', () => resize(window.innerWidth, window.innerHeight));
    const clock = new THREE.Clock();
    (function loop() {
      requestAnimationFrame(loop);
      renderFrame(clock.getElapsedTime() % SECONDS); // loop the shot for preview
    })();
  } else {
    document.body.classList.add('record');
    canvas.width = W; canvas.height = H;
    resize(W, H);
    if (MODE === 'stream') {
      startStreamRecording().catch((e) => publishError('stream capture failed: ' + (e && (e.stack || e))));
    } else {
      setupFrameGrab();
    }
  }
}
