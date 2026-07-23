"""Find the Roblox window, force a known client size, keep it centered."""

import ctypes
import time
from dataclasses import dataclass

try:
    import win32api
    import win32con
    import win32gui
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False


def enable_dpi_awareness():
    """Must run before any Qt window is created, or every coordinate is wrong."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


@dataclass
class ClientRect:
    x: int
    y: int
    w: int
    h: int

    def to_screen(self, nx: float, ny: float) -> tuple[int, int]:
        """Normalized 0-1 coords -> absolute screen pixels."""
        return int(self.x + nx * self.w), int(self.y + ny * self.h)

    def to_norm(self, sx: int, sy: int) -> tuple[float, float]:
        return (sx - self.x) / self.w, (sy - self.y) / self.h

    def as_tuple(self) -> tuple[int, int, int, int]:
        return self.x, self.y, self.w, self.h


class RobloxWindow:
    def __init__(self, cfg: dict):
        w = cfg["window"]
        self.title = w["window_title"]
        self.cls = w["window_class"]
        self.cw = w["client_width"]
        self.ch = w["client_height"]
        self.hwnd = None

    def find(self) -> int | None:
        if not HAS_WIN32:
            return None
        found = []

        def cb(hwnd, _):
            if not win32gui.IsWindowVisible(hwnd):
                return True
            try:
                cls = win32gui.GetClassName(hwnd)
                title = win32gui.GetWindowText(hwnd).strip()
            except Exception:
                return True
            if cls == self.cls and title == self.title:
                found.append(hwnd)
            return True

        win32gui.EnumWindows(cb, None)
        self.hwnd = found[0] if found else None
        return self.hwnd

    def is_alive(self) -> bool:
        return bool(self.hwnd and HAS_WIN32 and win32gui.IsWindow(self.hwnd))

    def _frame_padding(self) -> tuple[int, int]:
        """Difference between outer window size and inner client size."""
        wl, wt, wr, wb = win32gui.GetWindowRect(self.hwnd)
        cl, ct, cr, cb = win32gui.GetClientRect(self.hwnd)
        return (wr - wl) - (cr - cl), (wb - wt) - (cb - ct)

    def layout(self, left_bound: int = 0, bottom_bound: int = 0,
               pin: tuple[int, int] | None = None) -> ClientRect | None:
        """Restore and resize so the CLIENT area is exactly cw x ch, then place
        the window.

        pin=(x, y) puts the OUTER window's top-left at those screen coords -
        used by the L-dock, which pins the game top-left so the column to its
        right and the strip beneath it are free (the client then lands a few px
        inset by the frame, and the caller positions the docks off the returned
        client rect, so the exact inset doesn't matter). With pin=None it
        centers in the free area instead: right of left_bound, above
        bottom_bound.

        Retries once with freshly-measured padding - right after SW_RESTORE the
        window rect can still be settling, so the first padding read can be
        stale and the resulting SetWindowPos undershoots."""
        if not self.is_alive():
            return None

        placement = win32gui.GetWindowPlacement(self.hwnd)
        if placement[1] in (win32con.SW_SHOWMAXIMIZED, win32con.SW_SHOWMINIMIZED):
            win32gui.ShowWindow(self.hwnd, win32con.SW_RESTORE)
            time.sleep(0.35)

        rect = None
        for _ in range(2):
            pad_w, pad_h = self._frame_padding()
            total_w = self.cw + pad_w
            total_h = self.ch + pad_h

            if pin is not None:
                x, y = pin
            else:
                sw = win32api.GetSystemMetrics(win32con.SM_CXSCREEN)
                sh = win32api.GetSystemMetrics(win32con.SM_CYSCREEN)
                avail_h = max(total_h, sh - bottom_bound)
                x = max(left_bound, left_bound + (sw - left_bound - total_w) // 2)
                y = max(0, (avail_h - total_h) // 2)

            ok = win32gui.SetWindowPos(
                self.hwnd, win32con.HWND_TOP, x, y, total_w, total_h,
                win32con.SWP_SHOWWINDOW,
            )
            time.sleep(0.2)
            rect = self.client_rect()
            if not ok or rect is None:
                break
            if rect.w == self.cw and rect.h == self.ch:
                break
        return rect

    def client_rect(self) -> ClientRect | None:
        if not self.is_alive():
            return None
        cl, ct, cr, cb = win32gui.GetClientRect(self.hwnd)
        ox, oy = win32gui.ClientToScreen(self.hwnd, (0, 0))
        return ClientRect(ox, oy, cr - cl, cb - ct)

    def window_rect(self) -> ClientRect | None:
        """The OUTER window rectangle (title bar + borders + client), in screen
        px. The dashboard mask cuts its hole to this so the WHOLE Roblox window
        shows through, not just the client area."""
        if not self.is_alive():
            return None
        wl, wt, wr, wb = win32gui.GetWindowRect(self.hwnd)
        return ClientRect(wl, wt, wr - wl, wb - wt)

    def focus(self):
        if not self.is_alive():
            return
        try:
            win32gui.SetForegroundWindow(self.hwnd)
        except Exception:
            # SetForegroundWindow fails when our process has no input focus.
            # ALT tap releases the lock.
            win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
            win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
            try:
                win32gui.SetForegroundWindow(self.hwnd)
            except Exception:
                pass
        time.sleep(0.12)

    def is_foreground(self) -> bool:
        if not self.is_alive():
            return False
        return win32gui.GetForegroundWindow() == self.hwnd
