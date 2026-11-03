"""Fast detection log: same result as running Simulation + DetectionRecorder, without per-frame noise maps.

Only detector cells matter for the log, and a vehicle's noise at a detector depends only on the vehicle's cell.
So instead of building a full noise map for every frame:

1. BFS once from every detector, up to the loudest vehicle's reach, giving (detector, cell, steps) pairs.
   Steps on a 4-neighbour grid are symmetric, so this equals the per-vehicle BFS of `noise.py`.
2. Turn each vehicle's timeline into segments (cell, first frame, end frame) where its cell is constant.
3. For each segment and each detector in reach, add `loudness - steps` at the first frame and subtract it at
   the end frame. A cumulative sum over frames gives every detector's total noise on every frame.
4. Compare with the threshold and read off the firing intervals.

Detectors are processed in blocks so memory stays bounded on the largest scenarios.
"""

import numpy as np

from .movement import VehicleTrack
from .scenario import Scenario

DENSE_CELLS_PER_BLOCK = 4_000_000  # detectors x frames per block; float64, so ~32 MB per dense array
BFS_CELLS_PER_BLOCK = 50_000_000  # detectors x map cells per block for the BFS visited mask (bytes)
FLUSH_EVENTS = 8_000_000  # pending change events (16 bytes each) before they are folded into the dense array


def detection_log(scenario: Scenario, max_frames: int | None = None) -> dict:
    n_frames = scenario.n_frames if max_frames is None else max(0, min(scenario.n_frames, max_frames))
    city_map = scenario.city_map
    width = city_map.width + 2
    open_flat = city_map.padded_open
    offsets = np.array([-width, width, -1, 1], dtype=np.int64)

    def flat(cell):
        return (cell[0] + 1) * width + cell[1] + 1

    vehicles = [
        (vehicle.loudness, *_segments(VehicleTrack(city_map, vehicle), vehicle.loop, n_frames, flat))
        for vehicle in scenario.vehicles
    ]
    visited_cells = np.zeros(open_flat.size, dtype=bool)
    for _, cells, _, _, _ in vehicles:
        visited_cells[cells] = True

    detectors = scenario.detectors
    intervals = [[] for _ in detectors]
    if n_frames > 0 and detectors:
        reach = max(vehicle.loudness for vehicle in scenario.vehicles) - 1
        sources = np.array([flat(detector.cell) for detector in detectors], dtype=np.int64)
        block = max(1, min(DENSE_CELLS_PER_BLOCK // (n_frames + 1), BFS_CELLS_PER_BLOCK // open_flat.size))
        for first in range(0, len(detectors), block):
            pairs = _bounded_bfs(sources[first:first + block], open_flat, offsets, reach, visited_cells)
            _block_intervals(pairs, vehicles, len(sources[first:first + block]), n_frames,
                             scenario.threshold, intervals, first)

    return {
        "scenario": scenario.name,
        "n_frames": n_frames,
        "detectors": [{"id": d.id, "intervals": found} for d, found in zip(detectors, intervals)],
    }


def _segments(track: VehicleTrack, loop: bool, n_frames: int, flat):
    """(cell, start, end, period): segments where the vehicle's cell is constant.

    Mirrors VehicleTrack.cell_at. A looping track gives one lap of segments and its period; lap k is the same
    segments shifted by k * period. A non-looping track gives all its segments up to n_frames, resting at its
    final cell from the end of its timeline on, and period 0.
    """
    cells = [flat(segment.cell) for segment in track.segments]
    starts = [segment.start_frame for segment in track.segments]
    if not loop:
        cells.append(flat(track.final_cell))
        starts.append(track.timeline_frames)
    cells = np.array(cells, dtype=np.int64)
    starts = np.array(starts, dtype=np.int64)

    keep = np.ones(len(cells), dtype=bool)
    keep[1:] = cells[1:] != cells[:-1]  # a wait followed by a move from the same cell is one segment
    cells, starts = cells[keep], starts[keep]

    if loop:
        return cells, starts, np.append(starts[1:], track.timeline_frames), track.timeline_frames

    inside = starts < n_frames
    cells, starts = cells[inside], starts[inside]
    return cells, starts, np.append(starts[1:], n_frames), 0


def _bounded_bfs(sources, open_flat, offsets, reach, wanted):
    """Steps from each source to every open cell within `reach` steps, kept only where `wanted`.

    Returns (source index, cell, steps) arrays. Level-synchronous BFS run for all sources at once.
    """
    n_cells = open_flat.size
    visited = np.zeros(len(sources) * n_cells, dtype=bool)
    source_ids = np.arange(len(sources), dtype=np.int64)
    frontier = source_ids * n_cells + sources
    visited[frontier] = True

    found_keys, found_steps = [], []
    for steps in range(reach + 1):
        cells = frontier % n_cells
        hit = wanted[cells]
        found_keys.append(frontier[hit])
        found_steps.append(np.full(int(hit.sum()), steps, dtype=np.int64))
        if steps == reach or frontier.size == 0:
            break
        candidates = (frontier[:, None] + offsets).ravel()
        candidates = candidates[open_flat[(cells[:, None] + offsets).ravel()]]
        candidates = np.unique(candidates[~visited[candidates]])
        visited[candidates] = True
        frontier = candidates

    keys = np.concatenate(found_keys)
    return keys // n_cells, keys % n_cells, np.concatenate(found_steps)


def _block_intervals(pairs, vehicles, n_sources, n_frames, threshold, intervals, first):
    source, cell, steps = pairs
    # Grouped by cell, nearest first: the pairs a vehicle of loudness L reaches are a prefix of its cell's group.
    order = np.argsort(cell * (int(steps.max(initial=0)) + 1) + steps)
    source, cell, steps = source[order], cell[order], steps[order]
    n_rows = int(cell[-1]) + 1 if len(cell) else 0
    row_start = np.searchsorted(cell, np.arange(n_rows))

    # Pairs per cell with steps < L, for every vehicle loudness L, in one pass: bucket each pair by how many
    # loudness values it is too far for, then a cumulative count over buckets.
    louds = sorted({loudness for loudness, *_ in vehicles})
    bucket = np.searchsorted(louds, steps, side="right")  # 0..len(louds); len(louds) = out of every vehicle's reach
    n_buckets = len(louds) + 1
    by_bucket = np.bincount(cell * n_buckets + bucket, minlength=n_rows * n_buckets).reshape(n_rows, n_buckets)
    within = np.cumsum(by_bucket, axis=1)
    in_reach = {loudness: within[:, index] for index, loudness in enumerate(louds)}

    span = n_frames + 1
    row_key = source * span
    change = np.zeros(n_sources * span)
    where, amount, pending = [], [], 0
    for loudness, seg_cells, seg_starts, seg_ends, period in vehicles:
        known = seg_cells < n_rows
        seg_cells, seg_starts, seg_ends = seg_cells[known], seg_starts[known], seg_ends[known]
        counts = in_reach[loudness][seg_cells]
        total = int(counts.sum())
        if total == 0:
            continue
        # Index of every (segment, pair) combination without a Python loop over segments.
        pair = np.arange(total) + np.repeat(row_start[seg_cells] - (np.cumsum(counts) - counts), counts)
        # One lap of change events: +level when the segment starts, -level when it ends.
        key = np.empty(2 * total, dtype=np.int64)
        np.add(row_key[pair], np.repeat(seg_starts, counts), out=key[:total])
        np.add(row_key[pair], np.repeat(seg_ends, counts), out=key[total:])
        weight = np.empty(2 * total)
        np.subtract(loudness, steps[pair], out=weight[:total])
        np.negative(weight[:total], out=weight[total:])

        if not period:
            # A non-looping run's last end event is at n_frames, the spare slot of its row: no clipping needed.
            where.append(key)
            amount.append(weight)
            pending += len(key)
        else:
            # Laps that end before the last frame need no clipping, so they are added in one broadcast; only the
            # last lap or two drop events at or after n_frames, which never affect a logged frame.
            frame = np.concatenate([np.repeat(seg_starts, counts), np.repeat(seg_ends, counts)])
            whole_laps = (n_frames - 1) // period
            if whole_laps:
                where.append((key[None, :] + period * np.arange(whole_laps)[:, None]).ravel())
                amount.append(np.tile(weight, whole_laps))
            for lap in range(whole_laps, -(-n_frames // period)):
                inside = frame + lap * period < n_frames
                where.append(key[inside] + lap * period)
                amount.append(weight[inside])
            pending += len(key) * max(1, whole_laps)
        if pending > FLUSH_EVENTS:
            change += np.bincount(np.concatenate(where), weights=np.concatenate(amount), minlength=change.size)
            where, amount, pending = [], [], 0

    if where:
        change += np.bincount(np.concatenate(where), weights=np.concatenate(amount), minlength=change.size)
    noise = np.cumsum(change.reshape(n_sources, span)[:, :n_frames], axis=1)
    firing = np.zeros((n_sources, n_frames + 2), dtype=np.int8)
    firing[:, 1:-1] = noise >= threshold
    edges = np.diff(firing, axis=1)
    on_rows, on_frames = np.nonzero(edges == 1)
    off_frames = np.nonzero(edges == -1)[1]
    # Rows come out sorted and each interval opens before it closes, so starts and ends pair up in order.
    for row, start, end in zip(on_rows.tolist(), on_frames.tolist(), (off_frames - 1).tolist()):
        intervals[first + row].append([start, end])
