"""Dashboard window: a short, full-width bar docked to the BOTTOM edge of the
screen (Setup & Run, Readiness, Statistics, Webhooks, Current Process laid out
side by side). main.py sizes it to the screen width and positions the Roblox
window in the space ABOVE it, so the two never overlap. This replaces the old
tall left-docked column, which ran off the bottom of the screen. The stage
editor (canvas + Index grid) is its own separate window, opened on demand from
the 'Stage editor' button.
"""

from PySide6.QtWidgets import QWidget, QHBoxLayout

from ui.panels import (
    DASHBOARD_QSS, LogPanel, ReadinessPanel, SetupRunPanel, StatsPanel,
    WebhookPanel, install_no_wheel_filter,
)

# Height of the bottom bar (px). The Roblox window is centered in the screen
# area above this, so keep it small enough to leave room for a 720px client.
BAR_H = 250


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TD Macro")
        self.setFixedHeight(BAR_H)
        # dashRoot draws the accent hairline along the top edge (see the QSS);
        # the 6px top margin keeps the panels off it.
        self.setObjectName("dashRoot")
        self.setStyleSheet(DASHBOARD_QSS)
        # App-wide: the mouse wheel must never change a spin box / combo value.
        install_no_wheel_filter()

        root = QHBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 6)
        root.setSpacing(7)

        # Left to right across the bar, in the order the workflow uses them.
        # Everything is width-capped to its content except the log, which
        # stretches to fill whatever is left - on a 1920px screen that is most
        # of the bar, which is what makes long log lines readable.
        self.setup_run = SetupRunPanel()
        self.setup_run.setMinimumWidth(340)
        self.setup_run.setMaximumWidth(420)
        root.addWidget(self.setup_run)

        self.readiness = ReadinessPanel()
        self.readiness.setFixedWidth(248)
        root.addWidget(self.readiness)

        self.stats = StatsPanel()
        self.stats.setFixedWidth(196)
        root.addWidget(self.stats)

        self.webhook = WebhookPanel()
        self.webhook.setFixedWidth(210)
        root.addWidget(self.webhook)

        self.log = LogPanel()
        self.log.setMinimumWidth(260)
        root.addWidget(self.log, 1)
