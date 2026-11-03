"""Rendering: per-frame digests for --dump-frames, and the matplotlib animation for --render."""

import hashlib
from collections.abc import Iterable

import numpy as np

from .detection import detector_firing
from .scenario import Scenario
from .simulation import FrameState

FRAMES_PER_SECOND = 30
MILLISECONDS_PER_FRAME = 1000 / FRAMES_PER_SECOND
HEATMAP_COLOURMAP = "inferno"
BUILDING_COLOUR = "dimgray"
VEHICLE_COLOUR = "white"
DETECTOR_IDLE_COLOUR = "deepskyblue"
DETECTOR_FIRING_COLOUR = "red"


def frame_digest(state: FrameState, firing: list[bool]) -> str:
    """SHA-256 of one frame as drawn.

    Byte layout: the heatmap as little-endian int32 in row-major order, then each vehicle's draw
    position as three little-endian int64, then one byte (0 or 1) per detector.
    """
    hasher = hashlib.sha256()
    hasher.update(state.noise.astype("<i4").tobytes(order="C"))
    for position in state.draw_positions:
        hasher.update(np.array(position, dtype="<i8").tobytes())
    hasher.update(bytes(int(is_firing) for is_firing in firing))
    return hasher.hexdigest()


def animate(scenario: Scenario, frames: Iterable[FrameState], show: bool = True):
    """Animate the frames: noise heatmap, buildings, vehicles, and detectors lit while firing."""
    # Imported here so that runs without --render never need matplotlib.
    import matplotlib.pyplot as plt
    from matplotlib.animation import FuncAnimation
    from matplotlib.colors import ListedColormap

    buildings = np.array([[not is_open for is_open in row] for row in scenario.city_map.open_cells])
    # One vehicle's peak sets the scale; summing every vehicle's peak leaves busy maps nearly black.
    loudest_vehicle = max(vehicle.loudness for vehicle in scenario.vehicles)

    figure, axes = plt.subplots()
    heatmap = axes.imshow(np.zeros(buildings.shape), cmap=HEATMAP_COLOURMAP, vmin=0, vmax=loudest_vehicle)
    axes.imshow(np.ma.masked_where(~buildings, buildings.astype(float)), cmap=ListedColormap([BUILDING_COLOUR]))
    detector_marks = axes.scatter(
        [detector.cell[1] for detector in scenario.detectors],
        [detector.cell[0] for detector in scenario.detectors],
        marker="s",
        c=DETECTOR_IDLE_COLOUR,
    )
    vehicle_marks = axes.scatter([], [], marker="o", c=VEHICLE_COLOUR)
    title = axes.set_title(scenario.name)

    def draw(state: FrameState):
        heatmap.set_data(state.noise)
        vehicle_marks.set_offsets(
            [(col / denominator, row / denominator) for row, col, denominator in state.draw_positions]
        )
        firing = detector_firing(state, scenario.detectors, scenario.threshold)
        detector_marks.set_color(
            [DETECTOR_FIRING_COLOUR if is_firing else DETECTOR_IDLE_COLOUR for is_firing in firing]
        )
        title.set_text(f"{scenario.name}   frame {state.frame}")
        return heatmap, vehicle_marks, detector_marks, title

    animation = FuncAnimation(
        figure, draw, frames=frames, interval=MILLISECONDS_PER_FRAME, repeat=False, cache_frame_data=False
    )
    if show:
        plt.show()
    return animation
