"""Command line: python -m citynoise run <scenario.yaml> [options]."""

import argparse
import json
import time
from pathlib import Path

from .detection import DetectionRecorder
from .fast import detection_log
from .render import animate, frame_digest
from .scenario import ScenarioError, load_scenario
from .simulation import Simulation

DEFAULT_LOG_PATH = Path("log.json")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="citynoise")
    commands = parser.add_subparsers(dest="command", required=True)

    run_command = commands.add_parser("run", help="run a scenario and write its detection log")
    run_command.add_argument("scenario", type=Path)
    run_command.add_argument("--out", type=Path, default=DEFAULT_LOG_PATH, help="where to write the detection log")
    run_command.add_argument("--max-frames", type=int, default=None, help="stop after this many frames")
    run_command.add_argument("--dump-frames", type=Path, default=None, help="write one digest per frame to this file")
    run_command.add_argument("--render", action="store_true", help="show the animation instead of writing a log")
    return parser


def run(args: argparse.Namespace) -> None:
    started = time.perf_counter()
    scenario = load_scenario(args.scenario)
    if not args.render and args.dump_frames is None:
        # The log needs only detector cells, so skip building a full noise map per frame.
        log = detection_log(scenario, args.max_frames)
        args.out.write_text(json.dumps(log) + "\n", encoding="utf-8")
        elapsed = time.perf_counter() - started
        print(f"scenario={scenario.name} frames={log['n_frames']} wall_clock={elapsed:.2f}s log={args.out}")
        return

    frames = Simulation(scenario).frames(args.max_frames)

    if args.render:
        animate(scenario, frames)
        return

    recorder = DetectionRecorder(scenario)
    if args.dump_frames is None:
        for state in frames:
            recorder.observe(state)
    else:
        with open(args.dump_frames, "w", encoding="utf-8") as dump:
            for state in frames:
                firing = recorder.observe(state)
                dump.write(frame_digest(state, firing) + "\n")

    args.out.write_text(json.dumps(recorder.to_log()) + "\n", encoding="utf-8")
    elapsed = time.perf_counter() - started
    print(f"scenario={scenario.name} frames={recorder.frames_seen} wall_clock={elapsed:.2f}s log={args.out}")


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        run(args)
    except ScenarioError as error:
        raise SystemExit(f"scenario error: {error}")
