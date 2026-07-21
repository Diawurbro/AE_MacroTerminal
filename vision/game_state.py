"""Game-state detection (lobby / loading / in-stage / result).

WHY: the executor's actions only make sense in one state. Teleporting,
normalizing the camera, and clicking placement coords while you're on a
loading screen or back in the lobby just misfires. This lets a run wait for
the right state before acting, instead of blindly running the sequence.

HOW IT WORKS: each state is identified by a small, distinctive crop of a UI
element that is ONLY on screen in that state. We `matchTemplate` each crop
against the current frame; the best match above `threshold` wins. Full-frame
matching would be fragile (the map scrolls, units move) - a tight crop of a
fixed HUD element is stable.

WHAT TO CAPTURE (drop PNGs in vision/templates/states/):
  in_stage.png - crop of the top HUD that's only shown mid-stage, e.g. the
                 "health / wave / enemies / time" bar. THE most useful one.
  lobby.png    - crop of a lobby-only element, e.g. the "Play" button or the
                 Store/Units/Quests menu column.
  loading.png  - crop of the loading screen (a logo / spinner). Optional; the
                 brightness heuristic below already flags a near-black frame.
  result.png   - crop of the victory/defeat banner (win/loss templates in
                 vision/templates/ already cover the finer win-vs-loss split).

Use the dashboard "Screenshot" button to grab a full frame in each state,
then crop tightly to the distinctive element with any image editor.

If a state's PNG is missing it simply can't be detected (returns "unknown"),
so this degrades safely: with no templates at all, detect() is a no-op that
always says "unknown" and the executor proceeds exactly as before.
"""

import os

import cv2
import numpy as np

from . import capture as vcap

STATES = ["in_stage", "lobby", "loading", "result"]


class GameStateDetector:
    def __init__(self, templates_dir: str, threshold: float = 0.75,
                 log=lambda m: None):
        self.threshold = threshold
        self.log = log
        self.states_dir = os.path.join(templates_dir, "states")
        self.templates: dict[str, np.ndarray] = {}
        for name in STATES:
            path = os.path.join(self.states_dir, f"{name}.png")
            if os.path.exists(path):
                img = vcap.load(path)
                if img is not None:
                    self.templates[name] = img
        if not self.templates:
            self.log(f"No game-state templates in {self.states_dir} - state "
                     "detection disabled (runs proceed without it).")

    def available(self) -> bool:
        return bool(self.templates)

    def detect(self, frame: np.ndarray) -> str:
        """Best-matching state for this frame, or 'unknown'."""
        # Near-black frame with no strong template hit = almost certainly a
        # loading/transition screen, even without a loading.png.
        best_state, best_score = "unknown", 0.0
        for name, tmpl in self.templates.items():
            if frame.shape[0] < tmpl.shape[0] or frame.shape[1] < tmpl.shape[1]:
                continue
            score, _ = vcap.match(frame, tmpl)
            if score > best_score:
                best_state, best_score = name, score
        if best_score >= self.threshold:
            return best_state
        if "loading" not in self.templates and self._mostly_dark(frame):
            return "loading"
        return "unknown"

    @staticmethod
    def _mostly_dark(frame: np.ndarray, thresh: int = 25, frac: float = 0.9) -> bool:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return float((gray < thresh).mean()) >= frac
