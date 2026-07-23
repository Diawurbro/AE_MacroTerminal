"""Find the Roblox window on macOS and read/set its position - the mac
counterpart to core/window_win.py's win32gui-based implementation.

Window discovery (CGWindowListCopyWindowInfo) and frame reads (AXUIElement)
were confirmed working via tools/mac_smoketest/2_window_discovery_test.py.
Moving/resizing the window (AXUIElementSetAttributeValue) follows the same
API family but hasn't been separately smoke-tested - if `layout()` doesn't
actually move the window, that's the first thing to check.

Coordinate units: tools/mac_smoketest/3_retina_scale_test.py confirmed that
on this machine mss's pixel output matches the CGWindowList/AX point values
directly (no backingScaleFactor multiplication needed) - so unlike the plan's
original worst case, this file does NOT scale anything. If a future Mac/mss
combination disagrees, that test script is where to re-check the math.
"""

import time

from core.client_rect import ClientRect

try:
    from Quartz import (
        CGWindowListCopyWindowInfo, kCGWindowListOptionOnScreenOnly,
        kCGNullWindowID, CGMainDisplayID, CGDisplayBounds,
    )
    from ApplicationServices import (
        AXUIElementCreateApplication, AXUIElementCopyAttributeValue,
        AXUIElementSetAttributeValue, AXValueCreate, AXValueGetValue,
        kAXValueCGPointType, kAXValueCGSizeType,
        kAXPositionAttribute, kAXSizeAttribute, kAXWindowsAttribute,
        kAXMinimizedAttribute, kAXErrorSuccess,
    )
    from AppKit import NSRunningApplication, NSWorkspace, NSApplicationActivateIgnoringOtherApps
    HAS_MAC_APIS = True
except ImportError:
    HAS_MAC_APIS = False


def enable_dpi_awareness():
    """No-op on mac - Retina/point-vs-pixel handling is per-API (see the
    module docstring), not a single process-wide flag like Windows' DPI
    awareness call."""
    pass


def _ax_point(value: tuple[float, float]):
    return AXValueCreate(kAXValueCGPointType, value)


def _ax_size(value: tuple[float, float]):
    return AXValueCreate(kAXValueCGSizeType, value)


class RobloxWindow:
    # How much room the dashboard needs beside/below the game to be usable -
    # a rough floor matching ui/main_window.py's MARGIN/GAP/COL_W, not an
    # exact mirror of it (this file shouldn't import Qt-side layout code).
    _SIDE_W_FLOOR = 24 * 2 + 16 + 340   # margins + gap + a usable column width
    _LOG_H_FLOOR = 24 * 2 + 16 + 120    # margins + gap + a usable log strip

    def __init__(self, cfg: dict):
        w = cfg["window"]
        self.title = w.get("window_title", "Roblox")
        # Reference size: what profiles/templates/OCR crops were calibrated
        # against. The ACTUAL on-screen size (self.cw/ch) may be smaller on a
        # screen that can't fit this beside the dashboard column - clicks are
        # unaffected (normalized coordinates), and vision/capture.py resizes
        # every capture back up to this reference size before any template
        # match/OCR happens, so a smaller on-screen window doesn't desync
        # anything calibrated at the reference resolution.
        self.ref_cw = w["client_width"]
        self.ref_ch = w["client_height"]
        self.cw = self.ref_cw
        self.ch = self.ref_ch
        # Mac has no window-class concept; match Roblox by owning process
        # name instead. Overridable in case the mac client's process name
        # ever differs from "Roblox".
        self.process_name = w.get("mac_process_name", "Roblox")
        self.hwnd = None       # CoreGraphics window number, once found
        self._pid = None
        self._ax_win = None    # cached AXUIElement for the window
        self._fit_to_screen()  # so cw/ch are already correct pre-attach too

    # ---------------- discovery ----------------

    def _fit_to_screen(self):
        """Shrink cw/ch (aspect-ratio preserved) if ref_cw x ref_ch can't fit
        beside the dashboard column on this screen. No-op (cw/ch stay at the
        reference size) when there's room - the normal case on a big enough
        display."""
        if not HAS_MAC_APIS:
            return
        bounds = CGDisplayBounds(CGMainDisplayID())
        sw, sh = bounds.size.width, bounds.size.height
        avail_w = max(200, sw - self._SIDE_W_FLOOR)
        avail_h = max(200, sh - self._LOG_H_FLOOR)
        scale = min(1.0, avail_w / self.ref_cw, avail_h / self.ref_ch)
        self.cw = max(1, int(self.ref_cw * scale))
        self.ch = max(1, int(self.ref_ch * scale))

    def find(self) -> int | None:
        if not HAS_MAC_APIS:
            return None
        self._fit_to_screen()
        info_list = CGWindowListCopyWindowInfo(
            kCGWindowListOptionOnScreenOnly, kCGNullWindowID)
        for w in info_list:
            owner = w.get("kCGWindowOwnerName", "") or ""
            if self.process_name.lower() in owner.lower():
                self.hwnd = w.get("kCGWindowNumber")
                self._pid = w.get("kCGWindowOwnerPID")
                self._ax_win = None  # re-resolve lazily
                return self.hwnd
        self.hwnd = None
        self._pid = None
        self._ax_win = None
        return None

    def is_alive(self) -> bool:
        if not self.hwnd or not HAS_MAC_APIS:
            return False
        info_list = CGWindowListCopyWindowInfo(
            kCGWindowListOptionOnScreenOnly, kCGNullWindowID)
        return any(w.get("kCGWindowNumber") == self.hwnd for w in info_list)

    def _ax_window(self):
        """The cached AXUIElement for this window, re-resolved if lost."""
        if self._ax_win is not None:
            return self._ax_win
        if not self._pid:
            return None
        app_ref = AXUIElementCreateApplication(self._pid)
        err, windows = AXUIElementCopyAttributeValue(app_ref, kAXWindowsAttribute, None)
        if err != kAXErrorSuccess or not windows:
            return None
        self._ax_win = windows[0]
        return self._ax_win

    # ---------------- layout ----------------

    def layout(self, left_bound: int = 0, bottom_bound: int = 0,
               pin: tuple[int, int] | None = None) -> ClientRect | None:
        """Position and size the window so the client area is cw x ch.

        Roblox on mac runs borderless in practice (content view fills the
        frame, confirmed by tools/mac_smoketest/2 - the AX size matched the
        CGWindowList bounds exactly, no title-bar inset), so unlike Windows
        there's no frame-padding to measure: outer frame == client area."""
        if not self.is_alive():
            return None
        win_ref = self._ax_window()
        if win_ref is None:
            return None

        if pin is not None:
            x, y = pin
        else:
            bounds = CGDisplayBounds(CGMainDisplayID())
            sw, sh = bounds.size.width, bounds.size.height
            avail_h = max(self.ch, sh - bottom_bound)
            x = max(left_bound, left_bound + (sw - left_bound - self.cw) // 2)
            y = max(0, (avail_h - self.ch) // 2)

        AXUIElementSetAttributeValue(win_ref, kAXPositionAttribute, _ax_point((x, y)))
        AXUIElementSetAttributeValue(win_ref, kAXSizeAttribute, _ax_size((self.cw, self.ch)))
        time.sleep(0.2)
        rect = self.client_rect()
        # Roblox enforces its own minimum window size (observed: clamps any
        # requested height below ~628pt back up to 628, width unaffected) -
        # not something we can override via AX. Treat whatever it actually
        # settled at as ground truth rather than the original target, so a
        # screen where _fit_to_screen's request lands below that floor still
        # ends up self-consistent (main.py compares against these, not the
        # unreachable original ask) instead of permanently warning.
        if rect is not None:
            self.cw, self.ch = rect.w, rect.h
        return rect

    def client_rect(self) -> ClientRect | None:
        """Borderless in practice - client area == window frame (see layout())."""
        return self.window_rect()

    def window_rect(self) -> ClientRect | None:
        if not self.is_alive():
            return None
        win_ref = self._ax_window()
        if win_ref is None:
            return None
        err_p, pos_val = AXUIElementCopyAttributeValue(win_ref, kAXPositionAttribute, None)
        err_s, size_val = AXUIElementCopyAttributeValue(win_ref, kAXSizeAttribute, None)
        if err_p != kAXErrorSuccess or err_s != kAXErrorSuccess:
            return None
        ok_p, point = AXValueGetValue(pos_val, kAXValueCGPointType, None)
        ok_s, size = AXValueGetValue(size_val, kAXValueCGSizeType, None)
        if not ok_p or not ok_s:
            return None
        return ClientRect(int(point.x), int(point.y), int(size.width), int(size.height))

    # ---------------- focus ----------------

    def focus(self):
        if not self.is_alive() or not self._pid:
            return
        app = NSRunningApplication.runningApplicationWithProcessIdentifier_(self._pid)
        if app is not None:
            app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
        time.sleep(0.12)

    def is_foreground(self) -> bool:
        if not self.is_alive() or not self._pid:
            return False
        front = NSWorkspace.sharedWorkspace().frontmostApplication()
        return front is not None and front.processIdentifier() == self._pid
