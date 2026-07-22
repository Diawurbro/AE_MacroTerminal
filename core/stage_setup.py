"""Getting the stage into a known state before any step runs.

Everything here is about making the profile's recorded coordinates VALID:
the character back at spawn, the camera at its fixed top-down angle, and
the screen matching the reference the markers were placed against.
"""

import os

from vision import capture as vcap


class StageSetup:
    def __init__(self, ctx, camera, state_detector, panel):
        self.ctx = ctx
        self.camera = camera
        self.state_detector = state_detector
        self.panel = panel

    def wait_for_in_stage(self, rect) -> bool:
        """Optional gate (execution.wait_for_in_stage): block until the game-
        state detector reports 'in_stage', so a loop never acts on a loading
        screen or in the lobby. Returns True (no-op) unless the flag is on AND
        an in_stage template exists - so it can't accidentally block runs."""
        if not self.ctx.execution("wait_for_in_stage", False):
            return True
        if not self.state_detector.available():
            return True
        self.ctx.log("Waiting for the in-stage HUD...")
        got = self.ctx.poll_until(
            lambda: self.state_detector.detect(self.ctx.cap.grab(rect)) == "in_stage",
            self.ctx.execution("state_wait_timeout_s", 60))
        return bool(got)

    def teleport_to_spawn(self, rect):
        """Click the game's own teleport-to-spawn button, if one is calibrated.

        This is why there's no walk-path/servo subsystem at all (HANDOFF 2.2).

        Used to tap game.teleport_key. That key was never verified, "t" (the
        default guess) is actually the in-game Upgrade bind, and the macro no
        longer sends keystrokes at all (HANDOFF 2.22) - so this is now a
        click on game.teleport_btn and is OFF until someone sets that
        coordinate. Nothing here ever moves the character, so a run that
        starts at spawn stays at spawn and the teleport is only a recovery
        path for a user who walked away by hand; the reference-image check
        below is what actually catches a bad starting position.

        Deselects first: a plain 'place' step with no priority/upgrade never
        triggers a deselect, so a unit panel can still be open here, covering
        whatever we're about to click."""
        btn = self.ctx.game("teleport_btn")
        if not btn:
            return
        self.panel.deselect(rect)
        self.ctx.log("Teleporting to spawn...")
        sx, sy = rect.to_screen(*btn)
        self.ctx.drv.click(sx, sy)
        self.ctx.drv.wait(self.ctx.game("teleport_wait_ms", 1500))

    def normalize_camera(self, rect):
        self.ctx.log("Normalizing camera (top-down)...")
        self.camera.normalize(rect)

    def reference_score(self, rect) -> float | None:
        """How closely the live screen matches the stage reference image, or
        None when there's no reference to compare against."""
        ref_path = self.ctx.profile.reference_image
        if not ref_path or not os.path.exists(ref_path):
            return None
        return vcap.similarity(self.ctx.cap.grab(rect), vcap.load(ref_path))

    def normalize_and_verify(self, rect) -> bool:
        """Get the camera to its clamps and CONFIRM it landed there, retrying
        the whole sequence if it didn't.

        Every step coordinate was recorded against the reference image, so a
        camera that isn't back at the same angle makes all of them wrong -
        and wrong in a specific, destructive way: at a shallow angle a click
        aimed at mid-screen hits the ground plane far away, so units land at
        the edge of the map (HANDOFF 2.28). That's what a silent mismatch
        actually costs, which is why this now retries and then refuses,
        instead of warning and carrying on.

        Retrying is worth doing because the sequence has a known flaky step:
        Roblox has to capture the mouse for the camera drag to register, and
        the focus click that arranges it can be swallowed."""
        attempts = max(1, self.ctx.execution("camera_attempts", 3))
        threshold = self.ctx.vision("ref_match_threshold", 0.65)
        best = None
        for i in range(attempts):
            self.ctx.check_stop()
            self.normalize_camera(rect)
            score = self.reference_score(rect)
            if score is None:
                self.ctx.log("No reference image set - skipping camera "
                             "verification. Capture one: the run cannot tell "
                             "a good camera from a bad one without it.")
                return True
            best = score if best is None else max(best, score)
            self.ctx.log(f"Reference match: {score:.3f} (need >= {threshold})")
            if score >= threshold:
                return True
            if i + 1 < attempts:
                self.ctx.log(f"Camera doesn't match the reference - "
                             f"re-normalizing (attempt {i + 2}/{attempts}).")
        self.ctx.log(f"Camera never matched the reference (best {best:.3f} of "
                     f"{threshold}).")
        return False

    def verify_or_renormalize(self, rect) -> bool:
        """Repeat-loop camera check: VERIFY first, normalize only on mismatch.

        Repeat Stage restarts the stage, which respawns the character - and
        Roblox resets the camera on respawn (HANDOFF 2.3). So "the camera set
        on entry holds across repeats" (2.33's assumption) is wrong for this
        game: round 2 ran on the default angled camera with no check at all,
        every coordinate meant a different world position, and nothing was
        really placed (HANDOFF 2.39). Verifying is cheap and not flaky, so do
        it every round; the flaky normalize sequence only runs when the verify
        says the camera actually moved.

        Polls the score for up to execution.repeat_ref_wait_s first - right
        after Repeat the stage can still be fading in, and a premature
        "mismatch" would run the normalize against a loading screen."""
        threshold = self.ctx.vision("ref_match_threshold", 0.65)
        first = self.reference_score(rect)
        if first is None:
            return True   # no reference to compare - same no-op as entry
        if first >= threshold:
            self.ctx.log(f"Camera still matches ({first:.3f}) - not "
                         "re-normalizing.")
            return True

        wait_s = self.ctx.execution("repeat_ref_wait_s", 8)
        state = {"score": first}

        def settled():
            state["score"] = self.reference_score(rect) or 0.0
            return state["score"] >= threshold or None

        if self.ctx.poll_until(settled, wait_s):
            self.ctx.log(f"Camera still matches ({state['score']:.3f}) - not "
                         "re-normalizing.")
            return True
        self.ctx.log(f"Camera doesn't match after Repeat (best "
                     f"{max(first, state['score']):.3f} of {threshold}) - the "
                     "game likely reset it on restart. Re-normalizing...")
        return self.normalize_and_verify(rect)

    def capture_panel_baseline(self, rect):
        """Record what the unit panel's level readout looks like with NOTHING
        selected. Called once per loop, after Start Game.

        This moment is chosen because it's the only one that's provably
        empty: no unit has been placed yet this loop, so nothing CAN be
        selected. Every later "is a unit standing here?" check compares
        against this picture.

        It used to snapshot the region at the top of each place step and ask
        "did it change?", which inverts in two situations that both happened
        on a real run (HANDOFF 2.30): a panel left open by the previous step
        (the next step's click closes it - a change - and reads as "a unit is
        here"), and a loop starting mid-transition right after Repeat Stage
        (the transition clearing is also a change). Loop 1 looked perfect and
        loop 2 placed nothing.

        The region is settled first for the same reason - a baseline caught
        mid-animation isn't a baseline."""
        roi = self.ctx.anchor("upgrade_level_roi")
        if not roi:
            self.ctx.panel_empty = None
            self.ctx.log("upgrade_level_roi isn't calibrated - placements fall "
                         "back to watching the map, which can't tell a new unit "
                         "from a neighbour's. Set it in the Calibrate tab.")
            return
        img, settled = self.ctx.settle_roi(rect, roi)
        self.ctx.panel_empty = img
        if not settled:
            self.ctx.log("The unit-panel region never settled - placement "
                         "checks this loop may be unreliable.")

    def press_start_game(self, rect):
        """Click the in-game 'Start Game' button so a run kicks off the match
        on its own. Enabled by game.press_start_game (toggled live from the
        dashboard checkbox); position is game.start_game_btn (normalized)."""
        if not self.ctx.game("press_start_game"):
            return
        btn = self.ctx.game("start_game_btn")
        if not btn:
            self.ctx.log("press_start_game is on but game.start_game_btn is not set.")
            return
        sx, sy = rect.to_screen(*btn)
        self.ctx.drv.click(sx, sy)
        self.ctx.log("Pressed Start Game.")
        self.ctx.drv.wait(self.ctx.game("start_game_wait_ms", 400))
