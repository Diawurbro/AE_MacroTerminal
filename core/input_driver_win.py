"""SendInput wrapper. Roblox ignores SetCursorPos + mouse_event in many cases,
so everything here goes through SendInput with hardware scan codes."""

import ctypes
import random
import time
from ctypes import wintypes

ULONG_PTR = ctypes.POINTER(ctypes.c_ulong)

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000

KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

SCAN = {
    "w": 0x11, "a": 0x1E, "s": 0x1F, "d": 0x20, "e": 0x12, "q": 0x10,
    "r": 0x13, "f": 0x21, "g": 0x22, "space": 0x39, "esc": 0x01,
    "enter": 0x1C, "tab": 0x0F, "shift": 0x2A, "ctrl": 0x1D,
    "1": 0x02, "2": 0x03, "3": 0x04, "4": 0x05, "5": 0x06,
    "6": 0x07, "7": 0x08, "8": 0x09, "9": 0x0A, "0": 0x0B,
    # Rest of the alphabet. Nothing in the run path sends keys to the game
    # anymore (HANDOFF 2.22) - kept so key support doesn't have to be rebuilt
    # from scratch if some future control turns out to have no clickable
    # equivalent at all.
    "b": 0x30, "c": 0x2E, "h": 0x23, "i": 0x17, "j": 0x24, "k": 0x25,
    "l": 0x26, "m": 0x32, "n": 0x31, "o": 0x18, "p": 0x19, "t": 0x14,
    "u": 0x16, "v": 0x2F, "x": 0x2D, "y": 0x15, "z": 0x2C,
}


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD),
                ("wParamH", wintypes.WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


_user32 = ctypes.windll.user32 if hasattr(ctypes, "windll") else None


def _send(*inputs: INPUT):
    n = len(inputs)
    arr = (INPUT * n)(*inputs)
    _user32.SendInput(n, ctypes.byref(arr), ctypes.sizeof(INPUT))


def _sleep_ms(ms: float):
    if ms > 0:
        time.sleep(ms / 1000.0)


class InputDriver:
    def __init__(self, cfg: dict):
        i = cfg["input"]
        self.jitter_px = i.get("jitter_px", 3)
        self.jitter_pct = i.get("jitter_delay_pct", 0.15)
        self.click_hold = i.get("click_hold_ms", 45)
        self.step_gap = i.get("step_gap_ms", 180)
        self.wiggle_px = i.get("wiggle_px", 1)
        self.wiggle_delay = i.get("wiggle_delay_ms", 30)
        self.humanize = True

    # ---------- timing ----------

    def wait(self, ms: float):
        if self.humanize:
            ms *= 1.0 + random.uniform(-self.jitter_pct, self.jitter_pct)
        _sleep_ms(ms)

    def gap(self):
        self.wait(self.step_gap)

    # ---------- mouse ----------

    def _abs_coords(self, x: int, y: int) -> tuple[int, int]:
        vx = _user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
        vy = _user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
        vw = _user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
        vh = _user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
        nx = int((x - vx) * 65535 / max(1, vw - 1))
        ny = int((y - vy) * 65535 / max(1, vh - 1))
        return nx, ny

    def move(self, x: int, y: int, jitter: bool = True):
        if jitter and self.humanize and self.jitter_px:
            x += random.randint(-self.jitter_px, self.jitter_px)
            y += random.randint(-self.jitter_px, self.jitter_px)
        nx, ny = self._abs_coords(x, y)
        inp = INPUT(type=INPUT_MOUSE, u=_INPUTUNION(mi=MOUSEINPUT(
            nx, ny, 0,
            MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK,
            0, None)))
        _send(inp)

    def _wiggle(self):
        """Nudge the cursor a pixel and back, immediately before pressing.

        Roblox updates what's under the cursor from mouse-MOVE events; a
        press that arrives with no movement since the last one can land
        against a stale hover state and do nothing. Moving onto the target
        and pressing straight away is exactly that case, so every click pays
        for one tiny move first. Lifted from the Cys macro, which wiggles
        before literally every click for the same reason. Set input.wiggle_px
        to 0 to disable.

        Sent RELATIVE (MOUSEEVENTF_MOVE without _ABSOLUTE), so it needs no
        knowledge of where the cursor currently is and lands back exactly
        where it started."""
        if not self.wiggle_px:
            return
        d = self.wiggle_px
        _send(INPUT(type=INPUT_MOUSE, u=_INPUTUNION(
            mi=MOUSEINPUT(d, d, 0, MOUSEEVENTF_MOVE, 0, None))))
        _sleep_ms(self.wiggle_delay)
        _send(INPUT(type=INPUT_MOUSE, u=_INPUTUNION(
            mi=MOUSEINPUT(-d, -d, 0, MOUSEEVENTF_MOVE, 0, None))))

    def click(self, x: int = None, y: int = None, button: str = "left"):
        if x is not None:
            self.move(x, y)
            self.wait(35)
        self._wiggle()
        down = MOUSEEVENTF_LEFTDOWN if button == "left" else MOUSEEVENTF_RIGHTDOWN
        up = MOUSEEVENTF_LEFTUP if button == "left" else MOUSEEVENTF_RIGHTUP
        _send(INPUT(type=INPUT_MOUSE, u=_INPUTUNION(mi=MOUSEINPUT(0, 0, 0, down, 0, None))))
        self.wait(self.click_hold)
        _send(INPUT(type=INPUT_MOUSE, u=_INPUTUNION(mi=MOUSEINPUT(0, 0, 0, up, 0, None))))

    def scroll(self, ticks: int, step_delay_ms: int = 25):
        """Positive ticks = zoom in / wheel forward."""
        for _ in range(abs(ticks)):
            delta = 120 if ticks > 0 else -120
            _send(INPUT(type=INPUT_MOUSE, u=_INPUTUNION(
                mi=MOUSEINPUT(0, 0, delta & 0xFFFFFFFF, MOUSEEVENTF_WHEEL, 0, None))))
            _sleep_ms(step_delay_ms)

    def right_drag(self, from_xy: tuple[int, int], dy: int,
                   step_px: int = 12, step_delay_ms: int = 8):
        """Hold RMB and drag vertically in small steps.
        One big jump gets dropped by the Roblox camera controller."""
        x, y = from_xy
        self.move(x, y, jitter=False)
        self.wait(50)
        _send(INPUT(type=INPUT_MOUSE, u=_INPUTUNION(
            mi=MOUSEINPUT(0, 0, 0, MOUSEEVENTF_RIGHTDOWN, 0, None))))
        self.wait(60)

        sign = 1 if dy > 0 else -1
        remaining = abs(dy)
        cy = y
        while remaining > 0:
            step = min(step_px, remaining)
            cy += sign * step
            self.move(x, cy, jitter=False)
            _sleep_ms(step_delay_ms)
            remaining -= step

        self.wait(60)
        _send(INPUT(type=INPUT_MOUSE, u=_INPUTUNION(
            mi=MOUSEINPUT(0, 0, 0, MOUSEEVENTF_RIGHTUP, 0, None))))

    def look_drag(self, from_xy: tuple[int, int], dy: int,
                  step_px: int = 12, step_delay_ms: int = 8):
        """Same stepped-move technique as right_drag, but no button held -
        with Shift Lock engaged, Roblox rotates the camera from raw mouse
        movement alone. Only valid while Shift Lock is on."""
        x, y = from_xy
        self.move(x, y, jitter=False)
        self.wait(50)

        sign = 1 if dy > 0 else -1
        remaining = abs(dy)
        cy = y
        while remaining > 0:
            step = min(step_px, remaining)
            cy += sign * step
            self.move(x, cy, jitter=False)
            _sleep_ms(step_delay_ms)
            remaining -= step

    # ---------- keyboard ----------

    def key_down(self, key: str):
        sc = SCAN.get(key.lower())
        if sc is None:
            raise KeyError(f"unknown key: {key}")
        _send(INPUT(type=INPUT_KEYBOARD, u=_INPUTUNION(
            ki=KEYBDINPUT(0, sc, KEYEVENTF_SCANCODE, 0, None))))

    def key_up(self, key: str):
        sc = SCAN.get(key.lower())
        if sc is None:
            raise KeyError(f"unknown key: {key}")
        _send(INPUT(type=INPUT_KEYBOARD, u=_INPUTUNION(
            ki=KEYBDINPUT(0, sc, KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP, 0, None))))

    def tap(self, key: str, hold_ms: int = 45):
        self.key_down(key)
        self.wait(hold_ms)
        self.key_up(key)

    def hold(self, key: str, ms: int):
        self.key_down(key)
        _sleep_ms(ms)
        self.key_up(key)
