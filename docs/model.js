// The simulator's rules in JavaScript: routes, positions and noise for the demo city.
// Shared by the page (city.js draws it) and tests/test_demo_page.py (checks it against Echo).
function buildModel({ map, vehicles, threshold, n_frames }) {
  const H = map.length, W = map[0].length, open = map.map(r => [...r].map(c => c === "."));
  const isOpen = (r, c) => r >= 0 && r < H && c >= 0 && c < W && open[r][c];
  const MOVES = [[-1, 0], [1, 0], [0, -1], [0, 1]];  // up, down, left, right: the simulator's tie-break order

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
  // Total noise per cell on frame f. reach < 1 keeps only the part of each vehicle's sound within that
  // fraction of its range (the page's opening echo); reach 1 is the exact simulator rule.
  function noiseAt(f, reach = 1) {
    const out = new Float32Array(H * W);
    for (const t of tracks) {
      const [r, c] = t.cellAt(f), L = t.v.loudness, list = contribution(r, c, L), limit = reach * L;
      for (let i = 0; i < list.length; i += 3) if (list[i + 2] <= limit) out[list[i]] += list[i + 1];
    }
    return out;
  }
  return { H, W, open, isOpen, MOVES, tracks, noiseAt, threshold, n_frames };
}
if (typeof module !== "undefined") module.exports = { buildModel };
