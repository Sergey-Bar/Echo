"""The frame loop: moves every vehicle and combines their noise into one map per frame."""

from collections.abc import Iterator
from dataclasses import dataclass

import numpy as np

from .movement import DrawPosition, VehicleTrack
from .noise import noise_field
from .scenario import Scenario


@dataclass(frozen=True)
class FrameState:
    """What consumers need to know about one frame."""

    frame: int
    noise: np.ndarray                           # total noise per cell, shape (height, width)
    draw_positions: tuple[DrawPosition, ...]    # one per vehicle, in scenario order


class Simulation:
    def __init__(self, scenario: Scenario):
        self.scenario = scenario
        self.tracks = [VehicleTrack(scenario.city_map, vehicle) for vehicle in scenario.vehicles]

    def frames(self, max_frames: int | None = None) -> Iterator[FrameState]:
        n_frames = self.scenario.n_frames
        if max_frames is not None:
            n_frames = min(n_frames, max_frames)

        city_map = self.scenario.city_map
        for frame in range(n_frames):
            total = np.zeros((city_map.height, city_map.width), dtype=np.int64)
            for vehicle, track in zip(self.scenario.vehicles, self.tracks):
                total += noise_field(city_map, track.cell_at(frame), vehicle.loudness)

            draw_positions = tuple(track.draw_position_at(frame) for track in self.tracks)
            yield FrameState(frame, total, draw_positions)
