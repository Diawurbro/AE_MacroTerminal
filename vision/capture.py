"""Screen capture scoped to the Roblox client area, plus template matching."""

import numpy as np

try:
    import cv2
    import mss
    HAS_CV = True
except ImportError:
    HAS_CV = False


class Capture:
    def __init__(self, ref_size: tuple[int, int] | None = None):
        """ref_size: (width, height) the templates/OCR crops were calibrated
        at (config.window.client_width/height). On a screen too small to fit
        the game at that size beside the dashboard column, the window backend
        may run Roblox smaller on-screen than ref_size (see
        core/window_mac.py's _fit_to_screen) - clicks are unaffected (they use
        normalized 0-1 coordinates) but template matching/OCR need pixels at
        the ORIGINAL calibrated scale, so every capture here is resized up (or
        down) to ref_size before being handed to a caller. A no-op when the
        actual window is already ref_size (the normal Windows case today)."""
        self._sct = mss.mss() if HAS_CV else None
        self.ref_w, self.ref_h = ref_size or (None, None)

    def _to_ref_scale(self, img: np.ndarray, target_w: int, target_h: int) -> np.ndarray:
        h, w = img.shape[:2]
        if w == target_w and h == target_h:
            return img
        return cv2.resize(img, (target_w, target_h))

    def grab(self, rect) -> np.ndarray:
        """rect: ClientRect. Returns BGR array, resized to ref_size if set."""
        mon = {"left": rect.x, "top": rect.y, "width": rect.w, "height": rect.h}
        raw = self._sct.grab(mon)
        img = cv2.cvtColor(np.array(raw), cv2.COLOR_BGRA2BGR)
        if self.ref_w:
            img = self._to_ref_scale(img, self.ref_w, self.ref_h)
        return img

    def grab_roi(self, rect, roi: list[float]) -> np.ndarray:
        """roi: [x1, y1, x2, y2] normalized 0-1 within the client area.
        Returned at ref_size's scale (if set), not the actual window's pixel
        scale - so a normalized ROI always crops the same relative patch at
        the same pixel size templates/OCR were calibrated against."""
        x1, y1, x2, y2 = roi
        mon = {
            "left": int(rect.x + x1 * rect.w),
            "top": int(rect.y + y1 * rect.h),
            "width": max(1, int((x2 - x1) * rect.w)),
            "height": max(1, int((y2 - y1) * rect.h)),
        }
        raw = self._sct.grab(mon)
        img = cv2.cvtColor(np.array(raw), cv2.COLOR_BGRA2BGR)
        if self.ref_w:
            target_w = max(1, round((x2 - x1) * self.ref_w))
            target_h = max(1, round((y2 - y1) * self.ref_h))
            img = self._to_ref_scale(img, target_w, target_h)
        return img


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
