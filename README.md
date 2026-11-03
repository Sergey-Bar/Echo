# Echo

**Hear the whole city in a second.** Echo works out which noise detectors fire across a simulated city, frame by
frame, with exactly the same answer as the original frame-by-frame simulator. Runs that took hours now take
seconds.

**[See the live page, with the city running in your browser](https://sergey-bar.github.io/Echo/)**

| Workload | Original simulator | Echo | Speed-up |
|---|---:|---:|---:|
| Busy city: 80 vehicles, 20 detectors, 50,000 frames | ~42 h (projected) | 0.53 s | ~285,000× |
| Sensor grid: 6 vehicles, 12,000 detectors, 30,000 frames | ~7 h (projected) | 6.7 s | ~3,800× |
| Long patrol: 12 vehicles, 6,000 detectors, 45,000 frames | ~6 h (projected) | 3.7 s | ~5,800× |
| Big city: 400×400 map, 2,000 detectors, 14,000 frames | ~6.5 h (projected) | 3.2 s | ~7,300× |
| Included demo city (`examples/demo.yaml`) | 10.6 s | 0.03 s | ~350× |

Measured on one CPU core in a Linux container with a 4 GB memory cap. "Projected" means extrapolated from the
original simulator's first 20 frames, because full runs take hours.

## The problem

Vehicles drive through a grid city. Each vehicle's noise at a cell is `max(0, loudness − steps)`, where `steps`
is the street distance (up/down/left/right through open cells). Sound never passes through buildings. A detector
fires on a frame when the noise from all vehicles adds up to at least a threshold. The output lists, for every
detector, the exact frame intervals during which it fired.

The original simulator rebuilt a full noise map with a fresh breadth-first search for every vehicle on every
frame. Echo produces a log identical to it, within these limits: up to 400×400 cells, 100 vehicles, 20,000
detectors, 50,000 frames and loudness 80, on one core with 4 GB.

## How it works

1. **Listen from the detectors.** The log only needs noise at detector cells. Echo runs one breadth-first search
   from each detector, out to the loudest vehicle's reach. Street distance is symmetric, so these are exactly the
   distances the simulator computed from each vehicle.
2. **Turn routes into segments.** A vehicle's noise only changes when it moves to another cell. Each vehicle
   becomes a list of `(cell, first frame, end frame)`. A looping vehicle repeats its lap, so Echo builds one lap
   and copies it shifted in time.
3. **Add up changes, not frames.** Each segment adds `loudness − steps` to every detector in reach at its first
   frame and subtracts it at its end (`numpy.bincount`). One cumulative sum then gives every detector's exact
   noise on every frame. Comparing with the threshold gives the firing intervals.

**The route trick.** Vehicles follow shortest paths. When several are equally short, the simulator's FIFO queue
keeps the first parent that reaches each cell. That rule always yields the *lexicographically smallest*
shortest path, reading moves in up < down < left < right order: the queue holds each level in the order of its
cells' parent chains. So Echo runs one distance-only search from the goal, then walks from the start, always
taking the first direction that gets one step closer. That gives the same routes with far less work.

Detectors are processed in blocks, so memory stays bounded at every size.

## Proof it is exact

- `tests/test_equivalence.py` compares Echo with the original frame-by-frame simulator on **300 random
  cities** built to hit edge cases. They include walled-off regions, vehicles louder than the map, parked
  vehicles, waits, loops, runs cut short (`--max-frames` 0, 1, beyond the end), no detectors, and thresholds
  from trivial to unreachable.
- **5,000 random routes** are compared with the original path search, including an unreachable goal.
- The tests were checked by breaking the code on purpose: changing `>=` to `>` makes them fail. They also caught
  a real bug during development.
- `python -m citynoise run examples/demo.yaml --dump-frames frames.txt` forces the original engine, so anyone
  can compare its log with Echo's on any city.

## Pushed to the limits

Synthetic cities that stress every limit at once, run on **one core with a hard 4 GB cap and no swap**:

| City | Time | Peak memory |
|---|---:|---:|
| 100 looping vehicles, 20,000 detectors, 50,000 frames, 400×400 | 169 s | 875 MB |
| 100 one-way vehicles with 150 stops each, 20,000 detectors, 50,000 frames | 277 s | 929 MB |

## Run it

Requires Python 3.12+.

```bash
pip install -r requirements.txt
python -m citynoise run examples/demo.yaml            # writes log.json
python -m citynoise run examples/demo.yaml --render   # watch it (original frame-by-frame engine)
python tools/make_scenario.py examples/mine --vehicles 20 --detectors 500 --frames 20000
python -m pytest tests
```

The plain run uses the Echo engine. `--render` and `--dump-frames` need a full noise map for every frame, so
they use the original frame-by-frame engine.

## Project layout

```
citynoise/fast.py       Echo engine: detector searches, vehicle segments, change events, intervals
citynoise/movement.py   routes, with the lexicographic shortest-path planner
citynoise/              the rest of the simulator: scenario loading, rendering, CLI
tests/                  equivalence tests against the original simulator
tools/make_scenario.py  random city generator
examples/               demo city
docs/                   the project page (GitHub Pages)
```

## Credits

Built by [Sergey Bar](https://github.com/Sergey-Bar) with Claude Code and a custom agent setup. The baseline
frame-by-frame simulator was provided as a performance challenge. Echo's engine, route planner, tests,
benchmarks and page are built on top of it.
