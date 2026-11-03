"""Scenario loading: the city map, vehicles, detectors and run parameters."""

from collections.abc import Iterator
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

import numpy as np
import yaml

OPEN_CHAR = "."
BUILDING_CHAR = "#"

# Route expansion breaks ties between equally short paths by this order.
NEIGHBOUR_OFFSETS = ((-1, 0), (1, 0), (0, -1), (0, 1))  # up, down, left, right

Cell = tuple[int, int]


class ScenarioError(ValueError):
    """The scenario describes something the simulation cannot run."""


@dataclass(frozen=True)
class CityMap:
    open_cells: tuple[tuple[bool, ...], ...]

    @classmethod
    def from_text(cls, text: str) -> "CityMap":
        lines = [line.rstrip() for line in text.splitlines()]
        lines = [line for line in lines if line]
        if not lines:
            raise ScenarioError("map is empty")

        width = len(lines[0])
        for row, line in enumerate(lines):
            if len(line) != width:
                raise ScenarioError(f"map row {row} has {len(line)} cells, expected {width}")
            unknown = set(line) - {OPEN_CHAR, BUILDING_CHAR}
            if unknown:
                raise ScenarioError(f"map row {row} has unknown characters {sorted(unknown)}")

        return cls(tuple(tuple(char == OPEN_CHAR for char in line) for line in lines))

    @cached_property
    def padded_open(self) -> np.ndarray:
        """Open cells flattened row-major with a one-cell building border: cell (r, c) is (r + 1) * (width + 2) + c + 1.

        The border means neighbour lookups never need bounds checks.
        """
        padded = np.zeros((self.height + 2, self.width + 2), dtype=bool)
        padded[1:-1, 1:-1] = np.array(self.open_cells, dtype=bool)
        return padded.ravel()

    @cached_property
    def steps_scratch(self) -> np.ndarray:
        """Reusable per-cell step counts (padded layout), all -1; route planning resets what it writes."""
        return np.full(self.padded_open.size, -1, dtype=np.int64)

    @property
    def height(self) -> int:
        return len(self.open_cells)

    @property
    def width(self) -> int:
        return len(self.open_cells[0])

    def is_open(self, cell: Cell) -> bool:
        row, col = cell
        if not (0 <= row < self.height and 0 <= col < self.width):
            return False
        return self.open_cells[row][col]

    def open_neighbours(self, cell: Cell) -> Iterator[Cell]:
        row, col = cell
        for d_row, d_col in NEIGHBOUR_OFFSETS:
            neighbour = (row + d_row, col + d_col)
            if self.is_open(neighbour):
                yield neighbour


@dataclass(frozen=True)
class Waypoint:
    cell: Cell
    wait_frames: int = 0


@dataclass(frozen=True)
class Vehicle:
    id: str
    loudness: int
    frames_per_cell: int
    waypoints: tuple[Waypoint, ...]
    loop: bool


@dataclass(frozen=True)
class Detector:
    id: str
    cell: Cell


@dataclass(frozen=True)
class Scenario:
    name: str
    city_map: CityMap
    vehicles: tuple[Vehicle, ...]
    detectors: tuple[Detector, ...]
    threshold: int
    n_frames: int


def load_scenario(path: str | Path) -> Scenario:
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    # pyyaml's libyaml-backed loader parses the same documents several times faster. It rejects a few inputs
    # pyyaml's own scanner accepts (such as "{cell:[0, 0]}"), so any parse error retries with the original loader.
    try:
        raw = yaml.load(text, Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader))
    except yaml.YAMLError:
        raw = yaml.safe_load(text)
    return parse_scenario(raw, path.parent)


def parse_scenario(raw: dict, map_dir: Path) -> Scenario:
    """Builds and validates a Scenario from parsed scenario YAML; the map file is read from `map_dir`."""
    map_path = map_dir / _require(raw, "map", "scenario")
    scenario = Scenario(
        name=str(_require(raw, "name", "scenario")),
        city_map=CityMap.from_text(map_path.read_text(encoding="utf-8")),
        vehicles=tuple(_parse_vehicle(item) for item in _require(raw, "vehicles", "scenario")),
        detectors=tuple(_parse_detector(item) for item in _require(raw, "detectors", "scenario")),
        threshold=_parse_int(_require(raw, "threshold", "scenario"), "threshold"),
        n_frames=_parse_int(_require(raw, "n_frames", "scenario"), "n_frames"),
    )
    validate_scenario(scenario)
    return scenario


def _require(mapping: dict, key: str, context: str):
    if key not in mapping:
        raise ScenarioError(f"{context}: missing '{key}'")
    return mapping[key]


def _parse_int(value, context: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ScenarioError(f"{context}: expected an integer, got {value!r}")
    return value


def _parse_cell(value, context: str) -> Cell:
    if not isinstance(value, list) or len(value) != 2:
        raise ScenarioError(f"{context}: expected [row, col], got {value!r}")
    return (_parse_int(value[0], context), _parse_int(value[1], context))


def _parse_vehicle(raw: dict) -> Vehicle:
    vehicle_id = str(_require(raw, "id", "vehicle"))
    context = f"vehicle {vehicle_id}"
    waypoints = tuple(
        Waypoint(
            cell=_parse_cell(_require(item, "cell", context), context),
            wait_frames=_parse_int(item.get("wait_frames", 0), context),
        )
        for item in _require(raw, "waypoints", context)
    )
    return Vehicle(
        id=vehicle_id,
        loudness=_parse_int(_require(raw, "loudness", context), context),
        frames_per_cell=_parse_int(_require(raw, "frames_per_cell", context), context),
        waypoints=waypoints,
        loop=bool(raw.get("loop", False)),
    )


def _parse_detector(raw: dict) -> Detector:
    detector_id = str(_require(raw, "id", "detector"))
    context = f"detector {detector_id}"
    return Detector(id=detector_id, cell=_parse_cell(_require(raw, "cell", context), context))


def validate_scenario(scenario: Scenario) -> None:
    """Checks the rules every scenario must satisfy; raises ScenarioError on the first violation."""
    if scenario.threshold < 1:
        raise ScenarioError("threshold must be at least 1")
    if scenario.n_frames < 1:
        raise ScenarioError("n_frames must be at least 1")
    if not scenario.vehicles:
        raise ScenarioError("a scenario needs at least one vehicle")

    _check_unique([vehicle.id for vehicle in scenario.vehicles], "vehicle id")
    _check_unique([detector.id for detector in scenario.detectors], "detector id")
    _check_unique([detector.cell for detector in scenario.detectors], "detector cell")

    for vehicle in scenario.vehicles:
        _validate_vehicle(vehicle, scenario.city_map)

    for detector in scenario.detectors:
        if not scenario.city_map.is_open(detector.cell):
            raise ScenarioError(f"detector {detector.id} is not on an open cell: {detector.cell}")


def _check_unique(values: list, what: str) -> None:
    seen = set()
    for value in values:
        if value in seen:
            raise ScenarioError(f"duplicate {what}: {value!r}")
        seen.add(value)


def _validate_vehicle(vehicle: Vehicle, city_map: CityMap) -> None:
    context = f"vehicle {vehicle.id}"
    if vehicle.loudness < 1 or vehicle.frames_per_cell < 1:
        raise ScenarioError(f"{context}: loudness and frames_per_cell must be at least 1")
    if not vehicle.waypoints:
        raise ScenarioError(f"{context}: needs at least one waypoint")
    if vehicle.loop and len(vehicle.waypoints) < 2:
        raise ScenarioError(f"{context}: a looping route needs at least two waypoints")

    for waypoint in vehicle.waypoints:
        if not city_map.is_open(waypoint.cell):
            raise ScenarioError(f"{context}: waypoint {waypoint.cell} is not on an open cell")
        if waypoint.wait_frames < 0:
            raise ScenarioError(f"{context}: wait_frames must not be negative")

    # Every leg must actually go somewhere; for a loop that includes the closing leg.
    cells = [waypoint.cell for waypoint in vehicle.waypoints]
    legs = list(zip(cells, cells[1:]))
    if vehicle.loop:
        legs.append((cells[-1], cells[0]))
    for start, end in legs:
        if start == end:
            raise ScenarioError(f"{context}: consecutive waypoints must differ, both are {start}")
