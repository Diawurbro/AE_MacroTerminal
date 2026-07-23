"""Recording a finished loop: screenshot, SQLite row, Discord notification."""

import os
import time

from core.notify import send_result
from vision import capture as vcap


class RunRecorder:
    def __init__(self, ctx, stats, results_dir: str, on_result=None):
        self.ctx = ctx
        self.stats = stats
        self.results_dir = results_dir
        # Called with True/False on a decided win/loss so the GUI can update
        # its session tally. A callback rather than a Qt signal so this class
        # stays usable without Qt.
        self.on_result = on_result

    def record(self, loop_no: int, outcome: str, started: float, rect):
        shot_path = self._screenshot(outcome, started, rect)
        self.stats.record(self.ctx.profile.stage, outcome, loop_no, started, shot_path)
        duration = time.time() - started
        self.ctx.log(f"Round {loop_no} result: {outcome} ({duration:.0f}s)")

        # 'abort' is neither a win nor a loss - recorded for history, but it
        # must not touch the loss streak or fire a notification.
        if outcome not in ("win", "loss"):
            return

        won = outcome == "win"
        if self.on_result:
            self.on_result(won)
        self._notify(won, loop_no, duration, shot_path)

    def _screenshot(self, outcome: str, started: float, rect) -> str | None:
        try:
            frame = self.ctx.cap.grab(rect)
            safe = "".join(c if c.isalnum() else "_" for c in self.ctx.profile.stage)
            os.makedirs(self.results_dir, exist_ok=True)
            path = os.path.join(self.results_dir,
                                f"{safe}_{int(started)}_{outcome}.png")
            vcap.save(frame, path)
            return path
        except Exception as e:
            self.ctx.log(f"Couldn't save the screenshot: {e}")
            return None

    def _notify(self, won: bool, loop_no: int, duration: float, shot_path):
        streak = self.stats.loss_streak(self.ctx.profile.stage)
        d = self.ctx.cfg.get("discord", {})
        send_result(
            d.get("webhook_url", ""), self.ctx.profile.stage, won, loop_no,
            duration, screenshot_path=shot_path, loss_streak=streak,
            ping_streak_at=d.get("ping_on_fail_streak", 3), log=self.ctx.log,
        )
