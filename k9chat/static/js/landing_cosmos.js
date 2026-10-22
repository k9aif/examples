// SPDX-License-Identifier: Apache-2.0
// K9-AIF Framework — K9Chat splash (the "/" page, before the landing page)
//
// Two layers:
//   #vision  WebGL fragment shader: a slow, kaleidoscopic, domain-warped
//            flow (folded symmetry + an endless inward tunnel drift +
//            glowing lattice filaments). Purely atmospheric.
//   #cosmos  2D canvas: K9Chat's real message path as orbits around the
//            model -- rate limit, k9x Shield, Guardian, router. Messages
//            spiral in through each gate and replies flow back out;
//            hostile input (red) is turned away at Shield or Guardian.
//
// Palette stays in indigo / violet / blue / teal with amber sparks (no
// pink). prefers-reduced-motion: one still frame, no animation. If WebGL
// isn't available the CSS gradient on #vision shows instead.

(function () {
  "use strict";

  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const band = document.querySelector("[data-cosmos]");
  if (!band) return;

  // ── Layer 1: the vision (WebGL) ───────────────────────────────────────
  const vision = document.getElementById("vision");
  const gl = vision && (vision.getContext("webgl", { antialias: false, premultipliedAlpha: false }) ||
                        vision.getContext("experimental-webgl"));

  const VERT = `
    attribute vec2 p;
    void main() { gl_Position = vec4(p, 0.0, 1.0); }`;

  const FRAG = `
    precision mediump float;
    uniform vec2  uRes;
    uniform float uTime;
    uniform vec2  uCenter;   // where the core sits, in 0..1 screen space

    float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
    float noise(vec2 p) {
      vec2 i = floor(p), f = fract(p);
      vec2 u = f * f * (3.0 - 2.0 * f);
      return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), u.x),
                 mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), u.x), u.y);
    }
    float fbm(vec2 p) {
      float v = 0.0, a = 0.5;
      mat2 r = mat2(0.8, 0.6, -0.6, 0.8);
      for (int i = 0; i < 5; i++) { v += a * noise(p); p = r * p * 2.03; a *= 0.5; }
      return v;
    }
    // Visionary-art palette: night indigo, violet, jungle green, teal,
    // gold, deep orange. Piecewise so no blend passes through magenta/pink.
    vec3 ramp(float t) {
      t = fract(t);
      vec3 c0 = vec3(0.04, 0.03, 0.14);   // night indigo
      vec3 c1 = vec3(0.30, 0.14, 0.66);   // violet
      vec3 c2 = vec3(0.05, 0.50, 0.30);   // jungle green
      vec3 c3 = vec3(0.10, 0.85, 0.72);   // teal
      vec3 c4 = vec3(0.98, 0.76, 0.22);   // gold
      vec3 c5 = vec3(0.92, 0.38, 0.08);   // deep orange
      if (t < 0.18) return mix(c0, c1, t / 0.18);
      if (t < 0.36) return mix(c1, c0 * 0.6 + c2 * 0.4, (t - 0.18) / 0.18);   // via dark, not via grey-pink
      if (t < 0.52) return mix(c0 * 0.6 + c2 * 0.4, c2, (t - 0.36) / 0.16);
      if (t < 0.68) return mix(c2, c3, (t - 0.52) / 0.16);
      if (t < 0.84) return mix(c3, c4, (t - 0.68) / 0.16);
      if (t < 0.94) return mix(c4, c5, (t - 0.84) / 0.10);
      return mix(c5, c0, (t - 0.94) / 0.06);
    }

    void main() {
      vec2 uv = (gl_FragCoord.xy - uCenter * uRes) / uRes.y;
      float t = uTime * 0.06;

      // polar, folded into a slowly turning kaleidoscope
      float r = length(uv);
      float a = atan(uv.y, uv.x) + t * 0.6;
      float seg = 6.2831853 / 9.0;
      a = mod(a, seg);
      a = abs(a - seg * 0.5);

      // endless inward tunnel: log-radius scrolls with time
      vec2 q = vec2(a * 1.6, log(r + 0.04) * 1.15 - t * 2.2);

      // two levels of domain warping -> serpentine, breathing forms
      vec2 w1 = vec2(fbm(q * 1.4 + vec2(0.0, t)), fbm(q * 1.4 + vec2(5.2, 1.3 - t)));
      vec2 w2 = vec2(fbm(q * 1.9 + 3.0 * w1 + vec2(1.7, 9.2) + t * 0.7),
                     fbm(q * 1.9 + 3.0 * w1 + vec2(8.3, 2.8) - t * 0.5));
      float f = fbm(q * 1.2 + 3.4 * w2);

      // glowing lattice: thin bright contour filaments through the flow
      float lines = abs(fract(f * 7.0 + t * 0.8) - 0.5);
      float filament = smoothstep(0.05, 0.0, lines) * smoothstep(0.15, 0.6, f);

      // serpent bands: ribbons winding through the warp, with a scale pattern
      float band = sin(q.x * 5.0 + w2.y * 6.0 - q.y * 1.3 + t * 2.0);
      float serpent = smoothstep(0.70, 0.98, band);
      float scales = 0.6 + 0.4 * sin(q.y * 38.0 + w1.x * 10.0) * sin(q.x * 30.0);

      // eye rosettes: concentric rings blooming in each kaleidoscope cell
      vec2 cell = vec2(a * 3.2, fract(log(r + 0.04) * 1.6 - t * 1.4) - 0.5);
      float rd = length(cell - vec2(0.42, 0.0));
      float eye = smoothstep(0.20, 0.0, rd) * (0.5 + 0.5 * sin(rd * 70.0 - uTime * 2.0));
      float pupil = smoothstep(0.045, 0.02, rd);

      vec3 col = ramp(f * 1.35 + 0.25 * w2.x + 0.12 * sin(t * 1.7 + r * 3.0));
      col *= 0.45 + 0.95 * f * f;
      col = mix(col, ramp(0.6 + 0.3 * w1.y) * scales * 1.15, serpent * 0.75);
      col += eye * mix(vec3(0.98, 0.76, 0.22), vec3(0.10, 0.85, 0.72), 0.5 + 0.5 * sin(t * 3.0 + a * 9.0)) * 0.55;
      col = mix(col, vec3(0.02, 0.02, 0.06), pupil * 0.85);
      col += filament * mix(vec3(0.10, 0.85, 0.72), vec3(0.98, 0.76, 0.22), 0.5 + 0.5 * sin(t * 2.3 + f * 6.0)) * 0.6;

      // breathing light at the core, vignette at the edges
      float breathe = 0.5 + 0.5 * sin(uTime * 0.9);
      col += vec3(0.30, 0.42, 0.95) * exp(-r * (5.5 - breathe)) * 0.55;
      col *= smoothstep(1.45, 0.15, r);
      gl_FragColor = vec4(col * 0.92, 1.0);
    }`;

  let program = null, uRes, uTime, uCenter;
  if (gl) {
    const compile = (type, src) => {
      const sh = gl.createShader(type);
      gl.shaderSource(sh, src);
      gl.compileShader(sh);
      if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
        console.warn("[landing] shader:", gl.getShaderInfoLog(sh));
        return null;
      }
      return sh;
    };
    const vs = compile(gl.VERTEX_SHADER, VERT), fs = compile(gl.FRAGMENT_SHADER, FRAG);
    if (vs && fs) {
      program = gl.createProgram();
      gl.attachShader(program, vs);
      gl.attachShader(program, fs);
      gl.linkProgram(program);
      if (!gl.getProgramParameter(program, gl.LINK_STATUS)) { program = null; }
    }
    if (program) {
      gl.useProgram(program);
      const buf = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, buf);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
      const loc = gl.getAttribLocation(program, "p");
      gl.enableVertexAttribArray(loc);
      gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
      uRes = gl.getUniformLocation(program, "uRes");
      uTime = gl.getUniformLocation(program, "uTime");
      uCenter = gl.getUniformLocation(program, "uCenter");
    }
  }

  // ── Layer 2: the architecture (2D) ────────────────────────────────────
  const cosmos = document.getElementById("cosmos");
  const ctx = cosmos.getContext("2d");

  // Outside in, the order a message really meets them (see "What happens
  // to a message" on the page). Replies leave through Shield (out).
  const RINGS = [
    { name: "RATE LIMIT", f: 1.00, color: [140, 170, 255], spin: 0.05, dash: [2, 10] },
    { name: "K9X SHIELD", f: 0.78, color: [45, 212, 191], spin: -0.08, dash: [14, 8] },
    { name: "GUARDIAN",   f: 0.58, color: [167, 139, 250], spin: 0.11, dash: [4, 6] },
    { name: "ROUTER",     f: 0.40, color: [96, 165, 250], spin: -0.15, dash: [24, 6, 2, 6] },
  ];
  const CORE_F = 0.20;

  let W = 0, H = 0, DPR = 1, cx = 0, cy = 0, R = 0;
  const particles = [], sparks = [];
  RINGS.forEach(r => { r.glow = 0; r.hit = 0; });
  let coreGlow = 0;

  function layout() {
    const rect = band.getBoundingClientRect();
    W = rect.width; H = rect.height;
    DPR = Math.min(window.devicePixelRatio || 1, 2);
    cosmos.width = Math.round(W * DPR); cosmos.height = Math.round(H * DPR);
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    const narrow = W < 860;
    cx = narrow ? W * 0.5 : W * 0.66;
    cy = narrow ? H * 0.36 : H * 0.5;
    R = Math.min(narrow ? W * 0.42 : W * 0.25, H * (narrow ? 0.27 : 0.40));
    if (gl && program) {
      const s = 0.6;   // the vision renders at reduced resolution, scaled up by CSS
      vision.width = Math.round(W * s); vision.height = Math.round(H * s);
      gl.viewport(0, 0, vision.width, vision.height);
      gl.uniform2f(uRes, vision.width, vision.height);
      gl.uniform2f(uCenter, cx / W, 1 - cy / H);
    }
  }

  function spawn() {
    const hostile = Math.random() < 0.22;
    particles.push({
      a: Math.random() * Math.PI * 2,
      r: R * 1.25,
      dir: -1,                                   // inward
      hostile,
      stopAt: hostile ? (Math.random() < 0.6 ? 1 : 2) : -1,   // ring index that turns it away
      speed: 0.32 + Math.random() * 0.18,
      swirl: (Math.random() < 0.5 ? -1 : 1) * (0.45 + Math.random() * 0.35),
      trail: [],
      life: 1,
      passed: new Set(),
    });
  }

  function burst(x, y, rgb, n) {
    for (let i = 0; i < n; i++) {
      const a = Math.random() * Math.PI * 2, v = 30 + Math.random() * 90;
      sparks.push({ x, y, vx: Math.cos(a) * v, vy: Math.sin(a) * v, life: 1, rgb });
    }
  }

  const rgba = (c, a) => `rgba(${c[0]},${c[1]},${c[2]},${a})`;

  function drawRings(time) {
    ctx.save();
    ctx.globalCompositeOperation = "lighter";
    for (const ring of RINGS) {
      const rr = R * ring.f * (1 + 0.012 * Math.sin(time * 0.8 + ring.f * 9));
      ring.glow *= 0.94; ring.hit *= 0.92;
      // soft halo
      ctx.lineWidth = 8;
      ctx.strokeStyle = rgba(ring.color, 0.05 + ring.glow * 0.25);
      ctx.beginPath(); ctx.arc(cx, cy, rr, 0, Math.PI * 2); ctx.stroke();
      // dark under-stroke so the orbit reads over the busy background
      ctx.save();
      ctx.globalCompositeOperation = "source-over";
      ctx.lineWidth = 4;
      ctx.strokeStyle = "rgba(3,5,12,0.55)";
      ctx.beginPath(); ctx.arc(cx, cy, rr, 0, Math.PI * 2); ctx.stroke();
      ctx.restore();
      // dashed orbit, slowly turning
      ctx.save();
      ctx.translate(cx, cy); ctx.rotate(time * ring.spin);
      ctx.setLineDash(ring.dash);
      ctx.lineWidth = 2;
      ctx.strokeStyle = rgba(ring.hit > 0.05 ? [248, 113, 113] : ring.color, 0.45 + ring.glow * 0.5 + ring.hit * 0.5);
      ctx.beginPath(); ctx.arc(0, 0, rr, 0, Math.PI * 2); ctx.stroke();
      ctx.restore();
      // label above the orbit, on a dark plate
      ctx.setLineDash([]);
      ctx.font = "700 10.5px ui-monospace, Menlo, Consolas, monospace";
      ctx.textAlign = "center";
      const tw = ctx.measureText(ring.name).width + 12;
      ctx.save();
      ctx.globalCompositeOperation = "source-over";
      ctx.fillStyle = "rgba(3,5,12,0.72)";
      ctx.fillRect(cx - tw / 2, cy - rr - 19, tw, 16);
      ctx.restore();
      ctx.fillStyle = rgba(ring.color, 0.9 + ring.glow * 0.1);
      ctx.fillText(ring.name, cx, cy - rr - 7);
    }
    // the core: the model
    coreGlow *= 0.93;
    const cr = R * CORE_F * (1 + 0.05 * Math.sin(time * 0.9));
    const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, cr * 2.4);
    g.addColorStop(0, `rgba(255,236,190,${0.85 + coreGlow * 0.15})`);
    g.addColorStop(0.25, `rgba(140,170,255,${0.55 + coreGlow * 0.3})`);
    g.addColorStop(1, "rgba(60,40,160,0)");
    ctx.fillStyle = g;
    ctx.beginPath(); ctx.arc(cx, cy, cr * 2.4, 0, Math.PI * 2); ctx.fill();
    ctx.restore();
    ctx.font = "700 11px ui-monospace, Menlo, Consolas, monospace";
    ctx.textAlign = "center";
    ctx.fillStyle = "rgba(10,14,30,0.9)";
    ctx.fillText("MODEL", cx, cy + 4);
  }

  function step(dt, time) {
    for (let i = particles.length - 1; i >= 0; i--) {
      const p = particles[i];
      const prevR = p.r;
      p.a += p.swirl * dt * (p.dir < 0 ? 1 : 0.35);
      p.r += p.dir * p.speed * R * dt;
      const x = cx + Math.cos(p.a) * p.r, y = cy + Math.sin(p.a) * p.r;
      p.trail.push([x, y]);
      if (p.trail.length > 26) p.trail.shift();

      RINGS.forEach((ring, idx) => {
        const rr = R * ring.f;
        const crossed = (prevR - rr) * (p.r - rr) <= 0;
        if (!crossed || p.passed.has(idx + (p.dir > 0 ? 10 : 0))) return;
        p.passed.add(idx + (p.dir > 0 ? 10 : 0));
        if (p.dir < 0 && p.hostile && idx === p.stopAt) {
          ring.hit = 1;
          burst(x, y, [248, 113, 113], 14);
          p.dir = 1; p.speed *= 1.6; p.swirl *= -0.4; p.repelled = true;
        } else if (p.dir < 0 || (p.reply && idx === 1)) {
          // inbound messages light every gate they pass; replies light
          // only Shield (its egress check); turned-away input lights none
          ring.glow = Math.min(1, ring.glow + 0.6);
        }
      });

      if (p.dir < 0 && p.r <= R * CORE_F) {
        coreGlow = 1;
        burst(cx, cy, [255, 214, 140], 8);
        p.dir = 1; p.reply = true; p.speed = 0.55; p.swirl *= 0.2;
      }
      if (p.dir > 0 && p.r > R * 1.35) p.life -= dt * 2.5;
      if (p.life <= 0) particles.splice(i, 1);
    }
    for (let i = sparks.length - 1; i >= 0; i--) {
      const s = sparks[i];
      s.x += s.vx * dt; s.y += s.vy * dt; s.vx *= 0.94; s.vy *= 0.94;
      s.life -= dt * 1.6;
      if (s.life <= 0) sparks.splice(i, 1);
    }
  }

  function drawParticles() {
    ctx.save();
    ctx.globalCompositeOperation = "lighter";
    for (const p of particles) {
      const c = p.hostile ? [248, 113, 113] : p.reply ? [45, 212, 191] : [190, 210, 255];
      for (let k = 1; k < p.trail.length; k++) {
        const a = (k / p.trail.length) * 0.55 * p.life;
        ctx.strokeStyle = rgba(c, a);
        ctx.lineWidth = 1 + (k / p.trail.length) * 2.2;
        ctx.beginPath();
        ctx.moveTo(p.trail[k - 1][0], p.trail[k - 1][1]);
        ctx.lineTo(p.trail[k][0], p.trail[k][1]);
        ctx.stroke();
      }
      const head = p.trail[p.trail.length - 1];
      if (head) {
        const halo = ctx.createRadialGradient(head[0], head[1], 0, head[0], head[1], 11);
        halo.addColorStop(0, rgba(c, 0.9 * p.life));
        halo.addColorStop(1, rgba(c, 0));
        ctx.fillStyle = halo;
        ctx.beginPath(); ctx.arc(head[0], head[1], 11, 0, Math.PI * 2); ctx.fill();
      }
    }
    ctx.globalCompositeOperation = "source-over";
    for (const p of particles) {
      const head = p.trail[p.trail.length - 1];
      if (!head) continue;
      const c = p.hostile ? [248, 113, 113] : p.reply ? [45, 212, 191] : [235, 242, 255];
      ctx.fillStyle = "rgba(3,5,12,0.75)";
      ctx.beginPath(); ctx.arc(head[0], head[1], 4.6, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = rgba(c, p.life);
      ctx.beginPath(); ctx.arc(head[0], head[1], 3.2, 0, Math.PI * 2); ctx.fill();
    }
    ctx.globalCompositeOperation = "lighter";
    for (const s of sparks) {
      ctx.fillStyle = rgba(s.rgb, s.life);
      ctx.beginPath(); ctx.arc(s.x, s.y, 1.6, 0, Math.PI * 2); ctx.fill();
    }
    ctx.restore();
  }

  let last = performance.now(), spawnClock = 0, visible = true, warp = 1, warpTime = 0;
  const start = last;

  // Enter: the tunnel speeds up and every orbit flares while the page
  // fades into the core (splash.html handles the fade and navigation).
  window.K9Cosmos = {
    dive() {
      warp = 9;
      RINGS.forEach(r => { r.glow = 1; });
      coreGlow = 1;
      document.body.style.setProperty("--cx", `${(cx / W) * 100}%`);
      document.body.style.setProperty("--cy", `${(cy / H) * 100}%`);
    },
  };

  function frame(now) {
    const dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    const time = (now - start) / 1000;
    warpTime += dt * warp;
    if (gl && program) {
      gl.uniform1f(uTime, warpTime + 40.0);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    }
    spawnClock += dt;
    if (spawnClock > 0.85) { spawnClock = 0; spawn(); }
    step(dt, time);
    ctx.clearRect(0, 0, W, H);
    drawRings(time);
    drawParticles();
    if (visible) requestAnimationFrame(frame);
  }

  if (reduceMotion) {
    // One still frame: the vision, the orbits, and a few messages in flight.
    // Re-drawn after every resize, because resizing a canvas clears it.
    const still = () => {
      layout();
      if (gl && program) { gl.uniform1f(uTime, 52.0); gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4); }
      particles.length = 0; sparks.length = 0;
      for (let i = 0; i < 6; i++) {
        spawn();
        const p = particles[particles.length - 1];
        p.hostile = i === 2; p.stopAt = 1;
        p.r = R * (1.2 - i * 0.12);
        p.a = i * 1.05;
      }
      for (let k = 0; k < 24; k++) step(0.03, 0);
      ctx.clearRect(0, 0, W, H);
      drawRings(0);
      drawParticles();
    };
    still();
    window.addEventListener("resize", still);
    return;
  }

  layout();
  window.addEventListener("resize", layout);

  // Stop drawing while the hero is off screen or the tab is hidden.
  const io = new IntersectionObserver(entries => {
    const was = visible;
    visible = entries[0].isIntersecting && !document.hidden;
    if (visible && !was) { last = performance.now(); requestAnimationFrame(frame); }
  });
  io.observe(band);
  document.addEventListener("visibilitychange", () => {
    const was = visible;
    visible = !document.hidden && band.getBoundingClientRect().bottom > 0;
    if (visible && !was) { last = performance.now(); requestAnimationFrame(frame); }
  });
  requestAnimationFrame(frame);
})();
