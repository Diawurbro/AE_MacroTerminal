"""Executor: the QThread that drives a run.

Orchestration only. Each phase lives in its own class and this coordinates
them - the shape of a loop should be readable straight off _run_once():

    StageSetup   get the stage into the state the profile's coordinates assume
    StepRunner   satisfy each step's precondition, dispatch to its action
    MatchFlow    play the match out, read the result, hit Repeat
    RunRecorder  screenshot + SQLite + Discord

Only ever talk to the GUI through signals.
"""

import time

from PySide6.QtCore import QThread, Signal

from core import ocr
from core.camera import CameraNormalizer
from core.match_flow import MatchFlow
from core.run_context import RunContext, StopRequested
from core.run_recorder import RunRecorder
from core.stage_setup import StageSetup
from core.step_runner import StepRunner
from core.unit_panel import UnitPanel
from data.stats import StatsDB
from vision import capture as vcap
from vision.game_state import GameStateDetector
from vision.result_detector import ResultDetector
from vision.reward_screen import RewardScreenDetector

# Re-exported: this was defined here before the split, and it reads more
# naturally as core.executor.StopRequested from the outside.
__all__ = ["Executor", "StopRequested"]


class Executor(QThread):
    log = Signal(str)
    state = Signal(str)
    progress = Signal(int, int, int)   # loop_no, step, total
    result = Signal(bool)              # True = win

    def __init__(self, cfg, win, profile, loops: int, results_dir: str, stats_path: str,
                 templates_dir: str | None = None):
        super().__init__()
        self.cfg = cfg
        self.win = win
        self.profile = profile
        self.loops = loops if loops > 0 else -1
        self.results_dir = results_dir
        self.stats_path = stats_path
        self.templates_dir = templates_dir
        self._stop = False

    def request_stop(self):
        self._stop = True

    def _check_stop(self):
        if self._stop:
            raise StopRequested()

    # ---------------- thread entry ----------------

    def _build(self):
        """Assemble the run's collaborators. Called on the worker thread, not
        in __init__ - InputDriver holds ctypes handles that must be created on
        the thread that uses them."""
        from core.input_driver import InputDriver

        self.drv = InputDriver(self.cfg)
        w = self.cfg["window"]
        self.cap = vcap.Capture(ref_size=(w["client_width"], w["client_height"]))
        self.ctx = RunContext(self.cfg, self.profile, self.drv, self.cap,
                              self.log.emit, self._check_stop)

        detector = ResultDetector(self.cfg, self.templates_dir, log=self.log.emit)
        state_detector = GameStateDetector(self.templates_dir, log=self.log.emit)
        rewards = RewardScreenDetector(self.cfg, self.templates_dir, log=self.log.emit)

        self.panel = UnitPanel(self.ctx)
        self.setup = StageSetup(self.ctx, CameraNormalizer(self.drv, self.cfg),
                                state_detector, self.panel)
        self.steps = StepRunner(self.ctx, self.panel)
        self.match = MatchFlow(self.ctx, rewards, detector)
        self.recorder = RunRecorder(self.ctx, StatsDB(self.stats_path),
                                    self.results_dir, on_result=self.result.emit)

        # Warm the OCR engine on the worker thread, before any step runs -
        # the first load costs ~1s and would otherwise land mid-placement.
        if not ocr.engine_ready():
            self.log.emit("Text reading (OCR) is unavailable — cash/wave waits "
                          "and upgrade-to-max detection won't work. Reinstall "
                          "dependencies to enable them.")

    def run(self):
        self._build()
        loop_no = 0
        aborts = 0
        try:
            while self.loops < 0 or loop_no < self.loops:
                self._check_stop()
                loop_no += 1
                if self._run_once(loop_no):
                    aborts = 0
                    continue
                # A loop that never got as far as playing usually means
                # something the macro can't fix by trying again (the camera
                # won't normalize, the stage never loaded). Retrying forever
                # would just be a very patient way of doing nothing.
                aborts += 1
                limit = self.ctx.execution("max_consecutive_aborts", 3)
                if aborts >= limit:
                    self.log.emit(f"Stopping — {aborts} rounds in a row ended "
                                  "before any step ran. Fix the issues above, "
                                  "then start again.")
                    break
        except StopRequested:
            self.log.emit("Stopped.")
        except Exception as e:
            self.log.emit(f"Run error: {e}")
        finally:
            self.state.emit("IDLE")

    # ---------------- window helpers ----------------

    def _rect(self):
        r = self.win.client_rect()
        if not r:
            raise RuntimeError("Roblox window lost")
        return r

    def _ensure_foreground(self):
        """Abort rather than keep clicking if Roblox isn't frontmost - input
        goes to whatever window has focus, so a background run would be
        typing into someone else's application."""
        if not self.win.is_alive():
            raise RuntimeError("Roblox window closed")
        if not self.win.is_foreground():
            self.win.focus()
            time.sleep(0.2)
            if not self.win.is_foreground():
                raise RuntimeError("Roblox window lost foreground")

    # ---------------- one loop ----------------

    def _run_once(self, loop_no: int) -> bool:
        """Play one match. Returns False if it bailed before running a single
        step - see the abort counter in run()."""
        started = time.time()
        self.state.emit("RUNNING")
        self.log.emit(f"── Round {loop_no} ──")
        self._ensure_foreground()
        rect = self._rect()

        def record(outcome):
            self.recorder.record(loop_no, outcome, started, rect)

        if not self.setup.wait_for_in_stage(rect):
            self.log.emit("Never reached the stage — skipping this round.")
            record("abort")
            return False

        self.setup.teleport_to_spawn(rect)
        self._check_stop()

        # Full normalize+verify EVERY round, entry or repeat - no shortcut that
        # skips it when the camera "looked fine" last time. Repeat Stage
        # respawns the character and Roblox resets the camera on respawn, so
        # a round that trusted the previous camera ran on the default angled
        # view and placed nothing where it thought (HANDOFF 2.39). Clamp-based
        # normalize is idempotent - running it again when the camera is
        # already correct lands in the same place - so doing it unconditionally
        # costs a little time but makes every round follow the identical
        # sequence instead of branching on what the last round happened to do.
        camera_ok = self.setup.normalize_and_verify(rect)
        if not camera_ok:
            if self.ctx.execution("abort_on_ref_mismatch", True):
                self.log.emit(
                    "Skipping this round — the camera doesn't match, so units "
                    "would land in the wrong place. Fix the camera, re-capture "
                    "the reference, or lower the match threshold if the score "
                    "above looks right for a correct camera.")
                record("abort")
                return False
            self.log.emit("Warning: the camera doesn't match, but 'skip on "
                          "mismatch' is off — continuing anyway; placements "
                          "may be wrong.")

        self._check_stop()
        self.setup.press_start_game(rect)
        # After Start Game and before any step: the one moment in a loop when
        # nothing can possibly be selected, which is what makes it a valid
        # "empty panel" reference for every placement check (2.30).
        self.setup.capture_panel_baseline(rect)

        total = len(self.profile.steps)
        for i, step in enumerate(self.profile.steps, start=1):
            self._check_stop()
            self._ensure_foreground()
            self.progress.emit(loop_no, i, total)
            self.steps.run(step, rect)

        self.match.run_out(rect, record)
        return True
