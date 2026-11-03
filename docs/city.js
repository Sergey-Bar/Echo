// Live city: the demo scenario, played with the same rules (BFS noise, shortest-path routes, threshold).
(() => {
  const canvas = document.getElementById("city"), ctx = canvas.getContext("2d");
  const button = document.getElementById("toggle"), frameLabel = document.getElementById("frame");
  const firingLabel = document.getElementById("firing");
  const { map, vehicles, detectors, threshold, n_frames } = DEMO;
  const H = map.length, W = map[0].length, open = map.map(r => [...r].map(c => c === "."));
  const isOpen = (r, c) => r >= 0 && r < H && c >= 0 && c < W && open[r][c];
  const cell = Math.floor(Math.min(1280 / W, 800 / H)), CW = W * cell, CH = H * cell;
  const dpr = Math.min(2, window.devicePixelRatio || 1);
  canvas.width = CW * dpr; canvas.height = CH * dpr;
  const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  const C = {
    street: css("--street"), lane: css("--lane"), roof: css("--building"), roofEdge: css("--building-edge"),
    roofUnit: css("--building-unit"), ink: css("--ink"), amber: css("--amber"), white: css("--white"),
  };
  const MOVES = [[-1, 0], [1, 0], [0, -1], [0, 1]];

  function bfs(r0, c0, limit) {
    const d = new Int32Array(H * W).fill(-1), q = [r0 * W + c0];
    d[q[0]] = 0;
    for (let i = 0; i < q.length; i++) {
      const k = q[i], r = (k / W) | 0, c = k % W;
      if (d[k] >= limit) continue;
      for (const [dr, dc] of MOVES) {
        const rr = r + dr, cc = c + dc;
        if (!isOpen(rr, cc) || d[rr * W + cc] >= 0) continue;
        d[rr * W + cc] = d[k] + 1; q.push(rr * W + cc);
      }
    }
    return d;
  }
  function path(a, b) {  // lexicographically first shortest path, as in Echo
    const toGoal = bfs(b[0], b[1], 1e9), out = [a];
    let [r, c] = a;
    while (r !== b[0] || c !== b[1]) {
      const here = toGoal[r * W + c];
      for (const [dr, dc] of MOVES) {
        const rr = r + dr, cc = c + dc;
        if (isOpen(rr, cc) && toGoal[rr * W + cc] === here - 1) { r = rr; c = cc; break; }
      }
      out.push([r, c]);
    }
    return out;
  }
  // Timeline per vehicle, one entry per frame of a lap (or of the whole trip, then parked):
  // `cells` is the cell the noise rule uses; `pos` is where to draw it, sliding toward the next cell
  // while the vehicle moves, exactly like the simulator's own draw positions.
  const tracks = vehicles.map(v => {
    const wps = v.loop ? [...v.waypoints, v.waypoints[0]] : v.waypoints, cells = [], pos = [];
    const wait = (c, n) => { for (let i = 0; i < n; i++) { cells.push(c); pos.push(c); } };
    wait(wps[0].cell, wps[0].wait_frames || 0);
    for (let i = 1; i < wps.length; i++) {
      const p = path(wps[i - 1].cell, wps[i].cell), n = v.frames_per_cell;
      for (let j = 0; j < p.length - 1; j++) {
        const [a, b] = [p[j], p[j + 1]];
        for (let k = 0; k < n; k++) { cells.push(a); pos.push([a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n]); }
      }
      if (!(v.loop && i === wps.length - 1)) wait(wps[i].cell, wps[i].wait_frames || 0);
    }
    const last = v.loop ? null : wps[wps.length - 1].cell;
    const pick = list => f => v.loop ? list[f % list.length] : (list[f] || last);
    return { v, cellAt: pick(cells), posAt: pick(pos), heading: 0 };
  });

  // Noise one vehicle makes from one cell, cached: flat triples of (cell index, level, steps).
  const cache = new Map();
  function contribution(r, c, L) {
    const key = (r * W + c) * 128 + L;
    if (!cache.has(key)) {
      const d = bfs(r, c, L - 1), out = [];
      for (let k = 0; k < d.length; k++) if (d[k] >= 0 && d[k] < L) out.push(k, L - d[k], d[k]);
      cache.set(key, Int32Array.from(out));
    }
    return cache.get(key);
  }
  // reach < 1 draws only the part of each vehicle's sound within that fraction of its range (the opening echo).
  function noiseAt(f, reach) {
    const out = new Float32Array(H * W);
    for (const t of tracks) {
      const [r, c] = t.cellAt(f), L = t.v.loudness, list = contribution(r, c, L), limit = reach * L;
      for (let i = 0; i < list.length; i += 3) if (list[i + 2] <= limit) out[list[i]] += list[i + 1];
    }
    return out;
  }

  function layer(draw) {  // an offscreen canvas at the same resolution as the visible one
    const c = document.createElement("canvas");
    c.width = canvas.width; c.height = canvas.height;
    const g = c.getContext("2d");
    g.scale(dpr, dpr); draw(g);
    return c;
  }
  // Streets: asphalt with dashed centre lines down the middle of two-lane roads.
  const streets = layer(g => {
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
  });
  // Buildings: flat roofs, a darker parapet on every street-facing edge, and a few rooftop units.
  const buildings = layer(g => {
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
  });

  // Heatmap: one pixel per cell, scaled up with smoothing. Pale cyan to teal below the threshold;
  // deep blue at or above it, where a detector would fire.
  const heat = document.createElement("canvas");
  heat.width = W; heat.height = H;
  const heatCtx = heat.getContext("2d"), heatImg = heatCtx.createImageData(W, H);
  const rgb = hex => [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16));
  const LOW = rgb(css("--heat-low")), HIGH = rgb(css("--heat-high")), FIRE = rgb(css("--heat-fire"));
  function paintHeat(noise) {
    const px = heatImg.data;
    for (let k = 0; k < W * H; k++) {
      const n = noise[k], o = k * 4;
      if (n <= 0) { px[o + 3] = 0; continue; }
      const t = n / threshold;
      const rgb = t >= 1 ? FIRE : LOW.map((v, i) => v + (HIGH[i] - v) * t);
      px[o] = rgb[0]; px[o + 1] = rgb[1]; px[o + 2] = rgb[2];
      px[o + 3] = t >= 1 ? 235 : 70 + 150 * t;
    }
    // Building pixels take their loudest street neighbour's colour, so smoothing never fades streets toward
    // transparent at a wall (a pale halo). Buildings are drawn on top, so these pixels never show.
    for (let r = 0; r < H; r++) for (let c = 0; c < W; c++) {
      if (open[r][c]) continue;
      const o = (r * W + c) * 4;
      px[o + 3] = 0;
      for (const [dr, dc] of MOVES) {
        if (!isOpen(r + dr, c + dc)) continue;
        const n = ((r + dr) * W + c + dc) * 4;
        if (px[n + 3] > px[o + 3]) { px[o] = px[n]; px[o + 1] = px[n + 1]; px[o + 2] = px[n + 2]; px[o + 3] = px[n + 3]; }
      }
    }
    heatCtx.putImageData(heatImg, 0, 0);
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
    ctx.drawImage(heat, 0, 0, canvas.width, canvas.height);
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
    if (frame !== shownFrame) {
      shownFrame = frame;
      firingLabel.textContent = `${firingCount} of ${detectors.length} detectors firing`;
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
  setPlaying(playing);
  requestAnimationFrame(loop);
})();
