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
# Nocturne design system (see design_handoff README): dark blue-grey ground,
# muted blurple accent, low-chroma status colours. Names describe the role, not
# the colour, so the role-based references below the QSS keep working.
ACCENT = "#9184D9"          # blurple: focus rings, progress, primary button edge
ACCENT_SOFT = "#D2CEFD"     # accent-300: section labels, winrate, readable accent
ACCENT_DEEP = "#39356B"     # blurple at selection-background strength

BG = "#161826"              # page / sunken wells / log body
SURFACE = "#232532"         # panel cards
RAISED = "#2B2D3B"          # pills, combo popup (buttons are outlined, not filled)
SUNKEN = "#12131E"          # inputs
BORDER = "#33353F"          # card-internal borders (~divider as a solid)
BORDER_HI = "#45474F"

TEXT = "#E9E9ED"
DIM = "#8E9098"             # secondary text (neutral-500)
FAINT = "#74767E"           # tertiary text - captions, timestamps (neutral-600)

OK = "#8FBF9A"
WARN = "#D9B878"
BAD = "#D98C8C"
OK_BG, WARN_BG, BAD_BG = "#22332B", "#33301F", "#33232A"

# Neutral ramp, interpolated between the design system's 100 and 900 endpoints.
# Only the rungs the mock actually uses are named.
N300 = "#C0C2CB"            # IDLE pill text
N400 = "#A7A9B1"            # checkbox label
N700 = "#5B5D65"            # off/idle status dot
N800 = "#42444B"            # IDLE pill background, scrollbar thumb
N900 = "#292B31"            # progress-bar track
DIVIDER = "rgba(233,233,237,0.16)"

DASHBOARD_QSS = f"""
QWidget {{ background: {BG}; color: {TEXT}; font-size: 13px; }}

/* The frameless window ground; a touch darker than the cards so the {SURFACE}
   cards read as raised surfaces (Nocturne). */
QWidget#dashRoot, QWidget#logRoot {{ background: #10111C; }}
/* The column / log hosts are transparent, so the ground above shows through the
   gaps between cards (not the generic QWidget background). */
QWidget#colHost, QWidget#logHost {{ background: transparent; }}

QLabel {{ background: transparent; color: {TEXT}; font-size: 13px; }}
QLabel#appTitle {{ color: {TEXT}; font-size: 15px; font-weight: 500; }}
QLabel#value {{ color: {TEXT}; font-size: 14px; font-weight: 500; }}
QLabel#muted {{ color: {DIM}; font-size: 13px; }}
QLabel#caption {{ color: {FAINT}; font-size: 11px; }}
QLabel#colHead {{ color: {FAINT}; font-size: 10px; font-weight: 500; }}
QLabel#metric {{ color: {TEXT}; font-size: 13px; }}
QLabel#metricAccent {{ color: {ACCENT_SOFT}; font-size: 13px; }}
/* Section labels: uppercase accent-300. text-transform isn't a Qt QSS property,
   so the text is upper-cased in code; this only carries colour/size/tracking. */
QLabel#sectionHead {{ color: {ACCENT_SOFT}; font-size: 12px; font-weight: 500; }}
QLabel#checkRow {{ padding: 7px 1px; border-bottom: 1px solid {DIVIDER}; }}

/* Pills carry run state / readiness at a glance. Level is a dynamic property,
   so set it then re-polish the widget (see _repolish). */
QLabel#statePill {{
    background: {N800}; color: {N300}; border: none;
    border-radius: 5px; padding: 4px 10px; font-size: 12px; font-weight: 500;
}}
QLabel#statePill[level="run"] {{ background: {OK_BG}; color: {OK}; }}
QLabel#statePill[level="bad"] {{ background: {BAD_BG}; color: {BAD}; }}
QLabel#summary {{ border: none; border-radius: 6px;
    padding: 5px 10px; font-size: 12px; color: {DIM}; background: {N800}; }}
QLabel#summary[level="ok"] {{ color: {OK}; background: {OK_BG}; }}
QLabel#summary[level="warn"] {{ color: {WARN}; background: {WARN_BG}; }}
QLabel#summary[level="bad"] {{ color: #F0B8B8; background: {BAD_BG}; }}

QFrame#sep {{ background: {DIVIDER}; border: none; }}
QWidget#anchorRow {{ border-bottom: 1px solid {DIVIDER}; }}
QWidget#checkWell {{ background: transparent; }}

/* Cards. No visible border - the surface tone against the darker ground is the
   edge (Nocturne). The title is the uppercase section label, top-left. */
QGroupBox {{
    background: {SURFACE}; border: none; border-radius: 8px;
    margin-top: 12px; padding: 6px 4px 4px 4px;
    color: {ACCENT_SOFT}; font-size: 12px; font-weight: 500;
}}
QGroupBox::title {{
    subcontrol-origin: margin; subcontrol-position: top left;
    left: 18px; top: 2px; padding: 0; background: transparent;
}}

/* Buttons are OUTLINED, not filled: transparent ground, 1px border. Secondary
   uses the neutral divider; primary the accent; danger a muted red; ghost none. */
QPushButton {{
    background: transparent; color: {TEXT}; border: 1px solid {BORDER};
    border-radius: 8px; padding: 7px 12px; font-size: 13px; text-align: center;
}}
QPushButton:hover {{ background: rgba(255,255,255,0.045); border-color: {BORDER_HI}; }}
QPushButton:pressed {{ background: rgba(255,255,255,0.02); }}
QPushButton:disabled {{ color: #5A5C64; border-color: #2A2C36; }}
QPushButton#primary {{ color: {ACCENT_SOFT}; border: 1px solid {ACCENT}; font-weight: 500; }}
QPushButton#primary:hover {{ background: rgba(145,132,217,0.13); border-color: {ACCENT}; }}
QPushButton#primary:pressed {{ background: rgba(145,132,217,0.06); }}
QPushButton#primary:disabled {{ color: #63608A; border-color: #3B3960; }}
QPushButton#danger {{ color: {BAD}; border: 1px solid #7A4A4A; }}
QPushButton#danger:hover {{ background: rgba(217,140,140,0.13); border-color: {BAD}; }}
QPushButton#danger:disabled {{ color: #6E5458; border-color: #4A3538; }}
QPushButton#ghost {{ background: transparent; color: {DIM}; border: none; padding: 4px 8px; font-size: 12px; }}
QPushButton#ghost:hover {{ color: {TEXT}; }}

QLineEdit, QSpinBox, QComboBox {{
    background: {SUNKEN}; color: {TEXT}; border: 1px solid {BORDER};
    border-radius: 8px; padding: 6px 8px; font-size: 13px;
    selection-background-color: {ACCENT_DEEP}; selection-color: {TEXT};
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{ border-color: {ACCENT}; }}
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {{
    background: #14151F; color: #5A5C64; border-color: #262832;
}}
/* Spin box arrows deliberately unstyled (see _NoWheelFilter): styling ::up-button
   makes Qt drop the native glyph unless an ::up-arrow image is supplied. */

QComboBox QAbstractItemView {{
    background: {RAISED}; color: {TEXT}; border: 1px solid {BORDER_HI};
    border-radius: 8px; selection-background-color: {ACCENT_DEEP};
    selection-color: {TEXT}; outline: none; padding: 2px;
}}

/* Log body: the sunken well inside the log card (color-bg), 4px radius. */
QTextEdit, QPlainTextEdit {{
    background: {BG}; color: #C8C8D0; border: 1px solid {DIVIDER};
    border-radius: 4px; font-family: "Cascadia Mono", Consolas, monospace;
    font-size: 13px; selection-background-color: {ACCENT_DEEP};
}}

QProgressBar {{
    background: {N900}; border: none; border-radius: 2px;
    text-align: center; color: transparent; max-height: 5px;
}}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 2px; }}

QTabWidget::pane {{
    border: 1px solid {BORDER}; border-radius: 8px; background: {SURFACE}; top: -1px;
}}
QTabBar::tab {{
    background: transparent; color: {DIM}; padding: 7px 14px;
    border-bottom: 2px solid transparent; margin-right: 2px; font-size: 13px;
}}
QTabBar::tab:hover {{ color: {TEXT}; }}
QTabBar::tab:selected {{
    color: {TEXT}; background: {SURFACE}; border-bottom: 2px solid {ACCENT};
}}

QSplitter::handle {{ background: {DIVIDER}; }}
QSplitter::handle:hover {{ background: {ACCENT}; }}
QSplitter::handle:horizontal {{ width: 5px; }}
QSplitter::handle:vertical {{ height: 5px; }}

QTableWidget {{
    background: {BG}; alternate-background-color: #1B1D2A; color: {TEXT};
    gridline-color: {DIVIDER}; border: 1px solid {BORDER}; border-radius: 8px;
    font-size: 13px;
    selection-background-color: {ACCENT_DEEP};
}}
/* Steps table header (editor): transparent with just a bottom divider, per the
   mock - the uppercase label text is set in code (Qt QSS has no text-transform). */
QHeaderView::section {{
    background: transparent; color: {FAINT}; border: none;
    border-bottom: 1px solid {DIVIDER};
    padding: 6px 8px; font-size: 11px; font-weight: 500;
}}

QScrollArea {{ border: none; }}
QScrollBar:vertical {{ background: transparent; width: 9px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {N800}; border-radius: 4px; min-height: 22px; }}
QScrollBar::handle:vertical:hover {{ background: {BORDER_HI}; }}
QScrollBar:horizontal {{ background: transparent; height: 9px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: {N800}; border-radius: 4px; min-width: 22px; }}
QScrollBar::handle:horizontal:hover {{ background: {BORDER_HI}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QCheckBox {{ color: {N400}; font-size: 13px; background: transparent; spacing: 8px; }}
QCheckBox::indicator {{
    width: 15px; height: 15px; border: 1px solid {BORDER_HI};
    border-radius: 4px; background: {SUNKEN};
}}
QCheckBox::indicator:hover {{ border-color: {ACCENT}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}

QToolTip {{
    background: {RAISED}; color: {TEXT}; border: 1px solid {BORDER_HI};
    padding: 5px 7px;
}}
QMessageBox {{ background: {SURFACE}; }}
QMessageBox QLabel {{ color: {TEXT}; font-size: 13px; }}
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
        super().__init__("CURRENT PROCESS")
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
        super().__init__("SETUP && RUN")
        # Vertical stack for the wide right-dock control column (the old compact
        # 3-column grid was for the short bottom bar). Reading order top to
        # bottom: state -> setup -> options -> run.
        v = QVBoxLayout(self)
        v.setSpacing(10)
        v.setContentsMargins(18, 8, 18, 16)

        # Exit sits top-right, opposite the section label, as far from
        # Start/Emergency stop as the card allows.
        top = QHBoxLayout()
        top.addStretch(1)
        self.btn_exit = QPushButton("Exit")
        self.btn_exit.setObjectName("ghost")
        self.btn_exit.setToolTip("Quit TD Macro. Stops the macro first if it's running.")
        self.btn_exit.clicked.connect(self.exit_requested.emit)
        top.addWidget(self.btn_exit)
        v.addLayout(top)

        self.lbl_attach = QLabel()
        self.lbl_attach.setTextFormat(Qt.RichText)
        self.lbl_attach.setStyleSheet("font-size:14px;")
        v.addWidget(self.lbl_attach)

        prof_row = QHBoxLayout()
        prof_row.setSpacing(10)
        lbl_prof = QLabel("Profile")
        lbl_prof.setObjectName("muted")
        prof_row.addWidget(lbl_prof)
        self.cb_profile = QComboBox()
        self.cb_profile.setToolTip("Choose a saved stage profile.")
        self.cb_profile.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.cb_profile.setMinimumHeight(38)
        self.cb_profile.activated.connect(self._on_profile_picked)
        prof_row.addWidget(self.cb_profile, 1)
        self.lbl_profile = QLabel()
        self.lbl_profile.setTextFormat(Qt.RichText)
        prof_row.addWidget(self.lbl_profile)
        v.addLayout(prof_row)

        self.btn_attach = QPushButton("Attach game window")
        self.btn_attach.setMinimumHeight(42)
        self.btn_attach.setToolTip(
            "Find Roblox, resize it to 1280×720, and dock this dashboard "
            "around it.")
        self.btn_attach.clicked.connect(self.attach_requested.emit)
        v.addWidget(self.btn_attach)

        row3 = QHBoxLayout()
        row3.setSpacing(8)
        self.btn_camera = QPushButton("Test camera view")
        self.btn_camera.setToolTip(
            "Preview the top-down camera the macro uses, so you can check it "
            "before capturing a reference image.")
        self.btn_camera.clicked.connect(self.camera_test_requested.emit)
        row3.addWidget(self.btn_camera, 1)
        self.btn_editor = QPushButton("Stage editor")
        self.btn_editor.setToolTip("Open the stage editor to build or edit your steps.")
        self.btn_editor.clicked.connect(self.editor_requested.emit)
        row3.addWidget(self.btn_editor, 1)
        self.btn_load = QPushButton("Load profile…")
        self.btn_load.setToolTip("Open a saved profile from a file.")
        self.btn_load.clicked.connect(self.load_requested.emit)
        row3.addWidget(self.btn_load, 1)
        v.addLayout(row3)

        # Runs are always infinite - Stop / F12 is how one ends.
        self.btn_shot = QPushButton("Screenshot")
        self.btn_shot.setToolTip("Save a screenshot of the game window.")
        self.btn_shot.clicked.connect(self.screenshot_requested.emit)
        v.addWidget(self.btn_shot)

        self.chk_start_game = QCheckBox("Auto-press 'Start Game' each round")
        self.chk_start_game.setToolTip(
            "Automatically press the in-game 'Start Game' button at the start of each round.")
        self.chk_start_game.toggled.connect(self.start_game_toggled.emit)
        v.addWidget(self.chk_start_game)

        v.addWidget(hsep())

        run_row = QHBoxLayout()
        run_row.setSpacing(10)
        self.btn_run = QPushButton("Start  (F9)")
        self.btn_run.setObjectName("primary")
        self.btn_run.setMinimumHeight(44)
        self.btn_run.clicked.connect(self.run_requested.emit)
        run_row.addWidget(self.btn_run, 2)

        self.btn_stop = QPushButton("Stop  (F12)")
        self.btn_stop.setObjectName("danger")
        self.btn_stop.setMinimumHeight(44)
        self.btn_stop.setToolTip("Emergency stop. Finishes the current step, then halts.")
        self.btn_stop.setEnabled(False)   # nothing to stop until a run starts
        self.btn_stop.clicked.connect(self.stop_requested.emit)
        run_row.addWidget(self.btn_stop, 1)
        v.addLayout(run_row)

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
            text = f"connected <span style='color:{DIM}'>{html.escape(detail)}</span>"
            self.lbl_attach.setText(f"{_dot(OK)} Roblox {text}")
        else:
            self.lbl_attach.setText(f"{_dot(BAD)} Roblox "
                                    f"<span style='color:{DIM}'>not connected</span>")

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
        super().__init__("READINESS")
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
        super().__init__("STATISTICS")
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
        super().__init__("WEBHOOKS")
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
