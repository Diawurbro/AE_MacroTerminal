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
        # Set True once the camera has been normalized+verified for this run.
        # With execution.normalize_camera_once on, the camera is set a single
        # time on stage entry and then trusted for every repeat - re-running
        # the flaky normalize sequence each round is what was corrupting a
        # good camera and tripping the reference-mismatch abort (see _run_once).
        self._camera_set = False

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
        self.cap = vcap.Capture()
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

        ocr.configure(self.cfg.get("vision", {}).get("tesseract_cmd"))
        if not ocr.HAS_TESSERACT:
            self.log.emit("pytesseract/Tesseract not available - cash/wave "
                          "waits will time out. Install Tesseract-OCR.")

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
                    self.log.emit(f"Stopping: {aborts} loops in a row ended "
                                  "before any step ran. Fix what the messages "
                                  "above report, then start again.")
                    break
        except StopRequested:
            self.log.emit("Stopped.")
        except Exception as e:
            self.log.emit(f"Executor error: {e}")
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
        self.log.emit(f"--- Loop {loop_no} start ---")
        self._ensure_foreground()
        rect = self._rect()

        def record(outcome):
            self.recorder.record(loop_no, outcome, started, rect)

        if not self.setup.wait_for_in_stage(rect):
            self.log.emit("Never reached the in-stage state - skipping this loop.")
            record("abort")
            return False

        self.setup.teleport_to_spawn(rect)
        self._check_stop()

        # Normalize the camera ONCE per run (on stage entry), then reuse it for
        # every repeat. Repeat Stage restarts the same stage without moving the
        # camera and nothing here moves the character, so the top-down view set
        # on entry holds - and re-running the normalize each round only risks
        # its known flakiness corrupting a good camera, then failing the verify
        # and aborting the loop. Set execution.normalize_camera_once false to go
        # back to per-round normalize+verify. `_camera_set` (not loop_no) gates
        # it, so a first attempt that aborts still retries on the next loop.
        normalize_once = self.ctx.execution("normalize_camera_once", True)
        if not self._camera_set or not normalize_once:
            if self.setup.normalize_and_verify(rect):
                self._camera_set = True
            elif self.ctx.execution("abort_on_ref_mismatch", True):
                self.log.emit(
                    "Skipping this loop - running steps against a camera that "
                    "doesn't match the reference places units in the wrong "
                    "spots (often at the far edge of the map). Fix the camera, "
                    "re-capture the reference, or lower "
                    "vision.ref_match_threshold if the score above looks "
                    "right for a correct camera.")
                record("abort")
                return False
            else:
                self.log.emit("WARNING: camera/reference mismatch and "
                              "execution.abort_on_ref_mismatch is off - "
                              "continuing, but every step coordinate is suspect.")
        else:
            self.log.emit("Reusing the camera set on stage entry - not "
                          "re-normalizing (execution.normalize_camera_once).")

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
