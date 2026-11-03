"""Inputs where a faster building block behaves differently from the original, found by an independent review."""

import json

from citynoise.cli import main
from citynoise.scenario import load_scenario

MAP = ".....\n.....\n"


def write_scenario(tmp_path, body: str) -> str:
    (tmp_path / "map.txt").write_text(MAP, encoding="utf-8")
    path = tmp_path / "s.yaml"
    path.write_text("name: s\nn_frames: 10\nthreshold: 1\nmap: map.txt\n" + body, encoding="utf-8")
    return str(path)


def test_flow_mapping_without_space_after_colon_loads(tmp_path):
    # libyaml rejects "{cell:[0, 0]}"; pyyaml's own scanner (the original's loader) accepts it.
    path = write_scenario(tmp_path, (
        "vehicles:\n  - id: v\n    loudness: 3\n    frames_per_cell: 1\n"
        "    waypoints:\n      - {cell:[0, 0]}\n      - {cell: [0, 4]}\n"
        "detectors:\n  - {id: a, cell:[1, 1]}\n"
    ))
    scenario = load_scenario(path)
    assert scenario.vehicles[0].waypoints[0].cell == (0, 0)
    assert scenario.detectors[0].cell == (1, 1)


def test_waits_beyond_64_bits_fall_back_to_the_frame_by_frame_engine(tmp_path):
    path = write_scenario(tmp_path, (
        "vehicles:\n  - id: v\n    loudness: 3\n    frames_per_cell: 1\n"
        f"    waypoints:\n      - {{cell: [0, 0], wait_frames: {2 ** 63}}}\n      - {{cell: [0, 4]}}\n"
        "detectors:\n  - {id: a, cell: [0, 0]}\n"
    ))
    out = tmp_path / "log.json"
    main(["run", path, "--out", str(out)])
    assert json.loads(out.read_text())["detectors"] == [{"id": "a", "intervals": [[0, 9]]}]
