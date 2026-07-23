"""Global hotkeys (F9 start, F12 emergency stop) via a Quartz event tap - the
mac counterpart to core/hotkeys_win.py's RegisterHotKey/message-loop
implementation. Same "own thread, own event loop" shape: Qt's event loop
doesn't see these either, and Roblox holds OS focus while the macro runs, so
the tap has to run independently.

Needs Accessibility permission (System Settings > Privacy & Security >
Accessibility) for whatever process runs this - CGEventTapCreate returns
None without it, handled below as a graceful degrade (logged, not fatal),
same as the Windows file's handling of an already-bound hotkey.

Unlike input_driver_mac.py / window_mac.py, this file has not been separately
smoke-tested yet - verify F9/F12 actually fire while running the real app
before relying on it.
"""

import threading
import time

from core.platform_keys_mac import FUNCTION_VK

try:
    from Quartz import (
        CGEventTapCreate, CGEventTapEnable, CGEventMaskBit,
        kCGSessionEventTap, kCGHeadInsertEventTap, kCGEventTapOptionListenOnly,
        kCGEventKeyDown, CGEventGetIntegerValueField, kCGKeyboardEventKeycode,
    )
    from CoreFoundation import (
        CFMachPortCreateRunLoopSource, CFRunLoopAddSource, CFRunLoopGetCurrent,
        CFRunLoopRun, CFRunLoopStop, kCFRunLoopCommonModes,
    )
    HAS_MAC_APIS = True
except ImportError:
    HAS_MAC_APIS = False


class GlobalHotkeys:
    def __init__(self, log=lambda m: None):
        self._callbacks: dict[int, object] = {}
        self._thread = None
        self._runloop = None
        self._tap = None
        self._log = log

    def register(self, key: str, callback):
        vk = FUNCTION_VK.get(key.lower())
        if vk is None:
            raise KeyError(f"unsupported hotkey: {key}")
        self._callbacks[vk] = callback

    def start(self):
        if not HAS_MAC_APIS or self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        for _ in range(50):
            if self._runloop is not None:
                break
            time.sleep(0.02)

    def _tap_callback(self, proxy, event_type, event, refcon):
        keycode = CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode)
        cb = self._callbacks.get(keycode)
        if cb:
            try:
                cb()
            except Exception:
                pass
        return event

    def _run(self):
        try:
            mask = CGEventMaskBit(kCGEventKeyDown)
            self._tap = CGEventTapCreate(
                kCGSessionEventTap, kCGHeadInsertEventTap,
                kCGEventTapOptionListenOnly, mask, self._tap_callback, None)
            if self._tap is None:
                self._log(
                    "Global hotkeys need Accessibility permission: enable "
                    "this app (or your terminal/python3) in System Settings "
                    "> Privacy & Security > Accessibility, then restart.")
                return
            source = CFMachPortCreateRunLoopSource(None, self._tap, 0)
            self._runloop = CFRunLoopGetCurrent()
            CFRunLoopAddSource(self._runloop, source, kCFRunLoopCommonModes)
            CGEventTapEnable(self._tap, True)
            CFRunLoopRun()
        except Exception as e:
            self._log(f"Hotkey listener stopped unexpectedly: {e}")

    def stop(self):
        if self._tap is not None:
            try:
                CGEventTapEnable(self._tap, False)
            except Exception:
                pass
        if self._runloop is not None:
            try:
                CFRunLoopStop(self._runloop)
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=1.5)
        self._thread = None
        self._runloop = None
        self._tap = None
