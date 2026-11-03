"""Generate a random city scenario: a block-grid map, vehicles on random routes, and detectors.

    python tools/make_scenario.py examples/demo --height 40 --width 64 --vehicles 6 --detectors 24 --frames 1200

Writes <out>.yaml and <out>_map.txt. The same seed always gives the same scenario.
"""

import argparse
import random
from pathlib import Path

import yaml


def city_map(rng: random.Random, height: int, width: int) -> list[str]:
    """Rectangular blocks separated by 2-cell streets, with some blocks carved into courtyards or left open."""
    grid = [["." for _ in range(width)] for _ in range(height)]
    row = 2
    while row < height - 2:
        block_h = rng.randint(4, 9)
        col = 2
        while col < width - 2:
            block_w = rng.randint(5, 12)
            if rng.random() < 0.85:  # some lots stay open as plazas
                for r in range(row, min(row + block_h, height - 2)):
                    for c in range(col, min(col + block_w, width - 2)):
                        grid[r][c] = "#"
                if block_h > 5 and block_w > 6 and rng.random() < 0.3:  # courtyard with one entrance
                    for r in range(row + 2, min(row + block_h - 2, height - 2)):
                        for c in range(col + 2, min(col + block_w - 2, width - 2)):
                            grid[r][c] = "."
                    grid[row + 2][col] = grid[row + 2][col + 1] = "."
            col += block_w + 2
        row += block_h + 2
    return ["".join(line) for line in grid]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("out", type=Path, help="output path without extension")
    parser.add_argument("--height", type=int, default=40)
    parser.add_argument("--width", type=int, default=64)
    parser.add_argument("--vehicles", type=int, default=6)
    parser.add_argument("--detectors", type=int, default=24)
    parser.add_argument("--frames", type=int, default=1200)
    parser.add_argument("--threshold", type=int, default=20)
    parser.add_argument("--loudness", type=int, nargs=2, default=[15, 35], metavar=("MIN", "MAX"))
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    lines = city_map(rng, args.height, args.width)
    open_cells = [[r, c] for r, line in enumerate(lines) for c, ch in enumerate(line) if ch == "."]

    vehicles = []
    for index in range(args.vehicles):
        cells = [rng.choice(open_cells)]
        while len(cells) < rng.randint(2, 5):
            cell = rng.choice(open_cells)
            if cell != cells[-1]:
                cells.append(cell)
        loop = rng.random() < 0.7 and cells[-1] != cells[0]
        vehicles.append({
            "id": f"vehicle_{index}",
            "loudness": rng.randint(*args.loudness),
            "frames_per_cell": rng.randint(1, 4),
            "loop": loop,
            "waypoints": [{"cell": cell, "wait_frames": rng.choice([0, 0, 10, 30])} for cell in cells],
        })
    detectors = [{"id": f"detector_{i}", "cell": cell} for i, cell in enumerate(rng.sample(open_cells, args.detectors))]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    map_path = args.out.with_name(args.out.name + "_map.txt")
    map_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    scenario = {"name": args.out.name, "n_frames": args.frames, "threshold": args.threshold, "map": map_path.name,
                "vehicles": vehicles, "detectors": detectors}
    args.out.with_suffix(".yaml").write_text(yaml.safe_dump(scenario, sort_keys=False), encoding="utf-8")
    print(f"wrote {args.out.with_suffix('.yaml')} and {map_path}")


if __name__ == "__main__":
    main()
