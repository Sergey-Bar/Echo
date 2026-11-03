// Live city: the demo scenario, played with the same rules (BFS noise, shortest-path routes, threshold).
(() => {
  const canvas = document.getElementById("city"), ctx = canvas.getContext("2d");
  const button = document.getElementById("toggle"), frameLabel = document.getElementById("frame");
  const firingLabel = document.getElementById("firing");
  const { detectors, threshold, n_frames } = DEMO;
  const model = buildModel(DEMO);  // the tested rules: see docs/model.js and tests/test_demo_page.py
  const { H, W, open, isOpen, MOVES, tracks, noiseAt } = model;
  const cell = Math.floor(Math.min(1280 / W, 800 / H)), CW = W * cell, CH = H * cell;
  let dpr = 1, streets = null, buildings = null;  // sized by setup(), again whenever the pixel density changes
  const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  const C = {
    street: css("--street"), lane: css("--lane"), roof: css("--building"), roofEdge: css("--building-edge"),
    roofUnit: css("--building-unit"), ink: css("--ink"), amber: css("--amber"), white: css("--white"),
  };

  function layer(draw) {  // an offscreen canvas at the same resolution as the visible one
    const c = document.createElement("canvas");
    c.width = canvas.width; c.height = canvas.height;
    const g = c.getContext("2d");
    g.scale(dpr, dpr); draw(g);
    return c;
  }
  // Streets: asphalt with dashed centre lines down the middle of two-lane roads.
  const drawStreets = g => {
    g.fillStyle = C.street; g.fillRect(0, 0, CW, CH);
    g.strokeStyle = C.lane; g.lineWidth = Math.max(1, cell * 0.08); g.setLineDash([cell * 0.5, cell * 0.5]);
    g.beginPath();
    for (let r = 0; r + 1 < H; r++) for (let c = 0; c < W; c++) {  // horizontal road: two open rows, walls both sides
      if (isOpen(r, c) && isOpen(r + 1, c) && !isOpen(r - 1, c) && !isOpen(r + 2, c)) {
        g.moveTo(c * cell, (r + 1) * cell); g.lineTo((c + 1) * cell, (r + 1) * cell);
      }
    }
    for (let c = 0; c + 1 < W; c++) for (let r = 0; r < H; r++) {  // vertical road
      if (isOpen(r, c) && isOpen(r, c + 1) && !isOpen(r, c - 1) && !isOpen(r, c + 2)) {
        g.moveTo((c + 1) * cell, r * cell); g.lineTo((c + 1) * cell, (r + 1) * cell);
      }
    }
    g.stroke();
  };
  // Buildings: flat roofs, a darker parapet on every street-facing edge, and a few rooftop units.
  const drawBuildings = g => {
    g.fillStyle = C.roof;
    for (let r = 0; r < H; r++) for (let c = 0; c < W; c++) if (!open[r][c]) g.fillRect(c * cell, r * cell, cell, cell);
    const edge = Math.max(2, cell * 0.14);
    g.fillStyle = C.roofEdge;
    for (let r = 0; r < H; r++) for (let c = 0; c < W; c++) {
      if (open[r][c]) continue;
      const x = c * cell, y = r * cell;
      if (isOpen(r - 1, c)) g.fillRect(x, y, cell, edge);
      if (isOpen(r + 1, c)) g.fillRect(x, y + cell - edge, cell, edge);
      if (isOpen(r, c - 1)) g.fillRect(x, y, edge, cell);
      if (isOpen(r, c + 1)) g.fillRect(x + cell - edge, y, edge, cell);
    }
    g.fillStyle = C.roofUnit;
    for (let r = 1; r < H - 1; r++) for (let c = 1; c < W - 1; c++) {
      const inner = !open[r][c] && MOVES.every(([dr, dc]) => !open[r + dr][c + dc]) && !open[r + 1][c + 1];
      if (inner && (r * 31 + c * 17) % 23 === 0) g.fillRect(c * cell + cell * 0.3, r * cell + cell * 0.3, cell * 1.1, cell * 0.8);
    }
  };
  function setup() {  // backing store and static layers at the current pixel density (sharp on retina)
    dpr = Math.min(2, window.devicePixelRatio || 1);
    canvas.width = CW * dpr; canvas.height = CH * dpr;
    streets = layer(drawStreets); buildings = layer(drawBuildings);
    dirty = true;
    matchMedia(`(resolution: ${window.devicePixelRatio || 1}dppx)`).addEventListener("change", setup, { once: true });
  }

  // Heatmap in two layers, one pixel per cell:
  // - glow: pale cyan to teal by loudness, scaled up smoothly, purely for looks;
  // - fire: the exact cells at or above the threshold, deep blue, scaled up crisply. Smoothing this layer
  //   would spread "fires" colour onto cells below the threshold, next to sensors that correctly stay idle.
  const pixels = () => { const c = document.createElement("canvas"); c.width = W; c.height = H; return c; };
  const glow = pixels(), fire = pixels();
  const glowCtx = glow.getContext("2d"), fireCtx = fire.getContext("2d");
  const glowImg = glowCtx.createImageData(W, H), fireImg = fireCtx.createImageData(W, H);
  const rgb = hex => [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16));
  const LOW = rgb(css("--heat-low")), HIGH = rgb(css("--heat-high")), FIRE = rgb(css("--heat-fire"));
  function paintHeat(noise) {
    const g = glowImg.data, f = fireImg.data;
    for (let k = 0; k < W * H; k++) {
      const n = noise[k], o = k * 4, t = Math.min(1, n / threshold);
      f[o] = FIRE[0]; f[o + 1] = FIRE[1]; f[o + 2] = FIRE[2]; f[o + 3] = n >= threshold ? 235 : 0;
      if (n <= 0) { g[o + 3] = 0; continue; }
      for (let i = 0; i < 3; i++) g[o + i] = LOW[i] + (HIGH[i] - LOW[i]) * t;
      g[o + 3] = 30 + 190 * t;
    }
    // Building pixels take their loudest street neighbour's glow, so smoothing never fades a street toward
    // transparent at a wall (a pale halo). Buildings are drawn on top, so these pixels never show.
    for (let r = 0; r < H; r++) for (let c = 0; c < W; c++) {
      if (open[r][c]) continue;
      const o = (r * W + c) * 4;
      g[o + 3] = 0;
      for (const [dr, dc] of MOVES) {
        if (!isOpen(r + dr, c + dc)) continue;
        const n = ((r + dr) * W + c + dc) * 4;
        if (g[n + 3] > g[o + 3]) { g[o] = g[n]; g[o + 1] = g[n + 1]; g[o + 2] = g[n + 2]; g[o + 3] = g[n + 3]; }
      }
    }
    glowCtx.putImageData(glowImg, 0, 0);
    fireCtx.putImageData(fireImg, 0, 0);
  }

  function car(x, y, heading) {  // top-down car, nose pointing along `heading` (radians)
    const len = cell * 1.45, wid = cell * 0.86, rad = cell * 0.24;
    ctx.save(); ctx.translate(x, y); ctx.rotate(heading);
    ctx.fillStyle = C.ink; ctx.beginPath(); ctx.roundRect(-len / 2, -wid / 2, len, wid, rad); ctx.fill();
    ctx.fillStyle = C.white;  // windscreen and rear window
    ctx.beginPath(); ctx.roundRect(len * 0.08, -wid * 0.34, len * 0.2, wid * 0.68, cell * 0.06); ctx.fill();
    ctx.globalAlpha = 0.55;
    ctx.beginPath(); ctx.roundRect(-len * 0.38, -wid * 0.3, len * 0.12, wid * 0.6, cell * 0.05); ctx.fill();
    ctx.restore();
  }
  function sensor(x, y, on, ping) {  // round detector with a microphone dot; firing = amber plus a lasting ring
    const r = cell * 0.62;
    if (ping < 1) {
      ctx.globalAlpha = 1 - ping; ctx.strokeStyle = C.amber; ctx.lineWidth = 3;
      ctx.beginPath(); ctx.arc(x, y, r + 6 + easeOut(ping) * cell * 1.6, 0, Math.PI * 2); ctx.stroke();
      ctx.globalAlpha = 1;
    }
    if (on) { ctx.strokeStyle = C.ink; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(x, y, r + 5, 0, Math.PI * 2); ctx.stroke(); }
    ctx.fillStyle = on ? C.amber : C.white; ctx.strokeStyle = C.ink; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
    ctx.fillStyle = C.ink; ctx.beginPath(); ctx.arc(x, y, r * 0.32, 0, Math.PI * 2); ctx.fill();
  }

  const SIM_FPS = 20, ECHO_MS = 700, PING_MS = 400;
  const easeOut = p => 1 - (1 - p) ** 3;
  const reduced = matchMedia("(prefers-reduced-motion: reduce)");
  let motion = !reduced.matches;
  reduced.addEventListener("change", e => { motion = !e.matches; dirty = true; });

  let playing = motion, simTime = 0, shownFrame = -1, echoStart = performance.now(), lastNow = echoStart;
  let onScreen = true, dirty = true, noise = null, noiseFrame = -1;
  const firing = new Uint8Array(detectors.length), pingStart = new Float64Array(detectors.length).fill(-Infinity);

  function render(now) {
    const frame = Math.floor(simTime), frac = simTime - frame;
    const echo = motion ? Math.min(1, (now - echoStart) / ECHO_MS) : 1;
    if (echo < 1 || noiseFrame !== frame) {
      noise = noiseAt(frame, echo < 1 ? easeOut(echo) : 1);
      noiseFrame = echo < 1 ? -1 : frame;
      paintHeat(noise);
    }
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.drawImage(streets, 0, 0);
    ctx.imageSmoothingEnabled = true; ctx.imageSmoothingQuality = "high";
    ctx.drawImage(glow, 0, 0, canvas.width, canvas.height);
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(fire, 0, 0, canvas.width, canvas.height);
    ctx.drawImage(buildings, 0, 0);  // on top: sound never shows through a building
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    let firingCount = 0, pinging = false;
    detectors.forEach((det, i) => {
      const [r, c] = det.cell, on = noise[r * W + c] >= threshold;
      if (on && !firing[i] && motion) pingStart[i] = now;
      firing[i] = on;
      if (on) firingCount++;
      const ping = (now - pingStart[i]) / PING_MS;
      if (ping < 1) pinging = true;
      sensor(c * cell + cell / 2, r * cell + cell / 2, on, ping);
    });
    for (const t of tracks) {
      const a = motion ? t.posAt(frame) : t.cellAt(frame), b = motion ? t.posAt(frame + 1) : a;
      const next = t.posAt(frame + 1), here = t.posAt(frame);
      if (next[0] !== here[0] || next[1] !== here[1]) t.heading = Math.atan2(next[0] - here[0], next[1] - here[1]);
      const r = a[0] + (b[0] - a[0]) * frac, c = a[1] + (b[1] - a[1]) * frac;
      car(c * cell + cell / 2, r * cell + cell / 2, t.heading);
    }
    // Labels follow what is drawn, so they also update while the opening echo spreads on an unchanged frame.
    const firingText = `${firingCount} of ${detectors.length} detectors firing`;
    if (firingLabel.textContent !== firingText) firingLabel.textContent = firingText;
    if (frame !== shownFrame) {
      shownFrame = frame;
      frameLabel.textContent = `frame ${frame.toLocaleString("en-US")} of ${n_frames.toLocaleString("en-US")}`;
    }
    // Keep drawing while anything still moves; a paused, settled city costs nothing.
    dirty = playing || echo < 1 || pinging;
  }

  function loop(now) {
    const dt = Math.min(100, now - lastNow);  // a long gap (hidden tab) never jumps the simulation ahead
    lastNow = now;
    if (onScreen && !document.hidden) {
      if (playing) {
        simTime += dt * SIM_FPS / 1000;
        if (simTime >= n_frames) { simTime = 0; echoStart = now; shownFrame = -1; }  // replay the echo on restart
      }
      if (dirty) render(now);
    }
    requestAnimationFrame(loop);
  }

  new IntersectionObserver(([entry]) => { onScreen = entry.isIntersecting; dirty = true; }).observe(canvas);
  function setPlaying(p) {
    playing = p; button.textContent = p ? "Pause" : "Play"; dirty = true;
  }
  button.addEventListener("click", () => setPlaying(!playing));
  setup();
  setPlaying(playing);
  requestAnimationFrame(loop);
})();
