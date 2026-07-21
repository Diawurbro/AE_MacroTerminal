"""Screen capture scoped to the Roblox client area, plus template matching."""

import numpy as np

try:
    import cv2
    import mss
    HAS_CV = True
except ImportError:
    HAS_CV = False


class Capture:
    def __init__(self):
        self._sct = mss.mss() if HAS_CV else None

    def grab(self, rect) -> np.ndarray:
        """rect: ClientRect. Returns BGR array."""
        mon = {"left": rect.x, "top": rect.y, "width": rect.w, "height": rect.h}
        raw = self._sct.grab(mon)
        return cv2.cvtColor(np.array(raw), cv2.COLOR_BGRA2BGR)

    def grab_roi(self, rect, roi: list[float]) -> np.ndarray:
        """roi: [x1, y1, x2, y2] normalized 0-1 within the client area."""
        x1, y1, x2, y2 = roi
        mon = {
            "left": int(rect.x + x1 * rect.w),
            "top": int(rect.y + y1 * rect.h),
            "width": max(1, int((x2 - x1) * rect.w)),
            "height": max(1, int((y2 - y1) * rect.h)),
        }
        raw = self._sct.grab(mon)
        return cv2.cvtColor(np.array(raw), cv2.COLOR_BGRA2BGR)


def match(haystack: np.ndarray, needle: np.ndarray) -> tuple[float, tuple[int, int]]:
    """Returns (score, top-left position of best match)."""
    res = cv2.matchTemplate(haystack, needle, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)
    return float(max_val), max_loc


def similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Whole-frame similarity. Used to verify the camera is back to the
    same angle as the stage reference image."""
    if a.shape != b.shape:
        b = cv2.resize(b, (a.shape[1], a.shape[0]))
    ga = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY)
    gb = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY)
    res = cv2.matchTemplate(ga, gb, cv2.TM_CCOEFF_NORMED)
    return float(res.max())


def region_changed(before: np.ndarray, after: np.ndarray, threshold: float = 0.90) -> bool:
    """True if the region visibly changed - used to confirm a unit was placed."""
    return similarity(before, after) < threshold


def save(img: np.ndarray, path: str):
    cv2.imwrite(path, img)


def load(path: str) -> np.ndarray:
    return cv2.imread(path, cv2.IMREAD_COLOR)
