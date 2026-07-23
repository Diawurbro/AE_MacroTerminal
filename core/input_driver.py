"""Dispatches to the platform-specific InputDriver backend. See
core/input_driver_win.py / core/input_driver_mac.py for the actual
implementations."""

import sys

if sys.platform == "win32":
    from core.input_driver_win import InputDriver
elif sys.platform == "darwin":
    from core.input_driver_mac import InputDriver
else:
    raise RuntimeError(f"Unsupported platform: {sys.platform}")

__all__ = ["InputDriver"]
