"""Detection: which detectors fire on each frame, collected into intervals for the log."""

from .scenario import Detector, Scenario
from .simulation import FrameState


def detector_firing(state: FrameState, detectors: tuple[Detector, ...], threshold: int) -> list[bool]:
    return [int(state.noise[detector.cell]) >= threshold for detector in detectors]


class DetectionRecorder:
    """Turns per-frame firing into maximal, inclusive (start, end) intervals per detector."""

    def __init__(self, scenario: Scenario):
        self.scenario = scenario
        self.intervals = {detector.id: [] for detector in scenario.detectors}
        self._firing_since = {detector.id: None for detector in scenario.detectors}
        self.frames_seen = 0

    def observe(self, state: FrameState) -> list[bool]:
        firing = detector_firing(state, self.scenario.detectors, self.scenario.threshold)
        for detector, is_firing in zip(self.scenario.detectors, firing):
            self._update(detector.id, is_firing, state.frame)
        self.frames_seen = state.frame + 1
        return firing

    def _update(self, detector_id: str, is_firing: bool, frame: int) -> None:
        started = self._firing_since[detector_id]
        if is_firing and started is None:
            self._firing_since[detector_id] = frame
        elif not is_firing and started is not None:
            self.intervals[detector_id].append((started, frame - 1))
            self._firing_since[detector_id] = None

    def to_log(self) -> dict:
        """The detection log; an interval still open is closed at the last frame seen."""
        detectors = []
        for detector in self.scenario.detectors:
            intervals = list(self.intervals[detector.id])
            started = self._firing_since[detector.id]
            if started is not None:
                intervals.append((started, self.frames_seen - 1))
            detectors.append({"id": detector.id, "intervals": [[start, end] for start, end in intervals]})
        return {"scenario": self.scenario.name, "n_frames": self.frames_seen, "detectors": detectors}
