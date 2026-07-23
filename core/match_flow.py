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
                    self.ctx.log("Match finished — reward screens are up.")
                    return "ended"
            # The result screen itself is the most reliable end-of-match
            # signal: its Repeat Stage button is present on BOTH win and loss
            # and matches ~1.0, where the win/loss banners can be scale- or
            # timing-sensitive. Without this a loss that shows no reward
            # screens and whose defeat banner matches poorly would sit here
            # until result_timeout_s and never repeat.
            if self.rewards.repeat_available():
                showing, score = self._result_screen(rect)
                if showing:
                    self.ctx.log("Match finished — results screen is up.")
                    return "ended"
            return None

        got = self.ctx.poll_until(check, self.ctx.execution("result_timeout_s", 900))
        if got is None:
            self.ctx.log("Gave up waiting for the match to end.")
            return None
        # "ended" = match is over but not banner-classified; the result screen
        # read (read_result_screen) names the win/loss.
        return None if got == "ended" else got

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

        # The caption may not be up the instant we arrive here. When the match
        # end was read from the in-match banner (not the reward screens), the
        # item screens animate in a moment LATER - so a bare "is it showing?"
        # check sees nothing, returns "cleared" after 0 clicks, and the reward
        # screens then play out unclicked, stalling the whole loop (bug 1.1).
        # Wait a bounded window for the caption OR the result screen to appear.
        # A loss skips reward screens entirely and goes straight to the result
        # screen, so that short-circuits the wait immediately.
        if not self._reward_strip(rect)[0]:
            def caption_or_result():
                if self._reward_strip(rect)[0]:
                    return "reward"
                if self.rewards.repeat_available() and self._result_screen(rect)[0]:
                    return "result"
                return None
            got = self.ctx.poll_until(
                caption_or_result,
                self.ctx.execution("reward_appear_timeout_s", 12))
            if got != "reward":
                # Result screen already up (loss / no item screens), or nothing
                # appeared in the window - nothing to click through either way.
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
                    self.ctx.log(f"Cleared the reward screens ({clicks} clicks).")
                return True
            cx, cy = rect.to_screen(*point)
            self.ctx.drv.click(cx, cy)
            clicks += 1
            self.ctx.drv.wait(gap_ms)
        self.ctx.log(f"Reward screens still showing after {cap} clicks — "
                     "giving up this round.")
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
            self.ctx.log("Results screen never appeared — recording the result "
                         "from the match instead.")
            return None
        outcome = self.detector.classify_result_screen(self.ctx.cap.grab(rect))
        self.ctx.log(f"Results screen: {outcome}.")
        return None if outcome == "unknown" else outcome

    def click_repeat(self, rect) -> bool:
        """Click Repeat Stage to start the next run.

        Re-confirms the result screen immediately before clicking: this button
        sits beside "Back to lobby", so clicking blind on a mistimed frame is
        how a run ends up out of the stage entirely.

        Clicks the Repeat Stage button at its TEMPLATE-MATCHED location rather
        than the fixed repeat_btn anchor: that anchor was measured on the win
        screen (Repeat is the middle of three), but the loss screen drops
        "Next Stage" and Repeat shifts left, so a fixed click stalls every loss
        (bug 1.7). Matching the button finds its real column either way."""
        if not self.ctx.execution("auto_repeat", True):
            return False
        if not self.rewards.repeat_available():
            return False
        roi = self.ctx.anchor("result_screen_roi", self.RESULT_SCREEN)
        img = self.ctx.cap.grab_roi(rect, roi)
        showing, _, center = self.rewards.result_screen_loc(img)
        if not showing:
            self.ctx.log("Not on the results screen — skipping Repeat.")
            return False
        x1, y1 = roi[0], roi[1]
        sx = int(rect.x + x1 * rect.w + center[0])
        sy = int(rect.y + y1 * rect.h + center[1])
        self.ctx.drv.click(sx, sy)
        self.ctx.drv.wait(self.ctx.execution("repeat_wait_ms", 2500))
        self.ctx.log("Pressed 'Repeat Stage'.")
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
        self.ctx.log("Steps done — waiting for the match to end…")
        in_match = self.wait_for_match_end(rect)
        self.clear_reward_screens(rect)
        on_screen = self.read_result_screen(rect)
        record(on_screen or in_match or "abort")
        self.click_repeat(rect)
