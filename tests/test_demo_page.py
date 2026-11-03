"""The page's live demo must show what Echo computes: same firing on every frame, same noise everywhere.

Runs docs/model.js (the JavaScript model the page draws) under Node and compares it with the Python engines on
examples/demo.yaml. Skipped when Node is not installed.
"""

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
import yaml

from citynoise.fast import detection_log
from citynoise.scenario import load_scenario
from citynoise.simulation import Simulation

ROOT = Path(__file__).resolve().parent.parent
NODE = shutil.which("node")
SAMPLE_FRAMES = [0, 1, 2, 37, 250, 599, 600, 1000, 1199]

NODE_SCRIPT = r"""
const { buildModel } = require(process.argv[1]);
const input = JSON.parse(require("fs").readFileSync(0, "utf8"));
const m = buildModel(input.demo);
const intervals = input.demo.detectors.map(() => []);
for (let f = 0; f < m.n_frames; f++) {
  const noise = m.noiseAt(f);
  input.demo.detectors.forEach((d, i) => {
    const on = noise[d.cell[0] * m.W + d.cell[1]] >= m.threshold, list = intervals[i], last = list[list.length - 1];
    if (on && last && last[1] === f - 1) last[1] = f; else if (on) list.push([f, f]);
  });
}
const grids = Object.fromEntries(input.frames.map(f => [f, Array.from(m.noiseAt(f))]));
process.stdout.write(JSON.stringify({ intervals, grids }));
"""


@pytest.fixture(scope="module")
def page_model():
    if NODE is None:
        pytest.skip("Node.js not installed")
    raw = yaml.safe_load((ROOT / "examples/demo.yaml").read_text(encoding="utf-8"))
    city = [line for line in (ROOT / "examples" / raw["map"]).read_text(encoding="utf-8").splitlines() if line]
    demo = {**raw, "map": city}
    result = subprocess.run(
        [NODE, "-e", NODE_SCRIPT, str(ROOT / "docs/model.js")],
        input=json.dumps({"demo": demo, "frames": SAMPLE_FRAMES}),
        capture_output=True, text=True, check=True, timeout=300,
    )
    return json.loads(result.stdout)


def test_page_fires_the_same_detectors_as_echo_on_every_frame(page_model):
    log = detection_log(load_scenario(ROOT / "examples/demo.yaml"))
    assert page_model["intervals"] == [detector["intervals"] for detector in log["detectors"]]


def test_page_noise_matches_the_original_simulator_everywhere(page_model):
    scenario = load_scenario(ROOT / "examples/demo.yaml")
    for state in Simulation(scenario).frames(max(SAMPLE_FRAMES) + 1):
        if state.frame in SAMPLE_FRAMES:
            page = np.array(page_model["grids"][str(state.frame)]).reshape(state.noise.shape)
            assert np.array_equal(page, state.noise), f"noise differs on frame {state.frame}"
