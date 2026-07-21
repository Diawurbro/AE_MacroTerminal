"""Everything between the last step and the next loop: waiting the match
out, clicking through the post-match reward screens, reading the result, and
hitting Repeat Stage.

Ordering matters here and is easy to get wrong - see MatchFlow.run_out().
"""


class MatchFlow:
    #: fallbacks for anchors added later than the profiles on disk, so an
    #: older saved profile still finds these regions.
    REWARD_STRIP = [0.36, 0.90, 0.64, 0.96]
    RESULT_SCREEN = [0.15, 0.70, 0.70, 0.88]
    RESULT_BANNER = [0.30, 0.35, 0.70, 0.65]

    def __init__(self, ctx, rewards, result_detector):
        self.ctx = ctx
        self.rewards = rewards
        self.detector = result_detector

    # ---------------- detection helpers ----------------

    def _reward_strip(self, rect):
        """(showing, score) for the post-match "(Click anywhere to close)"
        caption."""
        img = self.ctx.grab_anchor(rect, "reward_strip_roi", self.REWARD_STRIP)
        return self.rewards.present(img)

    def _result_screen(self, rect):
        """(showing, score) for the result screen, matched on its Repeat
        Stage button."""
        img = self.ctx.grab_anchor(rect, "result_screen_roi", self.RESULT_SCREEN)
        return self.rewards.result_screen(img)

    # ---------------- phases ----------------

    def wait_for_match_end(self, rect):
        """Wait for the match to finish; returns 'win'/'loss' if the in-match
        banner check managed to classify it, else None.

        Watches for the win/loss banner AND for the reward screens, because
        the reward sequence is itself proof the match is over. Without that
        second signal, a game whose outcome only appears on the post-reward
        result screen would sit here for the full result_timeout_s (15 min by
        default) every single loop."""
        result_roi = self.ctx.anchor("result_roi", self.RESULT_BANNER)
        state = {"last": None}

        def check():
            frame = self.ctx.cap.grab(rect)
            cls = self.detector.classify_frame(frame, result_roi)
            # Two consecutive agreeing frames before trusting a banner read -
            # a single frame can catch a transition or an animation.
            if cls and cls == state["last"]:
                return cls
            state["last"] = cls
            if self.rewards.available():
                showing, score = self._reward_strip(rect)
                if showing:
                    self.ctx.log(f"Match over - reward screens are up "
                                 f"(match {score:.2f}).")
                    return "rewards"
            return None

        got = self.ctx.poll_until(check, self.ctx.execution("result_timeout_s", 900))
        if got is None:
            self.ctx.log("Timed out waiting for the match to end.")
            return None
        return None if got == "rewards" else got

    def clear_reward_screens(self, rect) -> bool:
        """Click through the post-match item screens until the result screen
        appears. Returns True once the caption is gone.

        Checks BEFORE every click and never after, so a click can only ever
        land while a reward screen is still up - the result screen's "Back to
        lobby" button is one stray click away otherwise. This is also why it
        detects rather than counting a fixed number of screens: the count
        varies per run (HANDOFF 2.16)."""
        if not self.rewards.available():
            return True
        cap = self.ctx.execution("max_reward_clicks", 15)
        gap_ms = self.ctx.execution("reward_click_interval_ms", 700)
        point = self.ctx.game("reward_click_point", [0.5, 0.62])
        clicks = 0
        for _ in range(cap):
            self.ctx.check_stop()
            showing, _ = self._reward_strip(rect)
            if not showing:
                if clicks:
                    self.ctx.log(f"Reward screens cleared after {clicks} click(s).")
                return True
            cx, cy = rect.to_screen(*point)
            self.ctx.drv.click(cx, cy)
            clicks += 1
            self.ctx.drv.wait(gap_ms)
        self.ctx.log(f"Reward screens still showing after {cap} clicks "
                     "(execution.max_reward_clicks) - giving up on this loop.")
        return False

    def read_result_screen(self, rect):
        """Wait for the post-reward result screen and classify it.

        Detected by its Repeat Stage button rather than the Victory ribbon,
        because that button is present whether you won or lost - so a loss is
        still recognised, and still gets repeated."""
        if not self.rewards.repeat_available():
            return None

        got = self.ctx.poll_until(
            lambda: self._result_screen(rect)[0] or None,
            self.ctx.execution("result_screen_timeout_s", 60))
        if not got:
            self.ctx.log("Result screen never appeared - recording from the "
                         "in-match check instead.")
            return None
        outcome = self.detector.classify_result_screen(self.ctx.cap.grab(rect))
        self.ctx.log(f"Result screen up - {outcome}.")
        return None if outcome == "unknown" else outcome

    def click_repeat(self, rect) -> bool:
        """Click Repeat Stage to start the next run.

        Re-confirms the result screen immediately before clicking: this button
        sits beside "Back to lobby", so clicking blind on a mistimed frame is
        how a run ends up out of the stage entirely."""
        if not self.ctx.execution("auto_repeat", True):
            return False
        if not self.rewards.repeat_available():
            return False
        showing, _ = self._result_screen(rect)
        if not showing:
            self.ctx.log("Not on the result screen - skipping Repeat.")
            return False
        if not self.ctx.click_anchor(rect, "repeat_btn"):
            return False
        self.ctx.drv.wait(self.ctx.execution("repeat_wait_ms", 2500))
        self.ctx.log("Clicked Repeat Stage.")
        return True

    # ---------------- the whole sequence ----------------

    def run_out(self, rect, record):
        """Play the match out and start the next one.

        `record(outcome)` is called once the outcome is known and the result
        screen is on display. That ordering is deliberate on both sides: the
        outcome only EXISTS on the result screen (this game names Victory
        only there), and the screenshot has to be taken while that screen is
        still up - it carries the run stats and full reward list, which makes
        a far better Discord attachment than a frame of the map. Clicking
        Repeat before recording would replace it with the next match.
        """
        self.ctx.log("Steps done - waiting for the match to end...")
        in_match = self.wait_for_match_end(rect)
        self.clear_reward_screens(rect)
        on_screen = self.read_result_screen(rect)
        record(on_screen or in_match or "abort")
        self.click_repeat(rect)
