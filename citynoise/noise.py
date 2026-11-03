"""Noise propagation: how loud one vehicle is at every cell of the map."""

from collections import deque

import numpy as np

from .scenario import Cell, CityMap

UNREACHABLE = -1


def bfs_steps(city_map: CityMap, source: Cell) -> list[list[int]]:
    """Fewest 4-neighbour moves from `source` to every cell; UNREACHABLE where noise cannot go."""
    steps = [[UNREACHABLE] * city_map.width for _ in range(city_map.height)]
    steps[source[0]][source[1]] = 0
    queue = deque([source])
    while queue:
        cell = queue.popleft()
        next_steps = steps[cell[0]][cell[1]] + 1
        for row, col in city_map.open_neighbours(cell):
            if steps[row][col] == UNREACHABLE:
                steps[row][col] = next_steps
                queue.append((row, col))
    return steps


def noise_field(city_map: CityMap, source: Cell, loudness: int) -> np.ndarray:
    """Noise of one vehicle at every cell: max(0, loudness - steps), and 0 where noise cannot reach."""
    steps = np.array(bfs_steps(city_map, source), dtype=np.int64)
    levels = np.maximum(0, loudness - steps)
    levels[steps == UNREACHABLE] = 0
    return levels
