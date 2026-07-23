"""Dispatches to the platform-specific GlobalHotkeys backend. See
core/hotkeys_win.py / core/hotkeys_mac.py for the actual implementations."""

import sys

if sys.platform == "win32":
    from core.hotkeys_win import GlobalHotkeys
elif sys.platform == "darwin":
    from core.hotkeys_mac import GlobalHotkeys
else:
    raise RuntimeError(f"Unsupported platform: {sys.platform}")

__all__ = ["GlobalHotkeys"]
