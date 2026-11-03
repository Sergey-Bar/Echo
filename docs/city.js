// Live city: the demo scenario, played with the same rules (BFS noise, shortest-path routes, threshold).
(() => {
  const canvas = document.getElementById("city"), ctx = canvas.getContext("2d");
  const button = document.getElementById("toggle"), frameLabel = document.getElementById("frame");
  const firingLabel = document.getElementById("firing");
  const { map, vehicles, detectors, threshold, n_frames } = DEMO;
  const H = map.length, W = map[0].length, open = map.map(r => [...r].map(c => c === "."));
  const cell = Math.floor(Math.min(1280 / W, 800 / H));
  canvas.width = W * cell; canvas.height = H * cell;
  const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  const C = { street: css("--street"), building: css("--building"), ink: css("--ink"), amber: css("--amber"),
              white: css("--white"), teal: [css("--teal-1"), css("--teal-2"), css("--teal-3"), css("--teal-4")] };
  const MOVES = [[-1, 0], [1, 0], [0, -1], [0, 1]];

  function bfs(r0, c0, limit) {
    const d = new Int32Array(H * W).fill(-1), q = [r0 * W + c0];
    d[q[0]] = 0;
    for (let i = 0; i < q.length; i++) {
      const k = q[i], r = (k / W) | 0, c = k % W;
      if (d[k] >= limit) continue;
      for (const [dr, dc] of MOVES) {
        const rr = r + dr, cc = c + dc;
        if (rr < 0 || rr >= H || cc < 0 || cc >= W || !open[rr][cc] || d[rr * W + cc] >= 0) continue;
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
        if (rr >= 0 && rr < H && cc >= 0 && cc < W && toGoal[rr * W + cc] === here - 1) { r = rr; c = cc; break; }
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
    return { v, cellAt: pick(cells), posAt: pick(pos) };
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
    }
    for (let r = 0; r < H; r++) for (let c = 0; c < W; c++) {
      const n = noise[r * W + c];
      // Darkest step = loud enough to fire a detector on this cell.
      const level = n >= threshold ? 3 : n >= threshold * 0.6 ? 2 : n >= threshold * 0.3 ? 1 : 0;
      ctx.fillStyle = !open[r][c] ? C.building : n <= 0 ? C.street : C.teal[level];
      ctx.fillRect(c * cell, r * cell, cell, cell);
    }
    let firingCount = 0, pinging = false;
    detectors.forEach((det, i) => {
      const [r, c] = det.cell, on = noise[r * W + c] >= threshold, x = c * cell, y = r * cell;
      if (on && !firing[i] && motion) pingStart[i] = now;
      firing[i] = on;
      if (on) {  // shape cue as well as colour: a ring stays around a firing detector
        firingCount++;
        ctx.strokeStyle = C.ink; ctx.lineWidth = 2; ctx.strokeRect(x - 5, y - 5, cell + 10, cell + 10);
      }
      const ping = (now - pingStart[i]) / PING_MS;
      if (ping < 1) {  // one expanding, fading ring as a detector starts firing
        pinging = true;
        const grow = 5 + easeOut(ping) * cell * 1.4;
        ctx.globalAlpha = 1 - ping; ctx.strokeStyle = C.amber; ctx.lineWidth = 3;
        ctx.strokeRect(x - grow, y - grow, cell + grow * 2, cell + grow * 2);
        ctx.globalAlpha = 1;
      }
      ctx.fillStyle = C.ink; ctx.fillRect(x - 2, y - 2, cell + 4, cell + 4);
      ctx.fillStyle = on ? C.amber : C.white; ctx.fillRect(x, y, cell, cell);
    });
    for (const t of tracks) {
      const a = motion ? t.posAt(frame) : t.cellAt(frame), b = motion ? t.posAt(frame + 1) : a;
      const r = a[0] + (b[0] - a[0]) * frac, c = a[1] + (b[1] - a[1]) * frac;
      ctx.fillStyle = C.ink; ctx.beginPath();
      ctx.arc(c * cell + cell / 2, r * cell + cell / 2, cell * 0.75, 0, Math.PI * 2); ctx.fill();
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
