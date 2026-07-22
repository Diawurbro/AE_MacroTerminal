"""Win/loss detection (Phase 4).

Primary path: template match victory.png / defeat.png from vision/templates/.
Those need to be cropped from real game screenshots, which don't exist yet
(HANDOFF open item 3), so there's a fallback: a green-vs-red color ratio
check on the result panel ROI. The executor still requires the SAME
classification on 2 consecutive polls before it trusts it, whichever path
produced it.
"""

import os

import cv2
import numpy as np

from . import capture as vcap

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")


class ResultDetector:
    def __init__(self, cfg, template_dir: str | None = None, log=lambda m: None):
        """template_dir should be BASE-relative (main.py app_dir()), not
        module-relative - in a frozen build __file__ resolves inside the
        PyInstaller _internal bundle, which isn't where a user would think
        to drop victory.png/defeat.png. Falls back to the source-tree
        location for standalone/dev use."""
        self.template_dir = template_dir or TEMPLATE_DIR
        self.threshold = cfg["vision"]["result_match_threshold"]
        self.victory = self._load("victory.png")
        self.defeat = self._load("defeat.png")
        if self.victory is None and self.defeat is None:
            log(f"No win/loss templates in {self.template_dir} - falling back "
                "to a colour ratio, which does NOT work for this game (its "
                "victory ribbon is blue, not green). Add victory.png.")
        elif self.defeat is None:
            log("defeat.png missing - result-screen classification still works "
                "(no victory ribbon on a result screen means a loss); only the "
                "in-match banner check is degraded.")

    def _load(self, name):
        path = os.path.join(self.template_dir, name)
        return vcap.load(path) if os.path.exists(path) else None

    def classify_frame(self, frame: np.ndarray, result_roi: list[float]) -> str | None:
        """Returns 'win' | 'loss' | None for a single frame.

        The template path matches inside result_roi (+ margin), not the full
        frame: this runs every poll for the entire match (the longest loop of
        a run), and two full-frame matchTemplate calls per poll burned enough
        CPU to make the whole app feel slow (RELEASE_REVIEW 1.6). The banner
        templates were cut from inside that region; if the ROI is ever mis-set
        the banner check degrades but match end is still caught by the reward
        caption / result screen signals (HANDOFF 2.31)."""
        if self.victory is not None and self.defeat is not None:
            return self._template(self._crop(frame, result_roi))
        return self._color_ratio(frame, result_roi)

    @staticmethod
    def _crop(frame: np.ndarray, roi, margin: float = 0.06) -> np.ndarray:
        """result_roi expanded by `margin` (normalized), clamped to the frame.
        Falls back to the full frame when the ROI is missing/degenerate."""
        if not roi or len(roi) != 4:
            return frame
        h, w = frame.shape[:2]
        x1 = max(0, int((roi[0] - margin) * w))
        y1 = max(0, int((roi[1] - margin) * h))
        x2 = min(w, int((roi[2] + margin) * w))
        y2 = min(h, int((roi[3] + margin) * h))
        crop = frame[y1:y2, x1:x2]
        return crop if crop.size else frame

    def classify_result_screen(self, frame: np.ndarray) -> str:
        """Win/loss on a frame the caller has ALREADY confirmed is the result
        screen. That confirmation is what makes a negative match meaningful:
        no victory ribbon on a result screen means a loss, so this works with
        only victory.png and doesn't need defeat.png to exist.

        The colour fallback is no help here - this game's victory ribbon is
        BLUE, so a green-vs-red ratio reads a win as neither."""
        if self.victory is not None and self._score(frame, self.victory) >= self.threshold:
            return "win"
        if self.defeat is not None and self._score(frame, self.defeat) >= self.threshold:
            return "loss"
        if self.victory is not None:
            return "loss"       # result screen, no victory ribbon
        return "unknown"

    def _template(self, frame):
        wv = self._score(frame, self.victory)
        wd = self._score(frame, self.defeat)
        if wv >= self.threshold and wv >= wd:
            return "win"
        if wd >= self.threshold and wd > wv:
            return "loss"
        return None

    @staticmethod
    def _score(frame, template):
        if frame.shape[0] < template.shape[0] or frame.shape[1] < template.shape[1]:
            return 0.0
        score, _ = vcap.match(frame, template)
        return score

    @staticmethod
    def _color_ratio(frame, result_roi):
        x1, y1, x2, y2 = result_roi
        h, w = frame.shape[:2]
        crop = frame[int(y1 * h):int(y2 * h), int(x1 * w):int(x2 * w)]
        if crop.size == 0:
            return None
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        green = cv2.inRange(hsv, (35, 60, 60), (85, 255, 255))
        red1 = cv2.inRange(hsv, (0, 60, 60), (10, 255, 255))
        red2 = cv2.inRange(hsv, (170, 60, 60), (180, 255, 255))
        red = cv2.bitwise_or(red1, red2)
        total = crop.shape[0] * crop.shape[1]
        g_ratio = cv2.countNonZero(green) / total
        r_ratio = cv2.countNonZero(red) / total
        if g_ratio < 0.15 and r_ratio < 0.15:
            return None
        return "win" if g_ratio > r_ratio else "loss"
