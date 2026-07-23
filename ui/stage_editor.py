"""Stage editor: load a reference screenshot, click to drop numbered markers,
assign an action and a wait condition to each one."""

import os

from PySide6.QtCore import Qt, QThread, QTimer, Signal, QRectF, QPointF
from PySide6.QtGui import QPixmap, QPen, QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGraphicsView, QGraphicsScene,
    QGraphicsEllipseItem, QGraphicsSimpleTextItem, QGraphicsRectItem,
    QTableWidget, QTableWidgetItem,
    QAbstractItemView, QHeaderView, QTabWidget, QScrollArea,
    QPushButton, QComboBox, QSpinBox, QDoubleSpinBox, QLabel, QLineEdit,
    QFileDialog, QMessageBox, QGroupBox, QSplitter, QAbstractSpinBox,
)

from data.profile import StageProfile, Step, MAX_STEPS
# Same theme as the dashboard - the editor is a second window of one tool, so
# it must not look like a different application.
from ui.panels import (
    DASHBOARD_QSS, ACCENT_SOFT, BAD, DIM, FAINT, OK, hsep, install_no_wheel_filter,
)

try:
    from core.input_driver import InputDriver
    from core.camera import CameraNormalizer
    HAS_CAMERA = True
except Exception:
    HAS_CAMERA = False

MARKER_R = 13
# Click-grab radius for picking up a marker, in scene units. Deliberately
# larger than the marker itself: the reference image is fit-to-view, so
# MARKER_R's 13 scene units render as only ~10 screen px, and a press that
# missed by a few pixels used to fall through to "clicked empty canvas" and
# silently ADD A STEP instead of grabbing the marker you were aiming at.
# The denser the stage, the easier that was to trigger. Trade-off: placing a
# brand-new step within this radius of an existing one now grabs the
# existing marker - use "+ Add step" and drag if you really need them that
# close together.
MARKER_GRAB_R = MARKER_R + 12
# Markers sit on top of a game screenshot, so they stay bright enough to survive
# a busy background. Colours are the Nocturne set from the Stage Editor mock:
# blurple placement, warm upgrade, cyan calibrated.
COLOR_PLACE = QColor("#9184D9")   # accent
COLOR_OTHER = QColor("#D9A45C")   # upgrade step
COLOR_SEL = QColor("#D2CEFD")     # accent-300 ring on the selected marker
CANVAS_BG = QColor("#050507")

# Calibration overlay (distinct cyan so anchors never look like step markers).
COLOR_ANCHOR = QColor("#5CC2D9")
COLOR_ANCHOR_EDGE = QColor("#0E3540")
COLOR_BOX_FILL = QColor(92, 194, 217, 55)

# Anchor sets the Calibrate tab drives. Point anchors are single [x, y]
# positions; box anchors are [x1, y1, x2, y2] HUD regions. "scope" says where
# the value lives: "profile" -> StageProfile.ui_anchors (saved with the
# profile), "config" -> config.yaml game section (saved immediately).
POINT_ANCHORS = [
    ("upgrade_btn", "Upgrade button", "profile"),
    ("sell_btn", "Sell button", "profile"),
    ("confirm_btn", "Confirm button", "profile"),
    ("priority_btn", "Priority button", "profile"),
    ("deselect_btn", "Unit panel close (X)", "profile"),
    ("repeat_btn", "Repeat Stage button", "profile"),
    ("start_game_btn", "Start Game button", "config"),
]
BOX_ANCHORS = [
    ("cash_roi", "Cash number (HUD)"),
    ("wave_roi", "Wave number (HUD)"),
    ("result_roi", "Win/Loss banner area"),
    ("upgrade_level_roi", "Upgrade N/M readout"),
    ("priority_label_roi", "Priority button label"),
    ("reward_strip_roi", "Post-match 'click to close' caption"),
    ("result_screen_roi", "Result screen search area"),
]


def hotbar_slot_count(cfg: dict) -> int:
    """How many unit cards the loadout has, per config.yaml's game.hotbar.
    Same source the executor clicks from (core/hotbar.py), so the editor can
    never offer a slot the run can't click."""
    hb = (cfg or {}).get("game", {}).get("hotbar", {}) or {}
    return len(hb.get("slots") or []) or int(hb.get("slot_count", 6))


def slot_combo(slot_count: int, value: int | None = None) -> QComboBox:
    """The 'Unit' picker: which hotbar card this step arms.

    A dropdown of the slots that actually exist, not a 1-9 spin box - the bar
    holds a fixed number of cards, so free-typing a 9 into a 6-card bar only
    ever produced a step the run had to skip. "none" (slot 0) arms nothing -
    for a Click step that shouldn't select a unit."""
    cb = QComboBox()
    cb.addItem("none")
    cb.addItems([str(i) for i in range(1, max(1, slot_count) + 1)])
    cb.setToolTip("Which hotbar card is armed before clicking the map. 'none' "
                  "arms nothing (a bare click). The card list comes from "
                  "game.hotbar in config.yaml - set slot_count to your loadout.")
    if value is not None:
        set_slot_value(cb, value)
    return cb


def set_slot_value(cb: QComboBox, value: int):
    """Select a slot, adding it first if the bar doesn't have that card. 0/none
    means no unit armed.

    A profile saved against a bigger loadout can name a slot this config
    doesn't cover. setCurrentText() on a missing entry is a silent no-op, so
    the step would display (and then save) as whatever was already showing -
    quietly rewriting the user's data. Showing the impossible value instead
    lets the Readiness check flag it."""
    text = "none" if not value else str(value)
    if cb.findText(text) < 0:
        cb.addItem(text)
    cb.setCurrentText(text)


class CameraTestThread(QThread):
    """Runs the real right-drag top-down sequence (core/camera.py) against
    the attached window - zoom in, pitch down, zoom out, all hard clamps -
    so it can be previewed before capturing the reference image. Off the
    GUI thread since it's a couple of seconds of humanized waits."""
    done = Signal()
    failed = Signal(str)

    def __init__(self, cfg, rect):
        super().__init__()
        self.cfg = cfg
        self.rect = rect

    def run(self):
        try:
            drv = InputDriver(self.cfg)
            cam = CameraNormalizer(drv, self.cfg)
            cam.normalize(self.rect)
            self.done.emit()
        except Exception as e:
            self.failed.emit(str(e))


class MarkerItem(QGraphicsEllipseItem):
    def __init__(self, step_id: int, x: float, y: float, color: QColor):
        super().__init__(QRectF(-MARKER_R, -MARKER_R, MARKER_R * 2, MARKER_R * 2))
        self.step_id = step_id
        self.setPos(x, y)
        self.setBrush(QBrush(color))
        self.setPen(QPen(QColor(255, 255, 255, 200), 1.5))
        self.setZValue(10)
        self.setFlag(QGraphicsEllipseItem.ItemIsMovable, True)
        self.setFlag(QGraphicsEllipseItem.ItemIsSelectable, True)
        self.setCursor(Qt.OpenHandCursor)

        self.label = QGraphicsSimpleTextItem(str(step_id), self)
        f = QFont()
        f.setPointSize(9)
        f.setBold(True)
        self.label.setFont(f)
        self.label.setBrush(QBrush(QColor("#FFFFFF")))
        br = self.label.boundingRect()
        self.label.setPos(-br.width() / 2, -br.height() / 2)


class StageCanvas(QGraphicsView):
    # Emitted for a left-click on the image that didn't land on a marker.
    # The canvas does NOT decide what that means - the editor does (it puts
    # the selected row's spot there). This used to be marker_added, i.e. a
    # bare click created a step, which is what made "move" so easy to
    # misfire into "add" (HANDOFF 2.24).
    canvas_clicked = Signal(float, float)    # normalized 0-1
    marker_clicked = Signal(int)
    marker_moved = Signal(int, float, float)
    calib_point = Signal(str, float, float)              # anchor name, nx, ny
    calib_box = Signal(str, float, float, float, float)  # anchor name, x1,y1,x2,y2

    def __init__(self):
        super().__init__()
        sp = self.sizePolicy()
        sp.setHeightForWidth(True)
        self.setSizePolicy(sp)
        self.scene_ = QGraphicsScene(self)
        self.setScene(self.scene_)
        self.setRenderHints(self.renderHints())
        self.setDragMode(QGraphicsView.NoDrag)
        # The viewport is painted by the scene, not the stylesheet, so the dark
        # field behind the reference image has to be set on the view itself.
        self.setBackgroundBrush(QBrush(CANVAS_BG))
        self.setFrameShape(QGraphicsView.NoFrame)
        self.pixmap_item = None
        self.markers: dict[int, MarkerItem] = {}
        self._drag_start = None
        # Calibration state: when calib_mode is an anchor name, the next click
        # (point) or drag (box) sets that anchor instead of adding a step.
        self.calib_mode = None
        self.calib_kind = None       # "point" | "box"
        self._anchor_items = []       # overlay graphics for the current anchors
        self._box_start = None
        self._rubber = None

    def set_image(self, path: str) -> bool:
        pm = QPixmap(path)
        if pm.isNull():
            return False
        self.scene_.clear()   # wipes markers AND anchor overlays - both get redrawn
        self.markers.clear()
        self._anchor_items = []
        self._rubber = None
        self._box_start = None
        self.pixmap_item = self.scene_.addPixmap(pm)
        self.scene_.setSceneRect(QRectF(pm.rect()))
        self.fitInView(self.scene_.sceneRect(), Qt.KeepAspectRatio)
        self.updateGeometry()   # heightForWidth now follows the real image
        return True

    def show_placeholder(self, text: str):
        """Empty-state hint. An empty black rectangle gives no clue that the
        first move is 'Capture ref'; this says so on the canvas itself."""
        if self.pixmap_item:
            return
        self.scene_.clear()
        self.scene_.setSceneRect(QRectF(0, 0, 640, 360))
        item = QGraphicsSimpleTextItem(text)
        f = QFont()
        f.setPointSize(11)
        item.setFont(f)
        item.setBrush(QBrush(QColor("#4E4E5C")))
        br = item.boundingRect()
        item.setPos(320 - br.width() / 2, 180 - br.height() / 2)
        self.scene_.addItem(item)
        self.centerOn(320, 180)

    # ---------------- calibration overlay ----------------

    def set_calib_mode(self, name, kind):
        self.calib_mode = name
        self.calib_kind = kind
        self.setCursor(Qt.CrossCursor if name else Qt.ArrowCursor)

    def set_picking(self, on: bool):
        """Crosshair while a row is selected - i.e. while a click on the image
        would actually go somewhere."""
        if not self.calib_mode:
            self.setCursor(Qt.CrossCursor if on else Qt.ArrowCursor)

    def _marker_near(self, pos):
        """Nearest marker within MARKER_GRAB_R of pos, or None.

        Distance-to-centre rather than scene_.itemAt()'s exact shape test, so
        a press that lands just outside the drawn circle still grabs it (see
        MARKER_GRAB_R). Nearest-wins, so a generous radius can't grab the
        wrong marker when two are close together."""
        best, best_d = None, None
        limit = MARKER_GRAB_R ** 2
        for m in self.markers.values():
            mp = m.pos()
            d = (mp.x() - pos.x()) ** 2 + (mp.y() - pos.y()) ** 2
            if d <= limit and (best_d is None or d < best_d):
                best, best_d = m, d
        return best

    def clear_anchors(self):
        for it in self._anchor_items:
            self.scene_.removeItem(it)
        self._anchor_items = []

    def draw_anchors(self, points: dict, boxes: dict):
        """points: {name: (nx, ny)}; boxes: {name: (x1, y1, x2, y2)}."""
        if not self.pixmap_item:
            return
        self.clear_anchors()
        w, h = self.img_size()
        for name, (nx, ny) in points.items():
            r = 8
            dot = QGraphicsEllipseItem(QRectF(nx * w - r, ny * h - r, r * 2, r * 2))
            dot.setBrush(QBrush(COLOR_ANCHOR))
            dot.setPen(QPen(COLOR_ANCHOR_EDGE, 1.5))
            dot.setZValue(20)
            self.scene_.addItem(dot)
            self._anchor_items.append(dot)
            self._anchor_items.append(self._label(name, nx * w + 10, ny * h - 8))
        for name, (x1, y1, x2, y2) in boxes.items():
            box = QGraphicsRectItem(QRectF(x1 * w, y1 * h, (x2 - x1) * w, (y2 - y1) * h))
            box.setBrush(QBrush(COLOR_BOX_FILL))
            box.setPen(QPen(COLOR_ANCHOR, 1.5))
            box.setZValue(19)
            self.scene_.addItem(box)
            self._anchor_items.append(box)
            self._anchor_items.append(self._label(name, x1 * w + 3, y1 * h + 2))

    def _label(self, text: str, x: float, y: float):
        t = QGraphicsSimpleTextItem(text)
        f = QFont()
        f.setPointSize(7)
        t.setFont(f)
        t.setBrush(QBrush(COLOR_ANCHOR))
        t.setPos(x, y)
        t.setZValue(21)
        self.scene_.addItem(t)
        return t

    def img_size(self) -> tuple[int, int]:
        if not self.pixmap_item:
            return (1, 1)
        r = self.pixmap_item.pixmap()
        return r.width(), r.height()

    def add_marker(self, step_id: int, nx: float, ny: float, is_place: bool):
        w, h = self.img_size()
        color = COLOR_PLACE if is_place else COLOR_OTHER
        m = MarkerItem(step_id, nx * w, ny * h, color)
        self.scene_.addItem(m)
        self.markers[step_id] = m

    def clear_markers(self):
        for m in self.markers.values():
            self.scene_.removeItem(m)
        self.markers.clear()

    def highlight(self, step_id: int | None):
        for sid, m in self.markers.items():
            pen = QPen(COLOR_SEL if sid == step_id else QColor(255, 255, 255, 200))
            pen.setWidthF(3.0 if sid == step_id else 1.5)
            m.setPen(pen)

    # The view is height-for-width: a 16:9 reference in a full-height column
    # letterboxed into ~150px of black above and below the image, which is
    # dead space right where the user is working. Claiming only the height the
    # image actually needs turns those bands back into ordinary page
    # background, and lets the legend sit directly under the image.
    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, w: int) -> int:
        iw, ih = self.img_size()
        if iw <= 1 or ih <= 1:
            iw, ih = 16, 9
        return max(220, int(w * ih / iw))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.pixmap_item:
            self.fitInView(self.scene_.sceneRect(), Qt.KeepAspectRatio)

    def mousePressEvent(self, e):
        if not self.pixmap_item:
            return
        pos = self.mapToScene(e.position().toPoint())

        # Calibration intercepts the click BEFORE any step-marker handling, so
        # setting an anchor never accidentally drops or selects a step marker.
        if self.calib_mode and e.button() == Qt.LeftButton:
            w, h = self.img_size()
            if self.calib_kind == "point":
                nx = max(0.0, min(1.0, pos.x() / w))
                ny = max(0.0, min(1.0, pos.y() / h))
                name = self.calib_mode
                self.set_calib_mode(None, None)
                self.calib_point.emit(name, round(nx, 4), round(ny, 4))
                return
            if self.calib_kind == "box":
                self._box_start = pos
                self._rubber = QGraphicsRectItem(QRectF(pos, pos))
                self._rubber.setPen(QPen(COLOR_ANCHOR, 1.5))
                self._rubber.setBrush(QBrush(COLOR_BOX_FILL))
                self._rubber.setZValue(30)
                self.scene_.addItem(self._rubber)
                return

        # Landing on a marker means "grab this one" - selecting its row and,
        # if the mouse then moves, dragging it.
        marker = self._marker_near(pos)
        if marker is not None:
            self._drag_start = marker
            self.marker_clicked.emit(marker.step_id)
            super().mousePressEvent(e)
            return
        if e.button() == Qt.LeftButton:
            w, h = self.img_size()
            if 0 <= pos.x() <= w and 0 <= pos.y() <= h:
                self.canvas_clicked.emit(pos.x() / w, pos.y() / h)
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._rubber is not None and self._box_start is not None:
            pos = self.mapToScene(e.position().toPoint())
            self._rubber.setRect(QRectF(self._box_start, pos).normalized())
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if self._rubber is not None and self._box_start is not None:
            pos = self.mapToScene(e.position().toPoint())
            w, h = self.img_size()
            r = QRectF(self._box_start, pos).normalized()
            x1 = max(0.0, min(1.0, r.left() / w))
            y1 = max(0.0, min(1.0, r.top() / h))
            x2 = max(0.0, min(1.0, r.right() / w))
            y2 = max(0.0, min(1.0, r.bottom() / h))
            self.scene_.removeItem(self._rubber)
            self._rubber = None
            self._box_start = None
            name = self.calib_mode
            self.set_calib_mode(None, None)
            # A click-without-drag makes a zero-size box - ignore it so the
            # user can just retry instead of saving a useless empty region.
            if name and x2 - x1 > 0.005 and y2 - y1 > 0.005:
                self.calib_box.emit(name, round(x1, 4), round(y1, 4),
                                    round(x2, 4), round(y2, 4))
            return
        if self._drag_start is not None:
            m = self._drag_start
            w, h = self.img_size()
            p = m.pos()
            self.marker_moved.emit(m.step_id,
                                   max(0.0, min(1.0, p.x() / w)),
                                   max(0.0, min(1.0, p.y() / h)))
            self._drag_start = None
        super().mouseReleaseEvent(e)


class StepRow:
    """The widgets for one row of the steps table.

    A row is one action at one spot on the map, in run order (HANDOFF 2.24 /
    2.27): put a unit here, or click here and buy some levels. Upgrading is
    its own row at the SAME position as the placement it upgrades - that's
    the model the user asked for, and it reads the way the run actually
    behaves (click the spot, then work the panel).

    The widgets write straight through to the Step. Nothing here rebuilds
    the table, because rebuilding destroys the widget mid-edit - the same
    trap the card grid hit.
    """

    # Label -> (Step.action, Step.upgrade_mode).
    WHAT = [("Place", "place", "off"),
            ("Click", "click", "off"),
            ("Upgrade to N", "upgrade", "off"),
            ("Upgrade to max", "upgrade", "max")]

    def __init__(self, step: Step, slot_count: int, on_change, on_move):
        self.step = step
        self._loading = True
        self.on_change = on_change
        self.on_move = on_move

        self.sp_x = self._coord(step.x)
        self.sp_y = self._coord(step.y)
        self.cb_unit = slot_combo(slot_count, step.slot)
        self.cb_unit.currentTextChanged.connect(self._apply)

        self.cb_what = QComboBox()
        self.cb_what.addItems([label for label, _, _ in self.WHAT])
        idx = next((i for i, (_, act, mode) in enumerate(self.WHAT)
                    if act == step.action and mode == step.upgrade_mode), None)
        if idx is None:
            # Either a sell/ability/wait step this editor no longer creates,
            # or an old 'place' row that carried a bundled upgrade_mode
            # (pre-2.27). Show what it is rather than silently rewriting it.
            self.cb_what.addItem(step.summary())
            self.cb_what.setCurrentIndex(self.cb_what.count() - 1)
        else:
            self.cb_what.setCurrentIndex(idx)
        self.cb_what.currentIndexChanged.connect(self._apply)

        self.sp_times = QSpinBox()
        self.sp_times.setRange(1, 20)
        self.sp_times.setValue(step.times)
        # No step arrows - on the dark theme they render as a murky block, and
        # the wheel is filtered out anyway, so it's a plain typed number field.
        self.sp_times.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.sp_times.setFixedWidth(46)
        self.sp_times.setToolTip("How many levels to buy. Each one is clicked "
                                 "until the panel's level readout actually "
                                 "changes, so \"can't afford it yet\" just waits.")
        self.sp_times.valueChanged.connect(self._apply)

        # Combo + count share one cell so the table keeps the four columns
        # the user asked for; the count only appears when it means something.
        self.what_cell = QWidget()
        h = QHBoxLayout(self.what_cell)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(4)
        h.addWidget(self.cb_what, 1)
        h.addWidget(self.sp_times)
        self._sync_enabled()
        self._loading = False

    def _coord(self, value: float) -> QDoubleSpinBox:
        sp = QDoubleSpinBox()
        sp.setRange(0.0, 1.0)
        sp.setDecimals(3)
        sp.setSingleStep(0.005)
        sp.setButtonSymbols(QAbstractSpinBox.NoButtons)   # plain text field, no arrow block
        sp.setValue(value)
        sp.setToolTip("Position on the reference image, 0-1. Clicking the "
                      "image with this row selected sets it.")
        sp.valueChanged.connect(self._apply_pos)
        return sp

    def _sync_enabled(self):
        """The count only means something for "Upgrade to N"; the unit only
        means something for a placement or a click (an upgrade row acts on
        whatever is already standing at its position). A click can arm a unit
        or, with "none", just click."""
        self.sp_times.setVisible(self.cb_what.currentText() == "Upgrade to N")
        self.cb_unit.setEnabled(self.step.action in ("place", "click"))

    def set_position(self, x: float, y: float):
        """Marker was dragged - show the new spot without re-entering _apply."""
        self._loading = True
        self.sp_x.setValue(x)
        self.sp_y.setValue(y)
        self._loading = False

    def _apply_pos(self, *_):
        if self._loading:
            return
        self.step.x = round(self.sp_x.value(), 4)
        self.step.y = round(self.sp_y.value(), 4)
        self.on_move()

    def _apply(self, *_):
        if self._loading:
            return
        unit = self.cb_unit.currentText()
        self.step.slot = 0 if unit == "none" else int(unit)
        label = self.cb_what.currentText()
        for text, action, mode in self.WHAT:
            if text == label:
                self.step.action = action
                self.step.upgrade_mode = mode
                break
        # No else: an unrecognised label is the "leave this legacy row alone"
        # entry added above, and rewriting it is exactly what must not happen.
        self.step.times = self.sp_times.value()
        self._sync_enabled()
        self.on_change()


class StageEditor(QWidget):
    def __init__(self, cfg: dict, get_client_rect=None, capture_fn=None, focus_fn=None,
                 save_start_game_fn=None, ocr_test_fn=None):
        super().__init__()
        self.cfg = cfg
        self.get_client_rect = get_client_rect
        self.capture_fn = capture_fn
        self.focus_fn = focus_fn
        # Persists game.start_game_btn to config.yaml (App wires this up); the
        # other anchors live in the profile and save with it.
        self.save_start_game_fn = save_start_game_fn
        # Live OCR probe for a cash/wave box -> (value, error). Lets the user
        # confirm a HUD box is placed right before relying on it in a run.
        self.ocr_test_fn = ocr_test_fn
        self.profile = StageProfile()
        self.current_path = None
        self._rows: list[StepRow] = []

        self.setWindowTitle("Stage editor")
        self.resize(1260, 780)
        self.setMinimumSize(900, 560)
        self.setStyleSheet(DASHBOARD_QSS)
        # Wheel must never change a spin box / combo value - every row of the
        # steps table is four of them.
        install_no_wheel_filter()
        self._build()
        self._refresh_list()

    # ---------------- layout ----------------

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 6)
        root.setSpacing(7)

        top = QHBoxLayout()
        top.setSpacing(6)
        lbl_stage = QLabel("Stage")
        lbl_stage.setObjectName("muted")
        top.addWidget(lbl_stage)
        self.stage_name = QLineEdit(self.profile.stage)
        self.stage_name.setPlaceholderText("Stage name (used for profile + capture filenames)")
        self.stage_name.textChanged.connect(self._on_name)
        top.addWidget(self.stage_name, 1)

        # Capture / Load / Save are the file-level actions; Save is the one the
        # user must not miss after calibrating, so it carries the accent.
        for text, fn, tip, obj in [
            ("Capture ref", self.capture_reference,
             "Raise Roblox and snapshot its client area as this stage's "
             "reference image.", ""),
            ("Load", self.load_profile, "Open a saved profile (.json).", ""),
            ("Save", self.save_profile,
             "Write steps + calibrated anchors to the profile file.", "primary"),
        ]:
            b = QPushButton(text)
            b.setToolTip(tip)
            if obj:
                b.setObjectName(obj)
            b.clicked.connect(fn)
            top.addWidget(b)
        root.addLayout(top)
        root.addWidget(hsep())

        split = QSplitter(Qt.Horizontal)
        split.setChildrenCollapsible(False)

        self.canvas = StageCanvas()
        self.canvas.canvas_clicked.connect(self._on_canvas_click)
        self.canvas.marker_clicked.connect(self._on_pick)
        self.canvas.marker_moved.connect(self._on_move)
        self.canvas.calib_point.connect(self._on_calib_point)
        self.canvas.calib_box.connect(self._on_calib_box)

        # A 16:9 reference in a tall canvas letterboxes badly, and that dead
        # space is exactly where the user is looking. The legend strip below
        # the image eats some of it and explains the marker colours, and the
        # right column gets a bigger share of the width (taking width off the
        # canvas costs nothing until it is narrower than 16:9).
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(5)
        lv.addWidget(self.canvas)          # height-for-width: no stretch here
        lv.addWidget(self._build_legend())
        self.hint_card = self._build_hints()
        lv.addWidget(self.hint_card)
        lv.addStretch(1)
        split.addWidget(left)

        side = QWidget()
        sl = QVBoxLayout(side)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(6)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)

        steps_tab = QWidget()
        tv = QVBoxLayout(steps_tab)
        tv.setContentsMargins(6, 6, 6, 6)
        tv.setSpacing(5)
        cap_all = QLabel("What the macro does, in order. Select a row, then click "
                         "the image to set its spot. To upgrade a unit, add a "
                         "row at the SAME spot and pick how many levels.")
        cap_all.setObjectName("caption")
        cap_all.setWordWrap(True)
        tv.addWidget(cap_all)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["#", "X", "Y", "UNIT", "WHAT TO DO"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        # Only the "#" column is a plain item, and it isn't editable - every
        # other column is a real widget the user drives directly.
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setFrameShape(QTableWidget.NoFrame)
        self.table.verticalHeader().setDefaultSectionSize(30)
        header = self.table.horizontalHeader()
        header.setHighlightSections(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.currentCellChanged.connect(self._on_row_changed)
        tv.addWidget(self.table)
        self.tabs.addTab(steps_tab, "Steps")

        self.tabs.addTab(self._build_calib_tab(), "Calibrate")

        head = QHBoxLayout()
        head.setSpacing(6)
        lbl_steps = QLabel("THIS RUN")
        lbl_steps.setObjectName("sectionHead")
        head.addWidget(lbl_steps)
        self.lbl_step_count = QLabel("nothing added yet")
        self.lbl_step_count.setObjectName("caption")
        head.addWidget(self.lbl_step_count)
        head.addStretch(1)
        btn_add = QPushButton("+ Add step")
        btn_add.setToolTip("Add a row, then click the image to place it.")
        btn_add.clicked.connect(self._add_step_clicked)
        head.addWidget(btn_add)
        btn_del = QPushButton("Delete")
        btn_del.setObjectName("danger")
        btn_del.setToolTip("Delete the selected row.")
        btn_del.clicked.connect(self._delete)
        head.addWidget(btn_del)
        sl.addLayout(head)
        sl.addWidget(self.tabs, 1)

        split.addWidget(side)
        split.setSizes([700, 560])
        root.addWidget(split, 1)

        root.addWidget(hsep())
        self.status = QLabel()
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        self._status("Capture a reference image to begin.")

        self.canvas.show_placeholder("No reference image - click 'Capture ref'")
        self._refresh_calib_labels()

    def _build_legend(self) -> QWidget:
        """Colour key + the two canvas gestures, parked under the image where
        the letterboxing leaves dead space anyway."""
        bar = QWidget()
        h = QHBoxLayout(bar)
        h.setContentsMargins(2, 0, 2, 0)
        h.setSpacing(12)
        key = QLabel(
            f"<span style='color:{COLOR_PLACE.name()}'>&#9679;</span> unit placement"
            f" &nbsp; <span style='color:{COLOR_OTHER.name()}'>&#9679;</span> upgrade step"
            f" &nbsp; <span style='color:{COLOR_ANCHOR.name()}'>&#9679;</span> calibrated spot")
        key.setTextFormat(Qt.RichText)
        h.addWidget(key)
        h.addStretch(1)
        tip = QLabel("Select a row, then click the image to set its spot - "
                     "or just drag a marker.")
        tip.setObjectName("caption")
        h.addWidget(tip)
        return bar

    def _build_hints(self) -> QWidget:
        """First-run running order, parked in the space the image doesn't use.
        Hidden again as soon as there is a reference and at least one step, so
        it never nags someone who already knows the tool."""
        box = QGroupBox("Getting started")
        v = QVBoxLayout(box)
        v.setContentsMargins(10, 6, 10, 8)
        text = QLabel(
            "1.  On the dashboard: Attach + center window, then Test camera view.<br>"
            "2.  Here: <b>Capture ref</b> - takes the picture everything else is "
            "positioned against.<br>"
            "3.  <b>Calibrate</b> tab: click each game button, drag a box round "
            "the cash and wave numbers.<br>"
            "4.  <b>+ Add step</b> for each unit, then click the picture where "
            "it should go and pick its unit number. To upgrade one, add "
            "another row at the same spot and set 'Upgrade to N'.<br>"
            "5.  <b>Save</b>, and press Start back on the dashboard.")
        text.setObjectName("muted")
        text.setTextFormat(Qt.RichText)
        text.setWordWrap(True)
        v.addWidget(text)
        return box

    def _update_hints(self):
        card = getattr(self, "hint_card", None)
        if card is not None:
            card.setVisible(not (self.profile.reference_image and self.profile.steps))

    def _status(self, msg: str, level: str = "info"):
        """Single status line at the bottom of the editor. The default is the
        accent-300 status colour from the mock; level still overrides it so a
        refusal ('capture a reference first') isn't mistaken for progress."""
        color = {"bad": BAD, "ok": OK}.get(level, ACCENT_SOFT)
        self.status.setStyleSheet(f"color: {color}; padding: 3px 2px; font-size: 12px;")
        self.status.setText(msg)

    # ---------------- calibrate tab ----------------

    def _build_calib_tab(self) -> QWidget:
        """One row per anchor: its current value + a Set button. 'Set point'
        arms the canvas so the next click on the reference image sets that
        button's position; 'Set box' arms it so a drag sets that HUD region.
        No pixel math, no editing JSON by hand."""
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(7)
        intro = QLabel(
            "Click 'Set', then click (buttons) or drag a box (HUD regions) on "
            "the reference image. Button positions save with the profile - click "
            "Save when done. The Start Game button saves immediately.")
        intro.setObjectName("caption")
        intro.setWordWrap(True)
        v.addWidget(intro)

        self._calib_value_labels = {}
        self._calib_dots = {}

        def add_row(host, name, label, on_click, btn_text, extra=None):
            # Two lines per anchor (name + action, then the value underneath),
            # boxed in its own bordered row. One long line did not survive the
            # editor's right column being dragged narrow - the Set button was
            # the first thing clipped - and without the row border the value
            # line floated between the anchor above and below it.
            row = QWidget()
            row.setObjectName("anchorRow")
            grid = QGridLayout(row)
            grid.setContentsMargins(2, 3, 2, 4)
            grid.setHorizontalSpacing(7)
            grid.setVerticalSpacing(1)
            # A dot per anchor so "what is still unset" is one glance down the
            # left edge instead of reading every value.
            dot = QLabel("●")
            self._calib_dots[name] = dot
            grid.addWidget(dot, 0, 0)
            grid.addWidget(QLabel(label), 0, 1)
            b = QPushButton(btn_text)
            b.clicked.connect(on_click)
            grid.addWidget(b, 0, 2)
            val = QLabel("not set")
            self._calib_value_labels[name] = val
            grid.addWidget(val, 1, 1)
            if extra is not None:
                grid.addWidget(extra, 1, 2)
            grid.setColumnStretch(1, 1)
            host.addWidget(row)

        btn_box = QGroupBox("Buttons - click a spot")
        bg = QVBoxLayout(btn_box)
        bg.setContentsMargins(9, 6, 9, 8)
        bg.setSpacing(2)
        for name, label, scope in POINT_ANCHORS:
            add_row(bg, name, label,
                    lambda _=False, n=name: self._start_calib_point(n), "Set point")
            if scope == "config":
                self._calib_value_labels[name].setToolTip(
                    "Saved to config.yaml immediately, not with the profile.")
        v.addWidget(btn_box)

        roi_box = QGroupBox("HUD regions - drag a box")
        rg = QVBoxLayout(roi_box)
        rg.setContentsMargins(9, 6, 9, 8)
        rg.setSpacing(2)
        for name, label in BOX_ANCHORS:
            # OCR-read boxes offer a live test so the user can confirm the box
            # catches just the number/word. It sits with the box it tests
            # instead of on a row of its own.
            extra = None
            if name in ("cash_roi", "wave_roi", "upgrade_level_roi", "priority_label_roi"):
                extra = QPushButton("Test read")
                extra.setObjectName("ghost")
                extra.setToolTip("Read this HUD region from the live game right now.")
                extra.clicked.connect(lambda _=False, n=name: self._test_ocr(n))
            add_row(rg, name, label,
                    lambda _=False, n=name: self._start_calib_box(n), "Set box", extra)
        v.addWidget(roi_box)
        v.addStretch(1)

        # The editor's right column can be short (see the splitter notes), so
        # the anchor list scrolls rather than squeezing the tab below it.
        tab = QScrollArea()
        tab.setWidgetResizable(True)
        tab.setFrameShape(QScrollArea.NoFrame)
        tab.setWidget(page)
        return tab

    def _test_ocr(self, name: str):
        if not self.ocr_test_fn:
            self._status("OCR test unavailable.", "bad")
            return
        roi = self.profile.ui_anchors.get(name)
        if not roi or len(roi) != 4:
            self._status(f"Set the {name} box first, then test it.", "bad")
            return
        val, err = self.ocr_test_fn(roi, name)
        if err:
            self._status(f"OCR test: {err}", "bad")
        elif val is None:
            self._status(f"OCR read nothing from {name} - make the box "
                         "tighter around just the number and try again.", "bad")
        else:
            self._status(f"OCR read {name.split('_')[0]} = {val}", "ok")

    def _anchor_value(self, name: str):
        if name == "start_game_btn":
            return self.cfg.get("game", {}).get("start_game_btn")
        return self.profile.ui_anchors.get(name)

    def _start_calib_point(self, name: str):
        if not self.profile.reference_image:
            self._status("Capture a reference image first, then calibrate.", "bad")
            return
        self.canvas.set_calib_mode(name, "point")
        self._status(f"Click the {name} location on the image.")

    def _start_calib_box(self, name: str):
        if not self.profile.reference_image:
            self._status("Capture a reference image first, then calibrate.", "bad")
            return
        self.canvas.set_calib_mode(name, "box")
        self._status(f"Drag a box around {name} on the image.")

    def _on_calib_point(self, name: str, nx: float, ny: float):
        val = [round(nx, 4), round(ny, 4)]
        if name == "start_game_btn":
            self.cfg.setdefault("game", {})["start_game_btn"] = val
            if self.save_start_game_fn:
                self.save_start_game_fn(val)
        else:
            self.profile.ui_anchors[name] = val
        self._refresh_calib_labels()
        self._redraw_anchors()
        self._status(f"{name} set to {val[0]:.3f}, {val[1]:.3f}.", "ok")

    def _on_calib_box(self, name: str, x1: float, y1: float, x2: float, y2: float):
        self.profile.ui_anchors[name] = [x1, y1, x2, y2]
        self._refresh_calib_labels()
        self._redraw_anchors()
        self._status(f"{name} region set.", "ok")

    def _refresh_calib_labels(self):
        anchor_color = COLOR_ANCHOR.name()
        for name, lbl in getattr(self, "_calib_value_labels", {}).items():
            v = self._anchor_value(name)
            dot = self._calib_dots.get(name)
            if not v:
                lbl.setText("not set")
                lbl.setStyleSheet(f"color: {FAINT}; font-size: 11px;")
                if dot:
                    dot.setStyleSheet(f"color: {FAINT};")
                continue
            if len(v) == 2:
                lbl.setText(f"{v[0]:.3f}, {v[1]:.3f}")
            else:
                lbl.setText(f"{v[0]:.3f},{v[1]:.3f} - {v[2]:.3f},{v[3]:.3f}")
            lbl.setStyleSheet(f"color: {anchor_color}; font-size: 11px;")
            if dot:
                dot.setStyleSheet(f"color: {anchor_color};")

    def _redraw_anchors(self):
        points, boxes = {}, {}
        for name, _label, _scope in POINT_ANCHORS:
            v = self._anchor_value(name)
            if v and len(v) == 2:
                points[name] = (v[0], v[1])
        for name, _label in BOX_ANCHORS:
            v = self._anchor_value(name)
            if v and len(v) == 4:
                boxes[name] = (v[0], v[1], v[2], v[3])
        self.canvas.draw_anchors(points, boxes)

    # ---------------- image ----------------

    def capture_reference(self):
        if not self.capture_fn or not self.get_client_rect:
            QMessageBox.warning(self, "Capture", "Roblox window not attached.")
            return
        rect = self.get_client_rect()
        if rect is None:
            QMessageBox.warning(self, "Capture", "Roblox window not found.")
            return
        # mss grabs whatever is drawn at those screen coords - if this editor
        # window is sitting over Roblox we'd capture ourselves. Raise Roblox
        # to the front first (focus() waits for it to come forward).
        if self.focus_fn:
            self.focus_fn()
        os.makedirs("profiles", exist_ok=True)
        safe = "".join(c if c.isalnum() else "_" for c in self.profile.stage)
        path = os.path.join("profiles", f"{safe}_ref.png")
        self.capture_fn(rect, path)
        if self.canvas.set_image(path):
            self.profile.reference_image = path
            self._redraw_markers()
            self._redraw_anchors()
            self._status(f"Reference saved: {path} - now open the "
                         "Calibrate tab and set the buttons/HUD regions.", "ok")
        else:
            QMessageBox.warning(self, "Capture", "Failed to read captured image.")

    # ---------------- markers ----------------

    def _add_step_clicked(self):
        """Add a row and select it. The map click that follows sets its spot -
        adding is ALWAYS explicit now, so nothing the user does on the canvas
        can create a step by accident (HANDOFF 2.24)."""
        if not self.profile.reference_image:
            self._status("Capture or load a reference image first.", "bad")
            return
        n = len(self.profile.steps)
        nx = min(0.95, 0.05 + (n % 20) * 0.045)
        ny = min(0.95, 0.05 + (n // 20) * 0.045)
        s = self.profile.add_step(nx, ny)
        if s is None:
            self._status(f"Step limit reached ({MAX_STEPS}) - delete one to "
                         "add another.", "bad")
            return
        self._redraw_markers()
        self._refresh_list()
        self.table.setCurrentCell(len(self.profile.steps) - 1, 0)
        self._status(f"Added step #{s.id} - now click the image to place it.")

    def _on_canvas_click(self, nx: float, ny: float):
        """A click on the image moves the SELECTED row's spot there. That is
        the click's only meaning - see StageCanvas.canvas_clicked."""
        s = self._current()
        if not s:
            self._status("Select a row first (or press '+ Add step'), then "
                         "click the image to set its spot.", "bad")
            return
        s.x, s.y = round(nx, 4), round(ny, 4)
        row = self.table.currentRow()
        if 0 <= row < len(self._rows):
            self._rows[row].set_position(s.x, s.y)
        self._redraw_markers()
        self.canvas.highlight(s.id)
        self._status(f"Step #{s.id} spot set to {s.x:.3f}, {s.y:.3f}.", "ok")

    def _on_pick(self, step_id: int):
        for i, s in enumerate(self.profile.steps):
            if s.id == step_id:
                self.table.setCurrentCell(i, 0)
                return

    def _on_row_edited(self):
        """A row widget already wrote its change into the Step. Never rebuild
        the table from here - that would destroy the widget the user is still
        holding (the old card grid's "can't edit and save" bug)."""
        self._redraw_markers()
        s = self._current()
        if s:
            self.canvas.highlight(s.id)

    def _on_move(self, step_id: int, nx: float, ny: float):
        """Marker dragged on the canvas."""
        s = self.profile.get(step_id)
        if not s:
            return
        s.x, s.y = round(nx, 4), round(ny, 4)
        for r in self._rows:
            if r.step.id == step_id:
                r.set_position(s.x, s.y)
                break
        self._status(f"Step #{step_id} moved to {s.x:.3f}, {s.y:.3f}.")

    def _redraw_markers(self):
        self.canvas.clear_markers()
        for s in self.profile.steps:
            self.canvas.add_marker(s.id, s.x, s.y, s.action == "place")

    # ---------------- steps table ----------------

    def _current(self) -> Step | None:
        i = self.table.currentRow()
        if 0 <= i < len(self.profile.steps):
            return self.profile.steps[i]
        return None

    def _refresh_list(self, keep_row: bool = False):
        """Rebuild every row widget. Structural changes only (add / delete /
        load) - an in-place edit must NOT come through here."""
        row = self.table.currentRow()
        self.table.blockSignals(True)
        self._rows = []
        self.table.setRowCount(len(self.profile.steps))
        slot_count = hotbar_slot_count(self.cfg)
        for i, s in enumerate(self.profile.steps):
            pos = QTableWidgetItem(str(i + 1))
            pos.setFlags(pos.flags() & ~Qt.ItemIsEditable)
            pos.setForeground(QColor(DIM))
            self.table.setItem(i, 0, pos)
            r = StepRow(s, slot_count, self._on_row_edited, self._on_row_edited)
            self.table.setCellWidget(i, 1, r.sp_x)
            self.table.setCellWidget(i, 2, r.sp_y)
            self.table.setCellWidget(i, 3, r.cb_unit)
            self.table.setCellWidget(i, 4, r.what_cell)
            self._rows.append(r)
        self.table.blockSignals(False)
        if keep_row and 0 <= row < self.table.rowCount():
            self.table.setCurrentCell(row, 0)

        n = len(self.profile.steps)
        if n == 0:
            text = "nothing added yet"
        else:
            text = f"{n} unit{'' if n == 1 else 's'}"
            if n >= MAX_STEPS - 10:
                text += f"  ({MAX_STEPS - n} left of {MAX_STEPS})"
        self.lbl_step_count.setText(text)
        self._update_hints()

    def _on_row_changed(self, row: int, _col: int, _prev_row: int, _prev_col: int):
        s = self._current()
        self.canvas.highlight(s.id if s else None)
        # Crosshair only while a click on the image would actually land
        # somewhere, i.e. while a row is selected.
        self.canvas.set_picking(s is not None)

    def _delete(self):
        s = self._current()
        if not s:
            return
        self.profile.remove_step(s.id)
        self._redraw_markers()
        self._refresh_list()

    def _on_name(self, text: str):
        self.profile.stage = text

    # ---------------- persistence ----------------

    def save_profile(self):
        if not self.profile.steps:
            QMessageBox.information(self, "Save", "Nothing to save yet.")
            return
        path = self.current_path
        if not path:
            safe = "".join(c if c.isalnum() else "_" for c in self.profile.stage)
            path, _ = QFileDialog.getSaveFileName(
                self, "Save profile", os.path.join("profiles", f"{safe}.json"),
                "JSON (*.json)")
            if not path:
                return
        self.profile.save(path)
        self.current_path = path
        self._status(f"Saved: {path}", "ok")

    def load_profile(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load profile", "profiles",
                                              "JSON (*.json)")
        if not path:
            return
        self.load_profile_path(path)

    def load_profile_path(self, path: str) -> bool:
        """Load one specific profile file. Split out of load_profile() so the
        dashboard's profile dropdown can load by name without a file dialog."""
        try:
            self.profile = StageProfile.load(path)
        except Exception as e:
            QMessageBox.critical(self, "Load", f"Failed: {e}")
            return False
        self.current_path = path
        self.stage_name.setText(self.profile.stage)
        if self.profile.reference_image and os.path.exists(self.profile.reference_image):
            self.canvas.set_image(self.profile.reference_image)
        self._redraw_markers()
        self._redraw_anchors()
        self._refresh_calib_labels()
        self._refresh_list()
        self._status(f"Loaded: {path}", "ok")
        return True
