"""Build docs/index.html from docs/index.template.html, embedding the demo scenario for the live city."""

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
scenario = yaml.safe_load((ROOT / "examples/demo.yaml").read_text(encoding="utf-8"))
city = [line for line in (ROOT / "examples" / scenario["map"]).read_text(encoding="utf-8").splitlines() if line]
demo = {
    "map": city,
    "vehicles": scenario["vehicles"],
    "detectors": scenario["detectors"],
    "threshold": scenario["threshold"],
    "n_frames": scenario["n_frames"],
}
template = (ROOT / "docs/index.template.html").read_text(encoding="utf-8")
scripts = [(ROOT / "docs" / name).read_text(encoding="utf-8") for name in ("model.js", "city.js")]
template = template.replace("/*CITY_SCRIPT*/", "\n".join(scripts))
(ROOT / "docs/index.html").write_text(template.replace("/*DEMO_DATA*/null", json.dumps(demo)), encoding="utf-8")
print("wrote docs/index.html")
