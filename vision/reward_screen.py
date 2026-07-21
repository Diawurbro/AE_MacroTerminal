"""Post-match reward screens - the "(Click anywhere to close) [N/5]" sequence.

When a match ends the game shows a run of item-reward screens before the
result screen (the one with Repeat). Every one of them carries the same
caption at the bottom centre, so the caption's PRESENCE is the whole signal:
click, re-check, and stop the moment it's gone - which is exactly when the
result screen is up.

Deliberately not counting clicks. The caption does show [N/M], but M varies
per run and reading it needs Tesseract, while presence detection needs
nothing but the template. Counting a fixed 5-6 clicks would also risk one
click landing on the result screen's buttons - "Back to lobby" is right
there. Checking before every click makes that impossible: the last click can
only ever happen while a reward screen is still up.

The template is the caption text ONLY, cropped without the [N/M] counter,
since that part changes between screens.
"""

import os

import numpy as np

from . import capture as vcap

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")


class RewardScreenDetector:
    def __init__(self, cfg, template_dir: str | None = None, log=lambda m: None):
        """template_dir should be BASE-relative (main.py app_dir()), not
        module-relative - in a frozen build __file__ lands inside the
        PyInstaller _internal bundle. Same reasoning as result_detector.py."""
        self.template_dir = template_dir or TEMPLATE_DIR
        self.threshold = cfg.get("vision", {}).get("reward_match_threshold", 0.70)
        self.result_threshold = cfg.get("vision", {}).get("result_match_threshold", 0.85)
        self.tpl = self._load("reward_close.png")
        if self.tpl is None:
            log(f"reward_close.png missing in {self.template_dir} - post-match "
                "reward screens will not be clicked through automatically.")
        # The "Repeat Stage" button. Its presence is how we know the reward
        # sequence is over and the result screen is up.
        self.repeat_tpl = self._load("result_repeat.png")
        if self.repeat_tpl is None:
            log(f"result_repeat.png missing in {self.template_dir} - the result "
                "screen can't be detected, so auto-repeat is disabled.")

    def _load(self, name):
        path = os.path.join(self.template_dir, name)
        return vcap.load(path) if os.path.exists(path) else None

    def available(self) -> bool:
        return self.tpl is not None

    def repeat_available(self) -> bool:
        return self.repeat_tpl is not None

    def result_screen(self, roi_img: np.ndarray) -> tuple[bool, float]:
        """(is_showing, score) for the result screen, matched on its Repeat
        Stage button. Uses the stricter result_match_threshold - that button
        is a plain rounded rect and scores higher against unrelated frames
        (~0.50) than the reward caption does (~0.16)."""
        return self._match(roi_img, self.repeat_tpl, self.result_threshold)

    def present(self, roi_img: np.ndarray) -> tuple[bool, float]:
        """(is_showing, score) for a crop of the caption region.

        Measured on real captures: reward screens score 0.84-1.00, gameplay
        frames 0.07-0.16. The 0.70 default sits in that gap with room on both
        sides - the spread within the positives is just sub-pixel scaling
        from slightly different window widths."""
        return self._match(roi_img, self.tpl, self.threshold)

    @staticmethod
    def _match(roi_img, tpl, threshold) -> tuple[bool, float]:
        if tpl is None or roi_img is None or roi_img.size == 0:
            return False, 0.0
        th, tw = tpl.shape[:2]
        h, w = roi_img.shape[:2]
        if h < th or w < tw:
            # matchTemplate raises if the needle is larger than the haystack.
            return False, 0.0
        try:
            score, _ = vcap.match(roi_img, tpl)
        except Exception:
            return False, 0.0
        return score >= threshold, score
