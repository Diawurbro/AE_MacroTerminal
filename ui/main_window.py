"""Dashboard: an L-shaped dock around the 1280x720 Roblox window (the game is
pinned top-left, freeing the column to its right and the strip beneath it).

- Right control column (COL_W wide): Setup & Run on top, then a row of
  [Readiness | Statistics + Webhooks].
- Bottom log strip (game width): the run log, in its own window under the game.

main.py positions all three (game top-left, column right, log bottom). The log
is a separate top-level window because an L-shape isn't a rectangle - one window
can't cover both docks without also covering the game. MainWindow owns it so
main.py still reaches everything through `self.window` (`.log`, `.log_window`).
"""

from PySide6.QtCore import Qt
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

# Kept for import compatibility; the bottom-bar height is no longer used to
# reserve screen space (the game is pinned top-left now, not centered above a
# bar). main.py positions everything from the constants above.
BAR_H = 0


class LogWindow(QWidget):
    """The bottom log strip - its own frameless-feeling top-level window so it
    can sit directly under the game window, in the space the L-dock leaves."""

    def __init__(self, log: LogPanel):
        super().__init__()
        self.setWindowTitle("TD Macro - Log")
        self.setObjectName("logRoot")
        # Frameless to match the mock - the dock is auto-positioned under the
        # game, so an OS title bar would only add chrome the design doesn't have.
        # It closes with MainWindow (which owns it), so it needs no close button.
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setStyleSheet(DASHBOARD_QSS)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(log)


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TD Macro")
        self.setObjectName("dashRoot")
        # Frameless to match the mock. The column is auto-docked to the right of
        # the game; its own Exit button (and Alt+F4 / taskbar) closes the app,
        # so it needs no title bar. closeEvent takes the log strip down with it.
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setStyleSheet(DASHBOARD_QSS)
        # App-wide: the mouse wheel must never change a spin box / combo value.
        install_no_wheel_filter()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(GAP)

        # Setup & Run spans the top of the column.
        self.setup_run = SetupRunPanel()
        root.addWidget(self.setup_run)

        # Below it: Readiness on the left, Statistics + Webhooks stacked right.
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
        root.addLayout(row, 1)

        # The log strip is a separate window; MainWindow builds and owns it so
        # positioning/show/close stay centralized (main.py uses both).
        self.log = LogPanel()
        self.log_window = LogWindow(self.log)

    def closeEvent(self, ev):
        # Closing the control column closes the whole dashboard - take the log
        # strip with it, or it lingers as an orphan window keeping the app alive.
        self.log_window.close()
        super().closeEvent(ev)
