"""The fast path must give exactly the log of the original frame-by-frame simulation.

Random small scenarios cover the edge cases the examples may not: buildings splitting the map into regions,
loudness larger than the map, vehicles parked from frame 0, waits, loops, early cut-off with --max-frames,
detectors under a vehicle, and thresholds both trivially low and unreachable.
"""

import random
from collections import deque

import pytest

from citynoise import movement
from citynoise.detection import DetectionRecorder
from citynoise.fast import detection_log
from citynoise.scenario import CityMap, Detector, Scenario, ScenarioError, Vehicle, Waypoint, validate_scenario
from citynoise.simulation import Simulation


def original_shortest_path(city_map, start, goal):
    """The original simulator's FIFO BFS, kept verbatim as the oracle for route tie-breaking."""
    parents = {start: None}
    queue = deque([start])
    while queue:
        cell = queue.popleft()
        if cell == goal:
            path = []
            while cell is not None:
                path.append(cell)
                cell = parents[cell]
            return path[::-1]
        for neighbour in city_map.open_neighbours(cell):
            if neighbour not in parents:
                parents[neighbour] = cell
                queue.append(neighbour)
    raise ScenarioError(f"no open path from {start} to {goal}")


def reference_log(scenario, max_frames, monkeypatch):
    monkeypatch.setattr(movement, "shortest_path", original_shortest_path)
    recorder = DetectionRecorder(scenario)
    for state in Simulation(scenario).frames(max_frames):
        recorder.observe(state)
    monkeypatch.undo()
    return recorder.to_log()


def random_map(rng, height, width, density):
    rows = [["#" if rng.random() < density else "." for _ in range(width)] for _ in range(height)]
    return CityMap.from_text("\n".join("".join(row) for row in rows))


def largest_region(city_map):
    """Open cells of the biggest connected region, so vehicles always have a route."""
    seen, best = set(), []
    for row in range(city_map.height):
        for col in range(city_map.width):
            if (row, col) in seen or not city_map.is_open((row, col)):
                continue
            region, queue = [], deque([(row, col)])
            seen.add((row, col))
            while queue:
                cell = queue.popleft()
                region.append(cell)
                for neighbour in city_map.open_neighbours(cell):
                    if neighbour not in seen:
                        seen.add(neighbour)
                        queue.append(neighbour)
            best = max(best, region, key=len)
    return best


def random_scenario(rng):
    city_map = random_map(rng, rng.randint(1, 14), rng.randint(2, 16), rng.choice([0.0, 0.2, 0.35, 0.5]))
    region = largest_region(city_map)
    all_open = [(r, c) for r in range(city_map.height) for c in range(city_map.width) if city_map.is_open((r, c))]
    if len(region) < 2:
        return None

    vehicles = []
    for index in range(rng.randint(1, 5)):
        loop = rng.random() < 0.5
        count = rng.randint(2, 4) if loop else rng.randint(1, 4)
        cells = [rng.choice(region)]
        while len(cells) < count:
            cell = rng.choice(region)
            if cell != cells[-1]:
                cells.append(cell)
        if loop and cells[-1] == cells[0]:
            continue
        waits = [rng.choice([0, 0, 1, 5, 17]) for _ in cells]
        vehicles.append(Vehicle(f"v{index}", rng.randint(1, 80), rng.randint(1, 5),
                                tuple(Waypoint(c, w) for c, w in zip(cells, waits)), loop))
    if not vehicles:
        return None

    detector_cells = rng.sample(all_open, rng.randint(0, min(len(all_open), 12)))
    scenario = Scenario(
        name="random",
        city_map=city_map,
        vehicles=tuple(vehicles),
        detectors=tuple(Detector(f"d{i}", cell) for i, cell in enumerate(detector_cells)),
        threshold=rng.choice([1, 5, 20, 60, 500]),
        n_frames=rng.randint(1, 400),
    )
    validate_scenario(scenario)
    return scenario


@pytest.mark.parametrize("seed", range(300))
def test_fast_log_equals_original_simulation(seed, monkeypatch):
    rng = random.Random(seed)
    scenario = random_scenario(rng)
    if scenario is None:
        pytest.skip("no valid scenario for this seed")
    max_frames = rng.choice([None, None, 0, 1, rng.randint(1, scenario.n_frames + 50)])
    assert detection_log(scenario, max_frames) == reference_log(scenario, max_frames, monkeypatch)


@pytest.mark.parametrize("seed", range(200))
def test_shortest_path_matches_original_tie_breaking(seed):
    rng = random.Random(seed)
    city_map = random_map(rng, rng.randint(1, 25), rng.randint(1, 25), rng.choice([0.0, 0.25, 0.4]))
    region = largest_region(city_map)
    if not region:
        pytest.skip("map has no open cell")
    # Many legs on one map also checks that the reused scratch array is left clean between calls.
    for _ in range(25):
        start, goal = rng.choice(region), rng.choice(region)
        assert movement.shortest_path(city_map, start, goal) == original_shortest_path(city_map, start, goal)


def test_shortest_path_reports_unreachable_goal_and_stays_usable():
    city_map = CityMap.from_text(".#.\n...\n#.#")
    blocked = CityMap.from_text(".#.")
    with pytest.raises(ScenarioError):
        movement.shortest_path(blocked, (0, 0), (0, 2))
    assert movement.shortest_path(city_map, (0, 0), (0, 2)) == original_shortest_path(city_map, (0, 0), (0, 2))


def test_shortest_path_on_real_example_maps():
    from pathlib import Path

    from citynoise.scenario import load_scenario

    scenarios = Path(__file__).resolve().parent.parent / "scenarios"
    if not (scenarios / "big_city.yaml").exists():
        pytest.skip("example scenarios not present")
    for name in ("big_city", "long_patrol"):
        city_map = load_scenario(scenarios / f"{name}.yaml").city_map
        rng = random.Random(name)
        open_cells = [(r, c) for r in range(city_map.height) for c in range(city_map.width) if city_map.is_open((r, c))]
        for _ in range(20):
            start, goal = rng.choice(open_cells), rng.choice(open_cells)
            assert movement.shortest_path(city_map, start, goal) == original_shortest_path(city_map, start, goal)
