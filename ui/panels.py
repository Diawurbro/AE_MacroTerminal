"""Dashboard widgets for the bottom bar (Setup & Run, Readiness, Statistics,
Webhooks, Current Process) plus DASHBOARD_QSS - the one dark theme shared with
the stage editor so both windows read as a single system.

Everything here has to stay legible inside a BAR_H-tall strip, so the visual
rules are deliberately tight: dark page, slightly lighter panel "cards", darker
"wells" for anything that scrolls, 11px UI text, and magenta used for accents
and state (focus, active tab, progress) instead of outlining every panel - an
accent on everything reads as noise and leaves nothing to draw the eye.
"""

import html
import time

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QPlainTextEdit, QSpinBox, QLineEdit, QGroupBox, QGridLayout, QCheckBox,
    QScrollArea, QFrame, QProgressBar, QSizePolicy, QComboBox,
    QAbstractSpinBox, QAbstractScrollArea, QApplication,
)

# --- palette -----------------------------------------------------------
# One place to retune the theme. Names describe the role, not the colour, so
# swapping the hue later doesn't leave lying variable names behind.
ACCENT = "#FF2FB0"          # magenta: focus, active tab, progress, hover edge
ACCENT_SOFT = "#FF8BD3"     # readable magenta for text (panel titles)
ACCENT_DEEP = "#4A1035"     # magenta at text-background strength (selection)

BG = "#101014"              # page / bar background
SURFACE = "#191920"         # panel card
RAISED = "#23232C"          # buttons
SUNKEN = "#0B0B0F"          # inputs, log, scrolling wells
BORDER = "#2B2B35"
BORDER_HI = "#3C3C49"

TEXT = "#E9E9F0"
DIM = "#9C9CAA"             # secondary text
FAINT = "#6C6C7A"           # tertiary text (timestamps, captions)

OK = "#3FCF8E"
WARN = "#E8B23F"
BAD = "#F06565"
OK_BG, WARN_BG, BAD_BG = "#122520", "#2A2416", "#2A1619"

DASHBOARD_QSS = f"""
QWidget {{ background: {BG}; color: {TEXT}; }}

/* The bar sits flush on the screen edge; the accent hairline is what makes it
   read as a docked tool strip rather than a window that lost its frame. */
QWidget#dashRoot {{ border-top: 2px solid {ACCENT}; }}

QLabel {{ background: transparent; color: {TEXT}; font-size: 11px; }}
QLabel#appTitle {{ color: #ffffff; font-size: 15px; font-weight: 700; }}
QLabel#value {{ color: #ffffff; font-size: 14px; font-weight: 600; }}
QLabel#muted {{ color: {DIM}; font-size: 11px; }}
QLabel#caption {{ color: {FAINT}; font-size: 10px; }}
QLabel#colHead {{ color: {FAINT}; font-size: 10px; font-weight: 600; }}
QLabel#metric {{ color: {TEXT}; font-size: 12px; font-weight: 600; }}
QLabel#metricAccent {{ color: {ACCENT_SOFT}; font-size: 12px; font-weight: 600; }}
QLabel#sectionHead {{ color: {ACCENT_SOFT}; font-size: 11px; font-weight: 600; }}
QLabel#checkRow {{ padding: 2px 1px 3px 1px; border-bottom: 1px solid #1E1E26; }}

/* Pills carry run state / readiness at a glance. Level is a dynamic property,
   so set it then re-polish the widget (see _repolish). */
QLabel#statePill {{
    background: {RAISED}; color: {DIM}; border: 1px solid {BORDER};
    border-radius: 4px; padding: 2px 8px; font-size: 12px; font-weight: 700;
}}
QLabel#statePill[level="run"] {{ background: {OK}; color: #08150F; border-color: {OK}; }}
QLabel#statePill[level="bad"] {{ background: {BAD}; color: #21080A; border-color: {BAD}; }}
QLabel#summary {{ border: 1px solid {BORDER}; border-radius: 4px;
    padding: 3px 6px; font-size: 11px; color: {DIM}; }}
QLabel#summary[level="ok"] {{ color: {OK}; background: {OK_BG}; border-color: #1E4736; }}
QLabel#summary[level="warn"] {{ color: {WARN}; background: {WARN_BG}; border-color: #4A3D18; }}
QLabel#summary[level="bad"] {{ color: {BAD}; background: {BAD_BG}; border-color: #4C2226; }}

QFrame#sep {{ background: {BORDER}; border: none; }}
/* One calibration anchor (stage editor): name + Set button, value underneath.
   The rule is here so the whole theme stays in one file. */
QWidget#anchorRow {{ border-bottom: 1px solid #23232C; }}

QGroupBox {{
    background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 7px;
    margin-top: 12px; padding-top: 4px;
    color: {ACCENT_SOFT}; font-size: 11px; font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin; subcontrol-position: top left;
    left: 9px; padding: 0 4px; background: transparent;
}}

QPushButton {{
    background: {RAISED}; color: {TEXT}; border: 1px solid {BORDER_HI};
    border-radius: 5px; padding: 4px 9px; font-size: 11px; text-align: center;
}}
QPushButton:hover {{ background: #2C2C37; border-color: {ACCENT}; }}
QPushButton:pressed {{ background: #17171D; }}
QPushButton:disabled {{ background: #17171C; color: #55555F; border-color: #262630; }}
QPushButton#primary {{
    background: #1B7A5A; color: #EAFFF6; border-color: #2AA57C; font-weight: 600;
}}
QPushButton#primary:hover {{ background: #229269; border-color: #3FD09C; }}
QPushButton#primary:pressed {{ background: #145C44; }}
QPushButton#primary:disabled {{ background: #17322A; color: #5F8D7B; border-color: #23483C; }}
QPushButton#danger {{ background: #2A171B; color: #F2A0A0; border-color: #8E3A3A; }}
QPushButton#danger:hover {{ background: #432026; border-color: {BAD}; }}
QPushButton#danger:disabled {{ background: #1A1418; color: #6B4A4E; border-color: #3A2429; }}
QPushButton#ghost {{
    background: transparent; color: {DIM}; border: 1px solid {BORDER};
    padding: 3px 7px; font-size: 10px;
}}
QPushButton#ghost:hover {{ color: {TEXT}; border-color: {BORDER_HI}; background: {RAISED}; }}

QLineEdit, QSpinBox, QComboBox {{
    background: {SUNKEN}; color: {TEXT}; border: 1px solid {BORDER};
    border-radius: 4px; padding: 4px 5px; font-size: 11px;
    selection-background-color: {ACCENT_DEEP}; selection-color: #ffffff;
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{ border-color: {ACCENT}; }}
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {{
    background: #131318; color: #55555F; border-color: #232330;
}}
/* The spin box up/down buttons are deliberately NOT styled: wheel-changing a
   value is filtered out (_NoWheelFilter), so those buttons are the only mouse
   way left to nudge a number, and any ::up-button rule here makes Qt drop the
   native arrow glyph unless an ::up-arrow image is supplied (a CSS-triangle
   ::up-arrow renders as a solid block, verified). Native arrows it is. */

QComboBox QAbstractItemView {{
    background: #1B1B22; color: {TEXT}; border: 1px solid {BORDER_HI};
    selection-background-color: {ACCENT_DEEP}; selection-color: #ffffff;
    outline: none;
}}

QTextEdit, QPlainTextEdit {{
    background: {SUNKEN}; color: #C8C8D2; border: 1px solid {BORDER};
    border-radius: 5px; font-family: Consolas, "Cascadia Mono", monospace;
    font-size: 11px; selection-background-color: {ACCENT_DEEP};
}}

QProgressBar {{
    background: {SUNKEN}; border: 1px solid {BORDER}; border-radius: 3px;
    text-align: center; color: transparent;
}}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 2px; }}

QTabWidget::pane {{
    border: 1px solid {BORDER}; border-radius: 6px; background: {SURFACE}; top: -1px;
}}
QTabBar::tab {{
    background: transparent; color: {DIM}; padding: 6px 13px;
    border-bottom: 2px solid transparent; margin-right: 2px; font-size: 11px;
}}
QTabBar::tab:hover {{ color: {TEXT}; }}
QTabBar::tab:selected {{
    color: #ffffff; background: {SURFACE}; border-bottom: 2px solid {ACCENT};
}}

QSplitter::handle {{ background: {BORDER}; }}
QSplitter::handle:hover {{ background: {ACCENT}; }}
QSplitter::handle:horizontal {{ width: 5px; }}
QSplitter::handle:vertical {{ height: 5px; }}

QTableWidget {{
    background: {SUNKEN}; alternate-background-color: #121218; color: {TEXT};
    gridline-color: #23232C; border: 1px solid {BORDER}; border-radius: 5px;
    font-size: 11px;
    /* Dimmer than the text-selection magenta: rows carry their own per-action
       foreground colour, which an item view keeps even when selected. */
    selection-background-color: #2E1424;
}}
QHeaderView::section {{
    background: #1C1C24; color: {DIM}; border: none;
    border-right: 1px solid #23232C; border-bottom: 1px solid #23232C;
    padding: 4px 6px; font-size: 10px; font-weight: 600;
}}

QScrollArea {{ border: none; }}
QScrollBar:vertical {{ background: transparent; width: 9px; margin: 0; }}
QScrollBar::handle:vertical {{ background: #32323E; border-radius: 4px; min-height: 22px; }}
QScrollBar::handle:vertical:hover {{ background: #45454F; }}
QScrollBar:horizontal {{ background: transparent; height: 9px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: #32323E; border-radius: 4px; min-width: 22px; }}
QScrollBar::handle:horizontal:hover {{ background: #45454F; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QCheckBox {{ color: {TEXT}; font-size: 11px; background: transparent; spacing: 6px; }}
QCheckBox::indicator {{
    width: 14px; height: 14px; border: 1px solid {BORDER_HI};
    border-radius: 3px; background: {SUNKEN};
}}
QCheckBox::indicator:hover {{ border-color: {ACCENT}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}

QToolTip {{
    background: #1B1B22; color: {TEXT}; border: 1px solid {BORDER_HI};
    padding: 4px 6px;
}}
QMessageBox {{ background: {SURFACE}; }}
QMessageBox QLabel {{ color: {TEXT}; font-size: 12px; }}
"""


class _NoWheelFilter(QObject):
    """Qt lets the mouse wheel change a spin box / combo box value whenever the
    pointer is merely over it. Here that silently rewrites a step's unit, its
    targeting priority or an upgrade count - and since several of these live inside
    scroll areas (readiness list, calibrate tab, index cards), scrolling the
    *panel* mutated whatever control happened to pass under the cursor. Swallow
    the wheel and hand it to the nearest scroll area instead, so the panel still
    scrolls and the value never moves. Typing and the arrow keys are untouched."""

    def eventFilter(self, obj, ev):
        if ev.type() != QEvent.Wheel or not isinstance(obj, (QAbstractSpinBox, QComboBox)):
            return False
        parent = obj.parentWidget()
        while parent is not None:
            if isinstance(parent, QAbstractScrollArea):
                QApplication.sendEvent(parent.viewport(), ev)
                break
            parent = parent.parentWidget()
        return True


_wheel_filter = None


def install_no_wheel_filter():
    """Install _NoWheelFilter on the application once. Both top-level windows
    call this, so it has to be idempotent - and it must be app-wide, since the
    editor builds spin boxes long after startup (index cards are recreated on
    every grid rebuild)."""
    global _wheel_filter
    app = QApplication.instance()
    if app is None:
        return
    try:
        if _wheel_filter is not None and _wheel_filter.parent() is app:
            return
    except RuntimeError:
        pass   # a previous QApplication (and its filter) has been torn down
    _wheel_filter = _NoWheelFilter(app)
    app.installEventFilter(_wheel_filter)


def _repolish(w: QWidget):
    """Dynamic-property selectors (e.g. [level="bad"]) only take effect after
    the style re-evaluates the widget."""
    w.style().unpolish(w)
    w.style().polish(w)


def hsep() -> QFrame:
    f = QFrame()
    f.setObjectName("sep")
    f.setFixedHeight(1)
    return f


def _dot(color: str) -> str:
    return f"<span style='color:{color}'>&#9679;</span>"


class LogPanel(QGroupBox):
    """Run log. The executor emits plain sentences with no severity prefix, so
    lines are classified by wording - colour is what makes a 200-line log
    scannable at 11px in a 250px-tall bar.

    Backed by QPlainTextEdit with a capped block count, not QTextEdit: a
    farming run emits many lines per loop and the log used to grow without
    bound, so QTextEdit re-laid-out an ever-larger document on every insert and
    the whole app got slower with each logged action. The cap makes each append
    O(1) - oldest lines are dropped once MAX_LINES is reached."""

    MAX_LINES = 600

    # Four levels, same colour language as the readiness checklist: red is
    # "this run is broken", amber is "degraded but continuing".
    _BAD = ("fail", "error", "not found", "unavailable", "abort",
            "did not register", "not installed", "not available", "cannot")
    _WARN = ("warning", "timed out", "mismatch", "missing", "not set",
             "skipping", "retry", "attempt", "result: loss", "closed",
             "not running", "limit reached")
    _OK = ("attached.", "saved", "ready.", "camera view set", "result: win",
           "pressed start game", "loaded:", "engine detected")
    _NOTE = ("--- loop", "starting", "step #", "stop requested", "normalizing",
             "teleporting", "waiting", "exiting", "reference match")

    def __init__(self):
        super().__init__("Current Process")
        v = QVBoxLayout(self)
        v.setContentsMargins(8, 4, 8, 7)
        v.setSpacing(4)

        head = QHBoxLayout()
        head.setSpacing(6)
        self.lbl_hint = QLabel("Newest at the bottom")
        self.lbl_hint.setObjectName("caption")
        head.addWidget(self.lbl_hint)
        head.addStretch(1)
        self.btn_clear = QPushButton("Clear")
        self.btn_clear.setObjectName("ghost")
        self.btn_clear.clicked.connect(self.clear_log)
        head.addWidget(self.btn_clear)
        v.addLayout(head)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        # Ring-buffer the document so a long session can't grow it without
        # bound - this is what keeps every append fast (see class docstring).
        self.log.setMaximumBlockCount(self.MAX_LINES)
        self.log.setUndoRedoEnabled(False)
        v.addWidget(self.log, 1)

    def _color_for(self, msg: str) -> str:
        low = msg.lower()
        if any(k in low for k in self._BAD):
            return BAD
        if any(k in low for k in self._WARN):
            return WARN
        if any(k in low for k in self._OK):
            return OK
        if any(k in low for k in self._NOTE):
            return ACCENT_SOFT
        return "#C8C8D2"

    def write(self, msg: str):
        color = self._color_for(msg)
        # Only follow the tail if the user is already at the bottom - yanking
        # the view while they're scrolled back reading makes the log useless.
        bar = self.log.verticalScrollBar()
        at_bottom = bar.value() >= bar.maximum() - 4

        # appendHtml adds one block and the maximumBlockCount cap drops the
        # oldest as needed - no manual cursor/trim bookkeeping.
        self.log.appendHtml(
            f"<span style='color:{FAINT}'>{time.strftime('%H:%M:%S')}</span>&nbsp;"
            f"<span style='color:{color}'>{html.escape(msg)}</span>")

        if at_bottom:
            bar.setValue(bar.maximum())

    def clear_log(self):
        self.log.clear()


class SetupRunPanel(QGroupBox):
    attach_requested = Signal()
    camera_test_requested = Signal()
    editor_requested = Signal()
    load_requested = Signal()
    screenshot_requested = Signal()
    run_requested = Signal()
    stop_requested = Signal()
    exit_requested = Signal()
    start_game_toggled = Signal(bool)
    profile_selected = Signal(str)      # user picked a name from the dropdown

    def __init__(self):
        super().__init__("Setup && Run")
        # Compact 3-column grid so the panel fits the short full-width bottom
        # bar (the old tall vertical stack ran off the bottom of the screen).
        # Reading order top to bottom: state -> setup -> options -> run.
        g = QGridLayout(self)
        g.setHorizontalSpacing(5)
        # 9 rows have to fit in BAR_H minus the group title - the spacing is
        # this tight on purpose; it leaves ~25px of headroom for a bigger UI
        # font before anything clips.
        g.setVerticalSpacing(3)
        g.setContentsMargins(8, 2, 8, 5)
        for c in range(3):
            g.setColumnStretch(c, 1)

        self.lbl_attach = QLabel()
        self.lbl_attach.setTextFormat(Qt.RichText)
        g.addWidget(self.lbl_attach, 0, 0, 1, 2)

        # Exit sits in the top corner, as far from Start/Emergency stop as the
        # panel allows - it used to have a row of its own, which the profile
        # picker now needs (the bar cannot get any taller).
        self.btn_exit = QPushButton("Exit")
        self.btn_exit.setObjectName("ghost")
        self.btn_exit.setToolTip("Quit TD Macro (stops a running macro first).")
        self.btn_exit.clicked.connect(self.exit_requested.emit)
        g.addWidget(self.btn_exit, 0, 2, Qt.AlignRight)

        prof_row = QHBoxLayout()
        prof_row.setSpacing(5)
        lbl_prof = QLabel("Profile")
        lbl_prof.setObjectName("muted")
        prof_row.addWidget(lbl_prof)
        self.cb_profile = QComboBox()
        self.cb_profile.setToolTip("Pick one of your saved stage profiles.")
        self.cb_profile.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.cb_profile.activated.connect(self._on_profile_picked)
        prof_row.addWidget(self.cb_profile, 1)
        self.lbl_profile = QLabel()
        self.lbl_profile.setTextFormat(Qt.RichText)
        prof_row.addWidget(self.lbl_profile)
        g.addLayout(prof_row, 2, 0, 1, 3)

        self.btn_attach = QPushButton("Attach + center window")
        self.btn_attach.setToolTip(
            "Find the Roblox window, resize its client area to 1280x720 and "
            "center it in the space above this bar.")
        self.btn_attach.clicked.connect(self.attach_requested.emit)
        g.addWidget(self.btn_attach, 3, 0, 1, 3)

        self.btn_camera = QPushButton("Test camera view")
        self.btn_camera.setToolTip(
            "Runs the right-drag top-down sequence against the attached Roblox "
            "window (zoom in, pitch down, zoom out - all hard clamps) so you can "
            "preview it before capturing the reference image in the stage editor.")
        self.btn_camera.clicked.connect(self.camera_test_requested.emit)
        g.addWidget(self.btn_camera, 4, 0)

        self.btn_editor = QPushButton("Stage editor")
        self.btn_editor.setToolTip("Open the stage editor window to build / edit steps.")
        self.btn_editor.clicked.connect(self.editor_requested.emit)
        g.addWidget(self.btn_editor, 4, 1)

        self.btn_load = QPushButton("Load from file")
        self.btn_load.setToolTip("Browse for a profile (.json) that isn't in the "
                                 "dropdown - e.g. one you saved elsewhere.")
        self.btn_load.clicked.connect(self.load_requested.emit)
        g.addWidget(self.btn_load, 4, 2)

        # Runs are always infinite - Stop / F12 is how one ends. The old
        # "Loops" spinbox is gone: it defaulted to infinite anyway, and a
        # farming macro that stops itself after N wins isn't a thing anyone
        # asked for twice.
        self.btn_shot = QPushButton("Screenshot")
        self.btn_shot.setToolTip("Save a PNG of the game client area.")
        self.btn_shot.clicked.connect(self.screenshot_requested.emit)
        g.addWidget(self.btn_shot, 5, 0, 1, 3)

        self.chk_start_game = QCheckBox("Press Start Game at run start")
        self.chk_start_game.setToolTip(
            "Auto-click the in-game 'Start Game' button when a run begins.")
        self.chk_start_game.toggled.connect(self.start_game_toggled.emit)
        g.addWidget(self.chk_start_game, 6, 0, 1, 3)

        g.addWidget(hsep(), 7, 0, 1, 3)

        self.btn_run = QPushButton("Start  (F9)")
        self.btn_run.setObjectName("primary")
        self.btn_run.clicked.connect(self.run_requested.emit)
        g.addWidget(self.btn_run, 8, 0, 1, 2)

        self.btn_stop = QPushButton("Stop  (F12)")
        self.btn_stop.setObjectName("danger")
        self.btn_stop.setToolTip("Emergency stop - finishes the current step, then aborts.")
        self.btn_stop.setEnabled(False)   # nothing to stop until a run starts
        self.btn_stop.clicked.connect(self.stop_requested.emit)
        g.addWidget(self.btn_stop, 8, 2)

        self._running = False
        self._cam_testing = False
        self.set_attached(False)
        self.set_profile_list([])
        self.set_profile("-", 0)

    # ---- profile picker ----

    def _on_profile_picked(self, index: int):
        # activated (not currentIndexChanged) so repopulating the list can
        # never look like a user choice and trigger a load.
        name = self.cb_profile.itemText(index)
        if self.cb_profile.isEnabled() and name:
            self.profile_selected.emit(name)

    def set_profile_list(self, names: list):
        """Populate the dropdown. main.py owns finding the profiles; this only
        shows them."""
        names = [str(n) for n in (names or [])]
        keep = self.cb_profile.currentText()
        self.cb_profile.blockSignals(True)
        self.cb_profile.clear()
        if names:
            self.cb_profile.addItems(names)
            self.cb_profile.setEnabled(True)
            if keep in names:
                self.cb_profile.setCurrentText(keep)
        else:
            self.cb_profile.addItem("no saved profiles")
            self.cb_profile.setEnabled(False)
        self.cb_profile.blockSignals(False)

    def set_current_profile(self, name: str):
        """Select a name without emitting profile_selected."""
        i = self.cb_profile.findText(str(name))
        if i < 0:
            return
        self.cb_profile.blockSignals(True)
        self.cb_profile.setCurrentIndex(i)
        self.cb_profile.blockSignals(False)

    # ---- state ----

    def _apply_enabled(self):
        """Anything that re-points the macro mid-run would desync it, so those
        controls are locked while the executor is alive."""
        busy = self._running or self._cam_testing
        self.btn_attach.setEnabled(not busy)
        self.btn_load.setEnabled(not self._running)
        self.btn_camera.setEnabled(not busy)
        self.btn_run.setEnabled(not busy)
        self.btn_stop.setEnabled(self._running)

    def set_attached(self, ok: bool, detail: str = ""):
        if ok:
            text = f"attached <span style='color:{DIM}'>{html.escape(detail)}</span>"
            self.lbl_attach.setText(f"{_dot(OK)} Roblox {text}")
        else:
            self.lbl_attach.setText(f"{_dot(BAD)} Roblox "
                                    f"<span style='color:{DIM}'>not attached</span>")

    def set_profile(self, name: str, steps: int):
        # The name itself now lives in the dropdown, so this label only carries
        # the part the dropdown can't show: whether the profile has any steps.
        color = OK if steps else WARN
        word = "step" if steps == 1 else "steps"
        self.lbl_profile.setText(
            f"{_dot(color)} <span style='color:{DIM}'>{steps} {word}</span>")
        self.lbl_profile.setToolTip(f"Profile: {name}\n{steps} step(s)")
        # Keep the dropdown in sync even if main.py only calls set_profile().
        self.set_current_profile(name)

    def set_running(self, running: bool):
        self._running = running
        self.btn_run.setText("Running..." if running else "Start  (F9)")
        self._apply_enabled()

    def set_camera_testing(self, testing: bool):
        self._cam_testing = testing
        self.btn_camera.setText("Testing camera..." if testing else "Test camera view")
        self._apply_enabled()

    def set_press_start_game(self, on: bool):
        self.chk_start_game.setChecked(on)


class ReadinessPanel(QGroupBox):
    """Plain-English green/yellow/red checklist of everything a real run
    needs, so Start tells you what's missing instead of silently timing out.
    App.refresh_readiness() computes the checks and calls set_checks()."""
    recheck_requested = Signal()
    guide_requested = Signal()

    DOT = {"ok": OK, "warn": WARN, "bad": BAD}

    def __init__(self):
        super().__init__("Readiness")
        self._v = QVBoxLayout(self)
        self._v.setSpacing(4)
        self._v.setContentsMargins(8, 3, 8, 7)

        self.summary = QLabel("Checking...")
        self.summary.setObjectName("summary")
        self.summary.setWordWrap(True)
        self._v.addWidget(self.summary)

        # The checklist can be taller than the bottom bar, so it scrolls inside
        # a fixed area instead of stretching the whole window.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)
        rows_container = QWidget()
        rows_container.setObjectName("checkWell")
        self._rows_host = QVBoxLayout(rows_container)
        self._rows_host.setSpacing(0)
        self._rows_host.setContentsMargins(2, 0, 2, 0)
        self._rows_host.setAlignment(Qt.AlignTop)
        scroll.setWidget(rows_container)
        self._v.addWidget(scroll, 1)
        self._row_labels = []

        row = QHBoxLayout()
        row.setSpacing(5)
        btn = QPushButton("Re-check")
        btn.setToolTip("Re-run every readiness check now.")
        btn.clicked.connect(self.recheck_requested.emit)
        row.addWidget(btn)
        guide = QPushButton("Guide")
        guide.setToolTip("Step-by-step first-time setup.")
        guide.clicked.connect(self.guide_requested.emit)
        row.addWidget(guide)
        self._v.addLayout(row)

    LEVEL_ORDER = {"bad": 0, "warn": 1, "ok": 2}

    def set_checks(self, checks: list):
        """checks: list of (label, level, detail). level in ok|warn|bad."""
        # Worst first. The panel exists so Start can name what's missing, and
        # with the caller's order a run of green rows filled the visible area
        # and pushed the one blocking item below the fold. sorted() is stable,
        # so the caller's logical order survives inside each group.
        checks = sorted(checks, key=lambda c: self.LEVEL_ORDER.get(c[1], 1))

        for lbl in self._row_labels:
            self._rows_host.removeWidget(lbl)
            lbl.deleteLater()
        self._row_labels = []

        bad = sum(1 for _l, lv, _d in checks if lv == "bad")
        warn = sum(1 for _l, lv, _d in checks if lv == "warn")
        for label, level, detail in checks:
            color = self.DOT.get(level, DIM)
            name_color = TEXT if level == "ok" else color
            row = QLabel(
                f"{_dot(color)} <span style='color:{name_color}'>"
                f"{html.escape(str(label))}</span><br>"
                f"<span style='color:{FAINT};font-size:10px'>"
                f"{html.escape(str(detail))}</span>")
            row.setObjectName("checkRow")
            row.setTextFormat(Qt.RichText)
            row.setWordWrap(True)
            # The detail line wraps to 2-3 lines at this width; the tooltip is
            # the escape hatch when the panel is scrolled tight.
            row.setToolTip(f"{label}\n{detail}")
            self._rows_host.addWidget(row)
            self._row_labels.append(row)

        if bad:
            level, text = "bad", f"Not ready - {bad} item(s) to fix"
        elif warn:
            level, text = "warn", f"Ready - {warn} warning(s)"
        else:
            level, text = "ok", "All set - ready to run"
        self.summary.setText(text)
        self.summary.setProperty("level", level)
        _repolish(self.summary)


class StatsPanel(QGroupBox):
    """Run state + session/all-time W/L. The state pill and the step bar are
    the two things glanced at mid-run, so they sit at the top at full contrast
    and the tallies stay quiet underneath."""

    # Executor only emits IDLE/RUNNING today, but the pill is keyed off the
    # word so a future state string still lands on a sane colour.
    _BAD_STATES = ("STOP", "ERROR", "ABORT", "FAIL")

    def __init__(self):
        super().__init__("Statistics")
        v = QVBoxLayout(self)
        v.setContentsMargins(8, 3, 8, 7)
        v.setSpacing(5)

        top = QHBoxLayout()
        top.setSpacing(6)
        self.lbl_state = QLabel("IDLE")
        self.lbl_state.setObjectName("statePill")
        top.addWidget(self.lbl_state)
        self.lbl_run = QLabel("Run 0")
        self.lbl_run.setObjectName("muted")
        top.addWidget(self.lbl_run)
        top.addStretch(1)
        v.addLayout(top)

        self.lbl_step = QLabel("step -/-")
        self.lbl_step.setObjectName("caption")
        v.addWidget(self.lbl_step)

        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(6)
        self.bar.setRange(0, 1)
        self.bar.setValue(0)
        v.addWidget(self.bar)

        v.addWidget(hsep())

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(2)
        for col, head in enumerate(("", "Session", "Total")):
            lbl = QLabel(head)
            lbl.setObjectName("colHead")
            if col:
                lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            grid.addWidget(lbl, 0, col)
        grid.setColumnStretch(0, 1)

        def _row(r: int, caption: str, accent: bool = False):
            cap = QLabel(caption)
            cap.setObjectName("muted")
            grid.addWidget(cap, r, 0)
            out = []
            for col in (1, 2):
                val = QLabel("0")
                val.setObjectName("metricAccent" if accent else "metric")
                val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                grid.addWidget(val, r, col)
                out.append(val)
            return out

        self.lbl_session_w, self.lbl_total_w = _row(1, "Wins")
        self.lbl_session_l, self.lbl_total_l = _row(2, "Losses")
        self.lbl_session_r, self.lbl_total_r = _row(3, "Winrate", accent=True)
        self.lbl_session_r.setText("-")
        self.lbl_total_r.setText("-")
        v.addLayout(grid)
        v.addStretch(1)

        self.wins = 0
        self.losses = 0

    def set_state(self, s: str):
        self.lbl_state.setText(s)
        up = str(s).upper()
        if "RUN" in up:
            level = "run"
        elif any(k in up for k in self._BAD_STATES):
            level = "bad"
        else:
            level = "idle"
        self.lbl_state.setProperty("level", level)
        _repolish(self.lbl_state)

    def set_progress(self, run: int, step: int, total: int):
        self.lbl_run.setText(f"Run {run}")
        self.lbl_step.setText(f"step {step}/{total}")
        self.bar.setRange(0, max(1, int(total)))
        self.bar.setValue(max(0, int(step)))

    def record(self, won: bool):
        if won:
            self.wins += 1
        else:
            self.losses += 1
        total = self.wins + self.losses
        rate = f"{self.wins / total * 100:.0f}%" if total else "-"
        self.lbl_session_w.setText(str(self.wins))
        self.lbl_session_l.setText(str(self.losses))
        self.lbl_session_r.setText(rate)

    def set_totals(self, wins: int, losses: int):
        total = wins + losses
        rate = f"{wins / total * 100:.0f}%" if total else "-"
        self.lbl_total_w.setText(str(wins))
        self.lbl_total_l.setText(str(losses))
        self.lbl_total_r.setText(rate)


class WebhookPanel(QGroupBox):
    webhook_save_requested = Signal(str)
    webhook_test_requested = Signal(str)

    def __init__(self):
        super().__init__("Webhooks")
        v = QVBoxLayout(self)
        v.setContentsMargins(8, 3, 8, 7)
        v.setSpacing(4)

        hint = QLabel("Discord run results + loss-streak ping")
        hint.setObjectName("caption")
        hint.setWordWrap(True)
        v.addWidget(hint)

        self.ed_webhook = QLineEdit()
        self.ed_webhook.setPlaceholderText("https://discord.com/api/webhooks/...")
        self.ed_webhook.setToolTip("Paste a Discord webhook URL, then Save.")
        self.ed_webhook.textChanged.connect(self._on_text)
        self.ed_webhook.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        v.addWidget(self.ed_webhook)

        row = QHBoxLayout()
        row.setSpacing(5)
        self.btn_save = QPushButton("Save")
        self.btn_save.setToolTip("Write the URL to config.yaml.")
        self.btn_save.clicked.connect(
            lambda: self.webhook_save_requested.emit(self.ed_webhook.text().strip()))
        row.addWidget(self.btn_save)
        self.btn_test = QPushButton("Test")
        self.btn_test.setToolTip("Post a test message to the webhook now.")
        self.btn_test.clicked.connect(
            lambda: self.webhook_test_requested.emit(self.ed_webhook.text().strip()))
        row.addWidget(self.btn_test)
        v.addLayout(row)

        self.lbl_state = QLabel()
        self.lbl_state.setObjectName("caption")
        self.lbl_state.setTextFormat(Qt.RichText)
        v.addWidget(self.lbl_state)
        v.addStretch(1)

        self._on_text("")

    def _on_text(self, text: str):
        """Save/Test on an empty field can only fail, so they stay disabled -
        and the caption says whether notifications are actually live."""
        ok = bool(text.strip())
        self.btn_save.setEnabled(ok)
        self.btn_test.setEnabled(ok)
        self.lbl_state.setText(
            f"{_dot(OK)} <span style='color:{DIM}'>webhook set</span>" if ok
            else f"{_dot(FAINT)} <span style='color:{FAINT}'>no webhook - "
                 f"notifications off</span>")

    def set_webhook(self, url: str):
        self.ed_webhook.setText(url)
        # The field is narrower than a webhook URL; show the start of it (which
        # says which server it points at) rather than the trailing token.
        self.ed_webhook.setCursorPosition(0)
