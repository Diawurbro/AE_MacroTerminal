"""Dispatches to the platform-specific RobloxWindow backend. See
core/window_win.py / core/window_mac.py for the actual implementations -
every other module imports RobloxWindow/enable_dpi_awareness/ClientRect from
here and stays unaware of which platform it's actually running on."""

import sys

from core.client_rect import ClientRect

if sys.platform == "win32":
    from core.window_win import RobloxWindow, enable_dpi_awareness
elif sys.platform == "darwin":
    from core.window_mac import RobloxWindow, enable_dpi_awareness
else:
    raise RuntimeError(f"Unsupported platform: {sys.platform}")

__all__ = ["RobloxWindow", "enable_dpi_awareness", "ClientRect"]
