"""Dashboard: ONE full-screen frameless window shaped around the Roblox window.

The game is pinned top-left; this window covers the whole screen with a
click-through MASK cutting a hole exactly where the game is, so the right
control column and the bottom log strip read as a single surface wrapping the
game (rather than two separate windows). The hole is unpainted and click-through:
real and synthetic clicks reach Roblox, and mss captures the true game pixels for
the executor.

main.py drives placement via place(game, screen) - called at startup (expected
game rect), on attach, and from the window watchdog when the game is moved.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QRegion
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout

from ui.panels import (
    DASHBOARD_QSS, LogPanel, ReadinessPanel, SetupRunPanel, StatsPanel,
    WebhookPanel, install_no_wheel_filter,
)

# Layout geometry (px), matching the design mock on a 1920x1080 screen.
MARGIN = 24        # gap from the screen edges
GAP = 16           # gap between the game window and the docks, and between cards
COL_W = 576        # right control-column width
GAME_W = 1280      # forced Roblox client width (see core/window.py)
GAME_H = 720

# Retired (the bottom bar is gone); kept = 0 so any stale import still resolves.
BAR_H = 0


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TD Macro")
        self.setObjectName("dashRoot")
        # Frameless full-screen surface. Its own Exit button (and Alt+F4) closes
        # the app; the mask (set in place()) is what carves out the game hole.
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setStyleSheet(DASHBOARD_QSS)
        # App-wide: the mouse wheel must never change a spin box / combo value.
        install_no_wheel_filter()

        # Control column (right of the game). A transparent host so the window
        # ground (#dashRoot) shows around the cards, not the generic widget bg.
        self._column_host = QWidget(self)
        self._column_host.setObjectName("colHost")
        col = QVBoxLayout(self._column_host)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(GAP)
        self.setup_run = SetupRunPanel()
        col.addWidget(self.setup_run)

        row = QHBoxLayout()
        row.setSpacing(GAP)
        self.readiness = ReadinessPanel()
        row.addWidget(self.readiness, 1)
        right = QVBoxLayout()
        right.setSpacing(GAP)
        self.stats = StatsPanel()
        right.addWidget(self.stats)
        self.webhook = WebhookPanel()
        right.addWidget(self.webhook)
        right.addStretch(1)
        row.addLayout(right, 1)
        col.addLayout(row, 1)

        # Log strip (below the game), same transparent-host treatment.
        self._log_host = QWidget(self)
        self._log_host.setObjectName("logHost")
        logl = QVBoxLayout(self._log_host)
        logl.setContentsMargins(0, 0, 0, 0)
        self.log = LogPanel()
        logl.addWidget(self.log)

    def place(self, game, screen):
        """Fill `screen` (a QRect), cut a click-through hole at `game`
        (x, y, w, h in screen px), and dock the control column to the right of
        the game and the log strip beneath it.

        All child/mask coordinates are window-relative (the window's top-left is
        the screen's top-left)."""
        self.setGeometry(screen)
        sw, sh = screen.width(), screen.height()
        # Game rect in window-relative coordinates.
        rx, ry = game[0] - screen.x(), game[1] - screen.y()
        gw, gh = game[2], game[3]

        col_x = rx + gw + GAP
        col_w = min(COL_W, max(320, sw - MARGIN - col_x))
        self._column_host.setGeometry(col_x, MARGIN, col_w, sh - 2 * MARGIN)

        log_y = ry + gh + GAP
        log_h = max(120, sh - MARGIN - log_y)
        self._log_host.setGeometry(rx, log_y, gw, log_h)

        # The hole: unpainted + click-through, so Roblox shows through it and
        # receives clicks, and mss reads the real game pixels beneath.
        self.setMask(QRegion(0, 0, sw, sh).subtracted(QRegion(rx, ry, gw, gh)))
