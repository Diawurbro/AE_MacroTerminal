"""Quartz CGEventPost wrapper - the mac counterpart to
core/input_driver_win.py's Win32 SendInput implementation. Confirmed working
against the real Roblox mac client via
tools/mac_smoketest/1_input_accept_test.py (cursor move + click + key tap
all registered) before this file was written.

Same public interface as the Windows driver (move/click/scroll/right_drag/
look_drag/key_down/key_up/tap/hold/wait/gap), so core/hotbar.py,
core/camera.py etc. don't need to know which platform they're on.
"""

import random
import time

from core.platform_keys_mac import VK

from Quartz import (
    CGEventCreate, CGEventGetLocation,
    CGEventCreateMouseEvent, CGEventCreateKeyboardEvent,
    CGEventCreateScrollWheelEvent, CGEventPost, CGEventSetIntegerValueField,
    kCGHIDEventTap, kCGScrollEventUnitLine,
    kCGEventMouseMoved,
    kCGEventLeftMouseDown, kCGEventLeftMouseUp, kCGEventLeftMouseDragged,
    kCGEventRightMouseDown, kCGEventRightMouseUp, kCGEventRightMouseDragged,
    kCGMouseButtonLeft, kCGMouseButtonRight,
    kCGMouseEventDeltaX, kCGMouseEventDeltaY,
)


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
        self.humanize = True
        self._pos = self._current_pos()

    def _current_pos(self) -> tuple[float, float]:
        loc = CGEventGetLocation(CGEventCreate(None))
        return (loc.x, loc.y)

    # ---------- timing ----------

    def wait(self, ms: float):
        if self.humanize:
            ms *= 1.0 + random.uniform(-self.jitter_pct, self.jitter_pct)
        _sleep_ms(ms)

    def gap(self):
        self.wait(self.step_gap)

    # ---------- mouse ----------

    def _post_mouse(self, event_type, point, button=kCGMouseButtonLeft):
        ev = CGEventCreateMouseEvent(None, event_type, point, button)
        CGEventPost(kCGHIDEventTap, ev)
        self._pos = point

    def move(self, x: int, y: int, jitter: bool = True):
        if jitter and self.humanize and self.jitter_px:
            x += random.randint(-self.jitter_px, self.jitter_px)
            y += random.randint(-self.jitter_px, self.jitter_px)
        self._post_mouse(kCGEventMouseMoved, (x, y))

    def click(self, x: int = None, y: int = None, button: str = "left"):
        if x is not None:
            self.move(x, y)
            self.wait(35)
        cg_button = kCGMouseButtonLeft if button == "left" else kCGMouseButtonRight
        down = kCGEventLeftMouseDown if button == "left" else kCGEventRightMouseDown
        up = kCGEventLeftMouseUp if button == "left" else kCGEventRightMouseUp
        self._post_mouse(down, self._pos, cg_button)
        self.wait(self.click_hold)
        self._post_mouse(up, self._pos, cg_button)

    def scroll(self, ticks: int, step_delay_ms: int = 25):
        """Positive ticks = zoom in / wheel forward."""
        for _ in range(abs(ticks)):
            delta = 1 if ticks > 0 else -1
            ev = CGEventCreateScrollWheelEvent(None, kCGScrollEventUnitLine, 1, delta)
            CGEventPost(kCGHIDEventTap, ev)
            _sleep_ms(step_delay_ms)

    def right_drag(self, from_xy: tuple[int, int], dy: int,
                   step_px: int = 12, step_delay_ms: int = 8):
        """Hold RMB and drag vertically in small steps.
        One big jump gets dropped by the Roblox camera controller."""
        x, y = from_xy
        self.move(x, y, jitter=False)
        self.wait(50)
        self._post_mouse(kCGEventRightMouseDown, self._pos, kCGMouseButtonRight)
        self.wait(60)

        sign = 1 if dy > 0 else -1
        remaining = abs(dy)
        cy = y
        while remaining > 0:
            step = min(step_px, remaining)
            cy += sign * step
            # Set the delta fields explicitly - Roblox's camera-look reads
            # raw HID-style delta, not just the event's absolute position
            # (a plain position-only drag zoomed fine but didn't rotate).
            ev = CGEventCreateMouseEvent(
                None, kCGEventRightMouseDragged, (x, cy), kCGMouseButtonRight)
            CGEventSetIntegerValueField(ev, kCGMouseEventDeltaX, 0)
            CGEventSetIntegerValueField(ev, kCGMouseEventDeltaY, sign * step)
            CGEventPost(kCGHIDEventTap, ev)
            self._pos = (x, cy)
            _sleep_ms(step_delay_ms)
            remaining -= step

        self.wait(60)
        self._post_mouse(kCGEventRightMouseUp, self._pos, kCGMouseButtonRight)

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
        vk = VK.get(key.lower())
        if vk is None:
            raise KeyError(f"unknown key: {key}")
        ev = CGEventCreateKeyboardEvent(None, vk, True)
        CGEventPost(kCGHIDEventTap, ev)

    def key_up(self, key: str):
        vk = VK.get(key.lower())
        if vk is None:
            raise KeyError(f"unknown key: {key}")
        ev = CGEventCreateKeyboardEvent(None, vk, False)
        CGEventPost(kCGHIDEventTap, ev)

    def tap(self, key: str, hold_ms: int = 45):
        self.key_down(key)
        self.wait(hold_ms)
        self.key_up(key)

    def hold(self, key: str, ms: int):
        self.key_down(key)
        _sleep_ms(ms)
        self.key_up(key)
