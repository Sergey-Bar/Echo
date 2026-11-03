"""Vehicle movement: expands waypoints into a driving route and tells where a vehicle is at any frame."""

from bisect import bisect_right
from dataclasses import dataclass

import numpy as np

from .scenario import NEIGHBOUR_OFFSETS, Cell, CityMap, ScenarioError, Vehicle

DrawPosition = tuple[int, int, int]  # (row numerator, col numerator, denominator)


def shortest_path(city_map: CityMap, start: Cell, goal: Cell) -> list[Cell]:
    """Shortest 4-neighbour path through open cells, start and goal included.

    Equally short paths are told apart by neighbour order: each cell keeps the first parent that reached it.

    That FIFO rule picks the lexicographically smallest shortest path, comparing moves in NEIGHBOUR_OFFSETS order:
    a FIFO queue holds each level in the order of its cells' parent chains, so the first parent to reach a cell
    is the one whose own path sorts first. So: BFS distances from the goal (numpy, one level at a time), then walk
    from the start, always taking the first neighbour in NEIGHBOUR_OFFSETS order that is one step closer.
    """
    open_flat = city_map.padded_open
    width = city_map.width + 2
    offsets = [d_row * width + d_col for d_row, d_col in NEIGHBOUR_OFFSETS]
    source, target = (start[0] + 1) * width + start[1] + 1, (goal[0] + 1) * width + goal[1] + 1

    offset_array = np.array(offsets, dtype=np.int64)
    to_goal = city_map.steps_scratch  # all -1 between calls; reset below
    to_goal[target] = 0
    reached = [np.array([target], dtype=np.int64)]
    steps = 0
    try:
        while reached[-1].size and to_goal[source] < 0:
            steps += 1
            candidates = (reached[-1][:, None] + offset_array).ravel()
            candidates = candidates[open_flat[candidates] & (to_goal[candidates] < 0)]
            candidates.sort()  # dedupe by sorting: much cheaper than np.unique's hashing on these small arrays
            first = np.ones(candidates.size, dtype=bool)
            first[1:] = candidates[1:] != candidates[:-1]
            candidates = candidates[first]
            to_goal[candidates] = steps
            reached.append(candidates)
        if to_goal[source] < 0:
            raise ScenarioError(f"no open path from {start} to {goal}")

        path = [source]
        for remaining in range(int(to_goal[source]) - 1, -1, -1):
            cell = path[-1]
            path.append(next(cell + offset for offset in offsets if to_goal[cell + offset] == remaining))
    finally:
        to_goal[np.concatenate(reached)] = -1
    return [(cell // width - 1, cell % width - 1) for cell in path]


def expand_route(city_map: CityMap, vehicle: Vehicle) -> tuple[list[Cell], dict[int, int]]:
    """Route cells in driving order, and the wait in frames at each route index that is a waypoint."""
    waypoints = list(vehicle.waypoints)
    if vehicle.loop:
        waypoints.append(waypoints[0])

    route = [waypoints[0].cell]
    waits = {0: waypoints[0].wait_frames}
    for leg_start, leg_end in zip(waypoints, waypoints[1:]):
        route.extend(shortest_path(city_map, leg_start.cell, leg_end.cell)[1:])
        waits[len(route) - 1] = leg_end.wait_frames

    if vehicle.loop:
        # The closing leg ends where the route began: that cell is index 0 of the next lap.
        route.pop()
        waits.pop(len(route))
    return route, waits


@dataclass(frozen=True)
class Segment:
    """Frames during which a vehicle waits at `cell` (next_cell is None) or moves from `cell` to `next_cell`."""

    start_frame: int
    duration: int
    cell: Cell
    next_cell: Cell | None


class VehicleTrack:
    """Position of one vehicle at any frame."""

    def __init__(self, city_map: CityMap, vehicle: Vehicle):
        self.frames_per_cell = vehicle.frames_per_cell
        self.loop = vehicle.loop
        route, waits = expand_route(city_map, vehicle)
        self.final_cell = route[-1]
        self.segments = self._build_segments(route, waits)
        self.timeline_frames = sum(segment.duration for segment in self.segments)
        self._segment_starts = [segment.start_frame for segment in self.segments]

    def _build_segments(self, route: list[Cell], waits: dict[int, int]) -> list[Segment]:
        segments = []
        frame = 0
        for index, cell in enumerate(route):
            wait = waits.get(index, 0)
            if wait > 0:
                segments.append(Segment(frame, wait, cell, None))
                frame += wait

            next_cell = self._next_cell(route, index)
            if next_cell is None:
                continue
            segments.append(Segment(frame, self.frames_per_cell, cell, next_cell))
            frame += self.frames_per_cell
        return segments

    def _next_cell(self, route: list[Cell], index: int) -> Cell | None:
        if index + 1 < len(route):
            return route[index + 1]
        return route[0] if self.loop else None

    def _locate(self, frame: int) -> tuple[Segment | None, int]:
        """Active segment and frames elapsed in it; (None, 0) once a non-looping vehicle has parked."""
        if self.loop:
            frame %= self.timeline_frames
        elif frame >= self.timeline_frames:
            return None, 0
        segment = self.segments[bisect_right(self._segment_starts, frame) - 1]
        return segment, frame - segment.start_frame

    def cell_at(self, frame: int) -> Cell:
        segment, _ = self._locate(frame)
        return self.final_cell if segment is None else segment.cell

    def draw_position_at(self, frame: int) -> DrawPosition:
        segment, progress = self._locate(frame)
        if segment is None:
            return self._resting_at(self.final_cell)
        if segment.next_cell is None:
            return self._resting_at(segment.cell)

        row, col = segment.cell
        next_row, next_col = segment.next_cell
        denominator = self.frames_per_cell
        return (
            row * denominator + (next_row - row) * progress,
            col * denominator + (next_col - col) * progress,
            denominator,
        )

    def _resting_at(self, cell: Cell) -> DrawPosition:
        return (cell[0] * self.frames_per_cell, cell[1] * self.frames_per_cell, self.frames_per_cell)
