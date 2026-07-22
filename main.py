"""Roblox TD Macro
Window manager, consolidated dashboard window, stage editor.
"""

import os
import re
import shutil
import sys
import time

import yaml

from core.window import RobloxWindow, enable_dpi_awareness

enable_dpi_awareness()

from PySide6.QtCore import QObject, QTimer, QLocale, Signal  # noqa: E402
from PySide6.QtGui import QFont  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from ui.main_window import MainWindow, BAR_H  # noqa: E402
from ui.panels import DASHBOARD_QSS  # noqa: E402
from ui.stage_editor import StageEditor, CameraTestThread, HAS_CAMERA  # noqa: E402
from data.stats import StatsDB  # noqa: E402
from core.hotkeys import GlobalHotkeys  # noqa: E402
from core.notify import send_test as send_webhook_test  # noqa: E402

try:
    from vision import capture as vcap
    HAS_VISION = True
except Exception:
    HAS_VISION = False

try:
    from core.executor import Executor
    HAS_EXECUTOR = True
except Exception:
    HAS_EXECUTOR = False


class HotkeyBridge(QObject):
    """RegisterHotKey fires on its own worker thread; these signals marshal
    the call back onto the Qt main thread instead of touching widgets directly."""
    start_hotkey = Signal()
    stop_hotkey = Signal()
    log_message = Signal(str)

def app_dir() -> str:
    """Writable folder next to the exe (frozen) or the source root (dev).
    Profiles, logs and config live here so they survive a rebuild."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def bundle_dir() -> str:
    """Read-only folder PyInstaller unpacks resources into."""
    return getattr(sys, "_MEIPASS", app_dir())


BASE = app_dir()


def load_config() -> dict:
    path = os.path.join(BASE, "config.yaml")
    if not os.path.exists(path):
        # Seed a config the first time. Two cases, tried in order:
        #  - frozen build: config.yaml is bundled next to the unpacked resources.
        #  - fresh clone (dev): config.yaml is gitignored (holds the webhook URL),
        #    so only config.example.yaml is on disk. Without this fallback run.bat
        #    on a clean checkout died with the startup-error box.
        for seed in (os.path.join(bundle_dir(), "config.yaml"),
                     os.path.join(BASE, "config.example.yaml"),
                     os.path.join(bundle_dir(), "config.example.yaml")):
            if os.path.exists(seed):
                shutil.copyfile(seed, path)
                break
        else:
            raise FileNotFoundError(
                f"config.yaml not found at {path}, and no config.example.yaml "
                "to seed it from")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_config(cfg: dict):
    """Full rewrite - only use this if you actually need to persist a change
    to a section save_config_value() can't reach. This strips every comment
    in the file (yaml.safe_dump has no idea they were ever there), so prefer
    save_config_value() for single settings - it edits the file in place."""
    path = os.path.join(BASE, "config.yaml")
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, default_flow_style=False, sort_keys=False)


def save_config_value(section: str, key: str, value):
    """Patch one `section.key: value` line in config.yaml in place, leaving
    every comment and every other line untouched. A prior version of the
    webhook Save button called save_config() (full rewrite) here and it
    silently wiped every comment in the file on first use."""
    path = os.path.join(BASE, "config.yaml")
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # Dump the BARE value (not wrapped in a {key: value} dict) so there's no
    # need to strip a "{...}" flow-mapping wrapper back off afterwards - a
    # naive split(":", 1) on the wrapped form broke on values that contain
    # their own colon (e.g. "https://..." webhook URLs), leaving a stray "}"
    # in the file and corrupting config.yaml on the very first real save.
    val_str = yaml.safe_dump(value, default_flow_style=True).split("\n", 1)[0]

    in_section = False
    key_line_idx = None
    insert_idx = len(lines)
    for i, line in enumerate(lines):
        if line.strip() == "" or line.lstrip().startswith("#"):
            continue
        if not line[0].isspace():
            if line.strip().rstrip(":") == section:
                in_section = True
                insert_idx = i + 1
                continue
            if in_section:
                break  # left the section without finding the key
            in_section = False
            continue
        if in_section:
            m = re.match(r"^(\s*)" + re.escape(key) + r"\s*:", line)
            if m:
                key_line_idx = i
                break
            insert_idx = i + 1

    if key_line_idx is not None:
        indent = re.match(r"^(\s*)", lines[key_line_idx]).group(1)
        comment = ""
        hash_idx = lines[key_line_idx].find("#")
        if hash_idx != -1:
            comment = "  " + lines[key_line_idx][hash_idx:].rstrip("\n")
        lines[key_line_idx] = f"{indent}{key}: {val_str}{comment}\n"
    else:
        lines.insert(insert_idx, f"  {key}: {val_str}\n")

    with open(path, "w", encoding="utf-8") as f:
        f.writelines(lines)


class App:
    def __init__(self):
        self.cfg = load_config()
        self.win = RobloxWindow(self.cfg)
        self.rect = None
        self.executor = None
        self._capture_obj = None   # lazily created shared Capture, see _shared_cap
        self.stats_db = StatsDB(os.path.join(BASE, self.cfg["paths"]["database"]))

        # Two separate windows: a narrow full-height dashboard docked to the
        # left edge, and the stage editor (opened on demand from its button).
        # Roblox is positioned in the space to the right of the dashboard on
        # attach, so nothing overlaps.
        self.window = MainWindow()
        self.editor = StageEditor(
            self.cfg,
            get_client_rect=lambda: self.rect,
            capture_fn=self._capture if HAS_VISION else None,
            focus_fn=self.win.focus,
            save_start_game_fn=self._save_start_game_btn,
            ocr_test_fn=self._test_ocr_read,
        )
        self._cam_thread = None
        self.window.webhook.set_webhook(self.cfg.get("discord", {}).get("webhook_url", ""))
        self.window.setup_run.set_profile(self.profile.stage, len(self.profile.steps))
        self.window.setup_run.set_press_start_game(
            bool(self.cfg.get("game", {}).get("press_start_game", False)))

        sr = self.window.setup_run
        sr.attach_requested.connect(self.attach)
        sr.camera_test_requested.connect(self.test_camera_view)
        sr.editor_requested.connect(self.open_editor)
        sr.load_requested.connect(self.load_profile)
        sr.profile_selected.connect(self.load_profile_named)
        sr.screenshot_requested.connect(self.take_screenshot)
        sr.run_requested.connect(self.run)
        sr.stop_requested.connect(self.stop)
        sr.exit_requested.connect(self.exit_app)
        sr.start_game_toggled.connect(self._set_press_start_game)
        self.window.webhook.webhook_save_requested.connect(self._save_webhook)
        self.window.webhook.webhook_test_requested.connect(self._test_webhook)
        self.window.readiness.recheck_requested.connect(self.refresh_readiness)
        self.window.readiness.guide_requested.connect(self.show_guide)

        # Dashboard: a short full-width bar docked to the bottom edge. The
        # editor is NOT shown at startup - it opens from the "Stage editor"
        # button. Roblox is positioned in the space above this bar on attach.
        screen = QApplication.primaryScreen().availableGeometry()
        self.window.setGeometry(screen.x(), screen.y() + screen.height() - BAR_H,
                                screen.width(), BAR_H)
        self.window.show()
        self._editor_positioned = False

        self.watchdog = QTimer()
        self.watchdog.timeout.connect(self._check_window)
        self.watchdog.start(2000)

        self.hotkey_bridge = HotkeyBridge()
        self.hotkey_bridge.start_hotkey.connect(self.run)
        self.hotkey_bridge.stop_hotkey.connect(self.stop)
        self.hotkey_bridge.log_message.connect(self.window.log.write)
        self.hotkeys = GlobalHotkeys(log=self.hotkey_bridge.log_message.emit)
        hk = self.cfg["hotkeys"]
        try:
            self.hotkeys.register(hk["start_stop"], self.hotkey_bridge.start_hotkey.emit)
            self.hotkeys.register(hk["emergency_stop"], self.hotkey_bridge.stop_hotkey.emit)
            self.hotkeys.start()
        except Exception as e:
            self.window.log.write(f"Global hotkeys unavailable: {e}")

        self.window.log.write("Ready. Click 'Attach + center window'.")
        self.refresh_profile_list()
        self.refresh_readiness()

    @property
    def profile(self):
        """Single source of truth: the profile the stage editor is holding.
        Avoids the old two-copy desync between the dashboard's idea of
        'current profile' and whatever the editor's own Load button last
        loaded."""
        return self.editor.profile

    def open_editor(self):
        if not self._editor_positioned:
            # First open: drop it near the top-left, above the bottom bar.
            self.editor.move(60, 40)
            self._editor_positioned = True
        self.editor.show()
        self.editor.raise_()
        self.editor.activateWindow()

    # ---------------- window ----------------

    def attach(self):
        hwnd = self.win.find()
        if not hwnd:
            self.window.setup_run.set_attached(False)
            self.window.log.write("Roblox window not found. Is the game running?")
            QMessageBox.warning(None, "Attach",
                                "Roblox window not found.\nLaunch the game first.")
            return
        # Position Roblox in the space above the bottom-docked dashboard bar.
        self.rect = self.win.layout(bottom_bound=BAR_H + 10)
        if self.rect:
            self.window.setup_run.set_attached(True, f"{self.rect.w}x{self.rect.h}")
            want_w = self.cfg["window"]["client_width"]
            want_h = self.cfg["window"]["client_height"]
            if (self.rect.w, self.rect.h) != (want_w, want_h):
                self.window.log.write(
                    f"WARNING: attached, but the client area is "
                    f"{self.rect.w}x{self.rect.h}, not the requested "
                    f"{want_w}x{want_h} - the resize didn't take. Likely "
                    f"causes: Roblox is in fullscreen/borderless mode (switch "
                    f"it to windowed in Settings), or Windows display scaling "
                    f"is not 100% (open_items #2 in HANDOFF.md). Coordinates "
                    f"will be wrong until this is fixed.")
            else:
                self.window.log.write(
                    f"Attached. Client {self.rect.w}x{self.rect.h} at "
                    f"({self.rect.x}, {self.rect.y})")
        self.refresh_readiness()

    def _check_window(self):
        if not self.rect:
            return
        if not self.win.is_alive():
            self.rect = None
            self.window.setup_run.set_attached(False)
            self.window.log.write("Roblox window closed.")
            return
        cur = self.win.client_rect()
        if not cur:
            return
        # DPI-rounding / DWM shadow-margin noise can shift the reported rect
        # by a pixel or two between polls with the window sitting still -
        # only treat it as a real move (and log it) past a small tolerance,
        # otherwise just absorb the jitter silently.
        delta = max(abs(cur.x - self.rect.x), abs(cur.y - self.rect.y),
                   abs(cur.w - self.rect.w), abs(cur.h - self.rect.h))
        if delta > 3:
            self.rect = cur
            self.window.log.write("Roblox window moved.")
        elif (cur.x, cur.y, cur.w, cur.h) != self.rect.as_tuple():
            self.rect = cur

    # ---------------- camera test ----------------

    def test_camera_view(self):
        if not HAS_CAMERA:
            self.window.log.write("Camera test unavailable - core input/camera modules missing.")
            return
        if not self.rect:
            self.window.log.write("Attach the Roblox window first.")
            return
        self.win.focus()  # SendInput goes to whatever window has OS focus
        self.window.setup_run.set_camera_testing(True)
        self.window.log.write("Testing camera view - the camera will pitch down briefly...")
        self._cam_thread = CameraTestThread(self.cfg, self.rect)
        self._cam_thread.done.connect(self._on_camera_test_done)
        self._cam_thread.failed.connect(self._on_camera_test_failed)
        self._cam_thread.start()

    def _on_camera_test_done(self):
        self.window.setup_run.set_camera_testing(False)
        self.window.log.write("Camera view set - zoomed all the way out.")
        self._report_reference_score()
        self.refresh_readiness()

    def _report_reference_score(self):
        """Print how well the camera we can SEE is correct scores against the
        stage reference. That number is the only sane way to pick
        vision.ref_match_threshold - a run refuses to place anything when it
        falls short (HANDOFF 2.28), and guessing the threshold either blocks
        every run or lets a bad camera through."""
        ref = self.profile.reference_image
        if not (HAS_VISION and self.rect and ref and os.path.exists(ref)):
            self.window.log.write("Open the stage editor and Capture ref now.")
            return
        try:
            score = vcap.similarity(self._shared_cap().grab(self.rect), vcap.load(ref))
        except Exception as e:
            self.window.log.write(f"Couldn't score the reference match: {e}")
            return
        need = self.cfg.get("vision", {}).get("ref_match_threshold", 0.65)
        if score >= need:
            self.window.log.write(
                f"Reference match: {score:.3f} (threshold {need}) - a run "
                "would accept this camera.")
        else:
            self.window.log.write(
                f"Reference match: {score:.3f}, BELOW the threshold {need} - a "
                "run would refuse to place anything. If the view looks right, "
                f"set vision.ref_match_threshold a little under {score:.3f}; "
                "if it doesn't, re-capture the reference.")

    def _on_camera_test_failed(self, msg: str):
        self.window.setup_run.set_camera_testing(False)
        self.window.log.write(f"Camera test failed: {msg}")

    # ---------------- capture ----------------

    def _shared_cap(self):
        """One reused Capture for all GUI-thread grabs (Test camera view /
        Screenshot / Test read). Each vcap.Capture() opens an mss handle, so
        making a fresh one per button click leaked a handle every time and
        slowed the app over a calibration session (RELEASE_REVIEW 1.4). The
        executor keeps its OWN Capture on the worker thread - mss handles are
        per-thread - so this shared one is for the GUI thread only."""
        if self._capture_obj is None:
            self._capture_obj = vcap.Capture()
        return self._capture_obj

    def _capture(self, rect, path):
        if not HAS_VISION:
            raise RuntimeError("opencv/mss not installed")
        img = self._shared_cap().grab(rect)
        vcap.save(img, path)

    def take_screenshot(self):
        if not HAS_VISION:
            self.window.log.write("Screenshot unavailable - opencv/mss not installed.")
            return
        if not self.rect:
            self.window.log.write("Attach the Roblox window first.")
            return
        out_dir = os.path.join(BASE, self.cfg["paths"].get("manual_screenshots", "screenshots"))
        os.makedirs(out_dir, exist_ok=True)
        safe = "".join(c if c.isalnum() else "_" for c in self.profile.stage)
        path = os.path.join(out_dir, f"{safe}_{time.strftime('%Y%m%d_%H%M%S')}.png")
        try:
            self._capture(self.rect, path)
            self.window.log.write(f"Screenshot saved: {path}")
        except Exception as e:
            self.window.log.write(f"Screenshot failed: {e}")

    # ---------------- profile ----------------

    def _profiles_dir(self) -> str:
        return os.path.join(BASE, self.cfg["paths"].get("profiles", "profiles"))

    def refresh_profile_list(self):
        """Repopulate the dashboard's profile dropdown from the profiles
        folder. The panel deliberately enumerates nothing itself - it only
        displays what it's given."""
        try:
            names = sorted(os.path.splitext(f)[0]
                           for f in os.listdir(self._profiles_dir())
                           if f.lower().endswith(".json"))
        except OSError:
            names = []
        self.window.setup_run.set_profile_list(names)
        cur = getattr(self.editor, "current_path", None)
        if cur:
            self.window.setup_run.set_current_profile(
                os.path.splitext(os.path.basename(cur))[0])

    def load_profile_named(self, name: str):
        """Load by name from the dropdown - no file dialog."""
        path = os.path.join(self._profiles_dir(), f"{name}.json")
        if not os.path.exists(path):
            self.window.log.write(f"Profile '{name}' no longer exists.")
            self.refresh_profile_list()
            return
        if not self.editor.load_profile_path(path):
            self.window.log.write(f"Failed to load profile '{name}'.")
            return
        self._after_profile_change()
        self.window.log.write(
            f"Loaded '{name}' ({len(self.profile.steps)} step(s)).")

    def load_profile(self):
        self.editor.load_profile()
        self._after_profile_change()

    def _after_profile_change(self):
        self.window.setup_run.set_profile(self.profile.stage, len(self.profile.steps))
        self.window.stats.set_totals(*self.stats_db.summary(self.profile.stage))
        self.refresh_profile_list()
        self.refresh_readiness()

    def _set_press_start_game(self, on: bool):
        # Executor shares this exact cfg dict, so it picks the change up live.
        self.cfg.setdefault("game", {})["press_start_game"] = on
        self.window.log.write(
            f"Press Start Game at run start: {'ON' if on else 'OFF'}")

    # Which OCR reader the Calibrate tab's "Test read" button uses, keyed by
    # anchor name - each region needs a different parse (see core/ocr.py):
    # wave is "<current> / <total>" (leading number only), upgrade level is
    # "Upgrade N/M" (both numbers), priority is a word, cash is a plain int.
    _OCR_TEST_READERS = {
        "wave_roi": "read_leading_int",
        "upgrade_level_roi": "read_fraction",
        "priority_label_roi": "read_word",
    }

    def _test_ocr_read(self, roi, name: str = "cash_roi"):
        """Grab the given HUD region live and report what the OCR reads, so the
        user can verify a box is placed right. Returns (value, error); value's
        type depends on the anchor (int, (int,int), or str). Runs on the GUI
        thread (a manual one-shot, not the executor's polling loop) so it's
        fine to be a bit slow."""
        from core import ocr
        if not self.rect:
            return None, "Attach the Roblox window first."
        if not HAS_VISION:
            return None, "opencv/mss not installed."
        ocr.configure(self.cfg.get("vision", {}).get("tesseract_cmd"))
        if not ocr.HAS_TESSERACT:
            return None, "Tesseract not installed - install it, then Re-check."
        self.win.focus()  # the ROI is captured from screen coords behind us
        reader = getattr(ocr, self._OCR_TEST_READERS.get(name, "read_int"))
        try:
            img = self._shared_cap().grab_roi(self.rect, roi)
            val = reader(img)
            if val == (None, None):
                val = None
            return val, None
        except Exception as e:
            return None, str(e)

    def _save_start_game_btn(self, xy):
        """The Calibrate tab sets game.start_game_btn by clicking the image;
        persist it to config.yaml right away (the other anchors save with the
        profile). The executor shares this cfg dict, so the change is live."""
        try:
            save_config_value("game", "start_game_btn", xy)
            self.window.log.write(f"Start Game button position saved: {xy}")
        except Exception as e:
            self.window.log.write(f"Failed to save Start Game position: {e}")

    # ---------------- webhook ----------------

    def _save_webhook(self, url: str):
        self.cfg.setdefault("discord", {})["webhook_url"] = url
        try:
            save_config_value("discord", "webhook_url", url)
            self.window.log.write("Webhook URL saved to config.yaml.")
        except Exception as e:
            self.window.log.write(f"Failed to save webhook URL: {e}")

    def _test_webhook(self, url: str):
        send_webhook_test(url, log=self.window.log.write)

    # ---------------- readiness ----------------

    def refresh_readiness(self):
        self.window.readiness.set_checks(self._compute_readiness())

    def show_guide(self):
        """Ordered first-time setup walkthrough. The Readiness checklist tells
        you WHAT is missing; this tells you the ORDER to do it in."""
        QMessageBox.information(
            None, "How to set up TD Macro",
            "First-time setup, in order:\n\n"
            "1. Launch Roblox and enter the game to the stage you want to farm.\n\n"
            "2. In Roblox Settings, set the display to WINDOWED mode and set "
            "Windows display scaling to 100% (Settings > Display > Scale). The "
            "macro clicks fixed positions - fullscreen/scaling breaks them.\n\n"
            "3. Click 'Attach + center window'. The Readiness panel should turn "
            "'Roblox attached' green at 1280x720.\n\n"
            "4. Click 'Test camera view' - Roblox zooms to the top-down angle.\n\n"
            "5. Click 'Stage editor', then 'Capture ref' to snapshot the stage.\n\n"
            "6. In the editor's 'Calibrate' tab, click 'Set point' and click each "
            "button on the image (upgrade / sell / confirm / priority / Start "
            "Game); click 'Set box' and drag over the cash number, wave number, "
            "and the area where the Win/Loss banner appears.\n\n"
            "7. On the 'Steps' tab, press '+ Add step' for each unit, click the "
            "image where it should go, then pick its Unit number and what to do "
            "(Place / Upgrade to N / Upgrade to max). Click 'Save'.\n\n"
            "8. (Optional) Install Tesseract-OCR so cash/wave waits work: "
            "https://github.com/UB-Mannheim/tesseract/wiki - if it's not on "
            "PATH, put its path in config.yaml under vision.tesseract_cmd.\n\n"
            "9. Back on the dashboard, click 'Re-check'. Fix any red items, then "
            "press Start (F9). F12 is emergency stop.")

    def _anchors_calibrated(self) -> bool:
        """Heuristic: the profile's anchors differ from any shipped default,
        i.e. the user actually set something in the Calibrate tab."""
        from data.profile import is_default_anchors
        return not is_default_anchors(self.profile.ui_anchors)

    def _compute_readiness(self) -> list:
        """(label, level, detail) rows for the dashboard checklist.
        level: 'ok' (green) | 'warn' (yellow, run works but limited) |
        'bad' (red, fix before a real run)."""
        checks = []

        if not self.rect:
            checks.append(("Roblox attached", "bad",
                           "Launch the game, then click 'Attach + center window'."))
        else:
            want_w = self.cfg["window"]["client_width"]
            want_h = self.cfg["window"]["client_height"]
            if (self.rect.w, self.rect.h) != (want_w, want_h):
                checks.append(("Roblox attached", "warn",
                               f"Size {self.rect.w}x{self.rect.h}, want {want_w}x{want_h}. "
                               "Use windowed mode + 100% display scaling."))
            else:
                checks.append(("Roblox attached", "ok", f"{self.rect.w}x{self.rect.h}."))

        n = len(self.profile.steps)
        if n == 0:
            checks.append(("Profile has steps", "bad",
                           "Open the stage editor and add steps."))
        else:
            checks.append(("Profile has steps", "ok", f"{n} step(s) loaded."))

        # Slots are CLICKED now, not typed (HANDOFF 2.22), so a slot number
        # the configured bar doesn't cover has no position at all - the step
        # is skipped at run time. Worth catching here rather than in the log.
        hb = self.cfg.get("game", {}).get("hotbar", {}) or {}
        slot_count = len(hb.get("slots") or []) or int(hb.get("slot_count", 6))
        used = sorted({s.slot for s in self.profile.steps
                       if s.action in ("place", "ability")})
        over = [s for s in used if not 1 <= s <= slot_count]
        if not used:
            pass
        elif over:
            checks.append(("Hotbar slots", "bad",
                           f"Step(s) use slot {', '.join(map(str, over))} but "
                           f"game.hotbar covers {slot_count}. Set slot_count to "
                           "your loadout size in config.yaml."))
        else:
            checks.append(("Hotbar slots", "ok",
                           f"Using slot(s) {', '.join(map(str, used))} of {slot_count}."))

        ref = self.profile.reference_image
        if ref and os.path.exists(ref):
            checks.append(("Reference image", "ok", os.path.basename(ref)))
        else:
            checks.append(("Reference image", "bad",
                           "Attach, Test camera view, then Capture ref in the editor."))

        if self._anchors_calibrated():
            checks.append(("Buttons/HUD calibrated", "ok", "Custom positions set."))
        else:
            checks.append(("Buttons/HUD calibrated", "warn",
                           "Using default guesses - use the editor's Calibrate tab."))

        tdir = os.path.join(BASE, "vision", "templates")
        has_win = os.path.exists(os.path.join(tdir, "victory.png"))
        if has_win and os.path.exists(os.path.join(tdir, "defeat.png")):
            checks.append(("Win/Loss detection", "ok", "victory.png + defeat.png found."))
        elif has_win:
            # victory.png alone is enough on the result screen: no ribbon means
            # a loss. defeat.png only sharpens the in-match banner check.
            checks.append(("Win/Loss detection", "ok",
                           "victory.png found - losses inferred on the result screen."))
        else:
            checks.append(("Win/Loss detection", "bad",
                           "victory.png missing. The colour fallback can't read this "
                           "game (its victory ribbon is blue, not green)."))

        missing = [n for n in ("reward_close.png", "result_repeat.png")
                   if not os.path.exists(os.path.join(tdir, n))]
        if not missing:
            checks.append(("Auto-repeat loop", "ok",
                           "Clicks through the item screens, then Repeat Stage."))
        else:
            checks.append(("Auto-repeat loop", "warn",
                           f"{', '.join(missing)} missing - the run won't get past "
                           "the post-match screens on its own."))

        from core import ocr
        if ocr.tesseract_ready(self.cfg.get("vision", {}).get("tesseract_cmd")):
            checks.append(("Tesseract OCR", "ok", "Engine detected."))
        else:
            checks.append(("Tesseract OCR", "warn",
                           "Not installed - cash/wave waits time out (delay waits work)."))

        return checks

    # ---------------- run ----------------

    def run(self):
        self.refresh_readiness()
        if self.executor is not None:
            self.window.log.write("Already running.")
            return
        if not HAS_EXECUTOR:
            self.window.log.write("Executor unavailable - check PySide6/opencv/mss install.")
            return
        if not self.rect:
            self.window.log.write("Attach the Roblox window first.")
            return
        if not self.profile.steps:
            self.window.log.write("Add steps in the stage editor or load a profile first.")
            return

        results_dir = os.path.join(BASE, self.cfg["paths"].get("screenshots", "logs/screenshots"))
        stats_path = os.path.join(BASE, self.cfg["paths"]["database"])
        templates_dir = os.path.join(BASE, "vision", "templates")
        # loops=0 -> infinite. A run ends when the user says so (Stop / F12),
        # never on its own count.
        self.executor = Executor(self.cfg, self.win, self.profile, 0,
                                 results_dir, stats_path, templates_dir)
        self.executor.log.connect(self.window.log.write)
        self.executor.state.connect(self.window.stats.set_state)
        self.executor.progress.connect(self.window.stats.set_progress)
        self.executor.result.connect(self._on_result)
        self.executor.finished.connect(self._on_executor_finished)

        self.window.setup_run.set_running(True)
        self.window.stats.set_state("RUNNING")
        self.window.log.write(f"Starting '{self.profile.stage}' - looping until "
                              "you press Stop (F12).")
        self.executor.start()

    def stop(self):
        if self.executor is not None:
            self.window.log.write("Stop requested - finishing current step...")
            self.executor.request_stop()
        else:
            self.window.log.write("Not running.")

    def _on_result(self, won: bool):
        self.window.stats.record(won)
        self.window.stats.set_totals(*self.stats_db.summary(self.profile.stage))

    def _on_executor_finished(self):
        self.executor = None
        self.window.setup_run.set_running(False)
        self.window.stats.set_state("IDLE")

    # ---------------- exit ----------------

    def exit_app(self):
        if self.executor is not None:
            self.window.log.write("Exiting - stopping the running macro first...")
            self.executor.request_stop()
        QApplication.instance().quit()

    # ---------------- shutdown ----------------

    def shutdown(self):
        self.hotkeys.stop()
        if self.executor is not None:
            self.executor.request_stop()
            self.executor.wait(3000)


def main():
    os.chdir(BASE)
    for d in ("profiles", "logs", "logs/screenshots", "data", "vision/templates", "screenshots"):
        os.makedirs(os.path.join(BASE, d), exist_ok=True)

    app = QApplication(sys.argv)
    # Force English/US so QSpinBox etc. render Arabic numerals (0-9), not the
    # system-locale digits (e.g. Thai ๐-๙), and pin a clean Latin UI font.
    QLocale.setDefault(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))
    app.setFont(QFont("Segoe UI", 9))
    # App-wide so the QMessageBox dialogs below (attach warnings, the Guide,
    # the startup error) and Qt's own file dialogs inherit the dark theme -
    # parented to None they'd otherwise pop as bright white boxes. Widget-level
    # sheets still win, so the editor's own copy is unaffected.
    app.setStyleSheet(DASHBOARD_QSS)
    try:
        gui = App()
    except Exception as e:
        # Without this a frozen build just dies silently with no console.
        import traceback
        QMessageBox.critical(None, "Startup failed",
                             f"{e}\n\n{traceback.format_exc()}")
        sys.exit(1)
    app.aboutToQuit.connect(gui.shutdown)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
