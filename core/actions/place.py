"""Placing a unit - the step type most likely to desync a run."""

import time

from vision import capture as vcap

from .base import StepAction, Target


class PlaceAction(StepAction):
    name = "place"

    def execute(self, step, rect, target: Target):
        # Resolve the card WITHOUT arming it. The loop arms immediately before
        # each placement click; arming here as well meant the loop's first
        # "is a unit already here?" click landed with a live card and placed
        # one - one extra unit per step, every step (HANDOFF 2.29).
        if self.hotbar.position(step.slot) is None:
            self.ctx.log(f"#{step.id} place skipped - hotbar slot {step.slot} "
                         "has no position.")
            return
        # No deselect-first for a leftover panel (HANDOFF 2.38): the check
        # click in _unit_is_there resolves it by itself - clicking an empty
        # spot deselects, clicking a unit switches the panel to it - without
        # depending on deselect_btn being calibrated.
        if not self._place_until_verified(step, rect, target):
            return
        if step.priority != "none" or step.upgrade_mode != "off":
            self._after_place(step, rect, target)
        else:
            # Panel-verified placements leave the panel open; close it so it
            # doesn't cover the map for the next step.
            self.panel.deselect(rect)

    # ---------------- the two ways to tell a unit is there ----------------

    # `ctx.panel_shows_unit(rect)` is the authoritative check: is anything
    # selected right now, measured against the loop's known-empty panel
    # (StageSetup.capture_panel_baseline). It exists because watching the MAP
    # does not work on a real stage (HANDOFF 2.26) - the window around a
    # marker is ~77x43px while a unit model is about the same size, so a
    # neighbour placed one step earlier sits inside it, and that neighbour's
    # spawn animation finishing reads as "a unit appeared here". The panel is
    # static UI in a fixed place, and nothing on the map can fake it.

    def _roi(self, target: Target) -> list[float]:
        r = 0.03
        return [max(0.0, target.ax - r), max(0.0, target.ay - r),
                min(1.0, target.ax + r), min(1.0, target.ay + r)]

    def _settle(self, rect, roi):
        """Read a patch of map until it stops moving. Returns (image, settled)
        - the last read either way, so a caller always has something to
        compare.

        Only used as the FALLBACK verification when upgrade_level_roi isn't
        calibrated. Settling filters out things that move (enemies crossing
        the spot); it cannot filter out a neighbouring unit that appears once
        and then stays, which is why the panel check above outranks it."""
        gap = self.ctx.execution("place_settle_interval_ms", 250)
        tries = self.ctx.execution("place_settle_reads", 6)
        prev = self.ctx.cap.grab_roi(rect, roi)
        for _ in range(tries):
            self.ctx.check_stop()
            self.ctx.drv.wait(gap)
            cur = self.ctx.cap.grab_roi(rect, roi)
            if not vcap.region_changed(prev, cur):
                return cur, True
            prev = cur
        return prev, False

    def _park_cursor(self, rect):
        """Move the mouse off the placement spot before judging it. An armed
        card draws a preview under the cursor, and a cursor left sitting on
        the marker puts that preview inside the very region being checked."""
        park = self.ctx.execution("cursor_park", [0.02, 0.5])
        self.ctx.drv.move(*rect.to_screen(*park))

    # ---------------- the retry loop ----------------

    def _unit_is_there(self, rect, target: Target, use_panel, roi, baseline) -> bool:
        """Is a unit standing on this spot? NEVER places anything (no card is
        armed when this runs).

        Clicks the spot and reads the panel - clicking a unit opens/switches
        to its panel, clicking empty ground deselects whatever was open. The
        old version returned True WITHOUT clicking whenever any panel was
        open, which turned one leftover panel (a failed deselect) into every
        later placement being skipped (HANDOFF 2.38). The cost of clicking
        first: a click on this spot's OWN already-selected unit toggles its
        panel off and reads as empty - recovered with one more click, which
        re-selects it (only attempted when a panel was open going in, so an
        empty spot doesn't pay double clicks)."""
        if use_panel:
            was_open = self.ctx.panel_shows_unit(rect)
            self.ctx.drv.click(target.sx, target.sy)
            self.ctx.drv.wait(self.ctx.execution("place_select_wait_ms", 400))
            self._park_cursor(rect)
            if self.ctx.panel_shows_unit(rect):
                return True
            if was_open:
                self.ctx.drv.click(target.sx, target.sy)
                self.ctx.drv.wait(self.ctx.execution("place_select_wait_ms", 400))
                self._park_cursor(rect)
                return self.ctx.panel_shows_unit(rect)
            return False

        self._park_cursor(rect)
        after, settled = self._settle(rect, roi)
        # Remembered for the failure message: a spot that never stops moving
        # is a different problem (marker on the enemy path) from one that
        # stays stubbornly empty (never affordable).
        self._busy = not settled
        return settled and vcap.region_changed(baseline, after)

    def _place_until_verified(self, step, rect, target: Target) -> bool:
        """Put a unit on this spot, retrying until one is really there.

        Placement is the main desync risk (HANDOFF 2.6): every later step
        assumes this unit exists, so a silently-failed placement corrupts the
        rest of the run. Retrying is on a slow interval rather than at click
        speed because the usual cause of failure is "not enough cash yet",
        which is a wait, not an error (HANDOFF 2.25).

        **Every iteration checks BEFORE it places, never after.** Verifying
        after the click means a false negative re-clicks an occupied spot and
        places a SECOND unit - which is what happened on a real run: five
        units stacked where one was wanted, reported as "placed on attempt 5"
        (HANDOFF 2.29). Checking first makes that impossible: a placement
        click is only ever issued at a spot just confirmed empty. The cost is
        one cheap select-click before the first placement.

        Re-arms the hotbar card before every placement click, not just the
        first. A click that fails to place (bad terrain, an overlay in the
        way) can also cost the card's ARMED state - Roblox drops back to
        "nothing selected" rather than leaving it ready, so retrying with only
        another click fails identically every time (HANDOFF 2.20).

        A verified placement still can't be told apart from a queued ghost,
        which is why phantom/pre-placement must be OFF in-game (HANDOFF
        section 7); with it off, an underfunded click is a clean no-op."""
        use_panel = self.ctx.panel_empty is not None
        roi = self._roi(target)
        baseline = None if use_panel else self._settle(rect, roi)[0]
        timeout = self.ctx.execution("place_timeout_s", 45)
        interval = self.ctx.execution("place_retry_interval_ms", 1200)
        deadline = time.monotonic() + timeout

        placed = 0
        self._busy = False
        while True:
            self.ctx.check_stop()
            if self._unit_is_there(rect, target, use_panel, roi, baseline):
                if placed > 1:
                    self.ctx.log(f"#{step.id} placed after {placed} attempts.")
                return True
            # `placed` guard: always make at least one real attempt, however
            # tight the timeout is set.
            if placed and time.monotonic() >= deadline:
                break

            if placed:
                # Nothing landed last time. Almost always "can't afford it
                # yet", so wait rather than burning attempts at click speed.
                self.ctx.drv.wait(interval)
            self.hotbar.select(rect, step.slot)
            self.ctx.drv.click(target.sx, target.sy)
            self.ctx.drv.wait(self.ctx.execution("place_select_wait_ms", 400))
            placed += 1
            # Fast path: placing auto-selects the new unit, so the panel
            # lighting up right after OUR placement click is the verification.
            # Safe to trust: the check that preceded this click confirmed
            # nothing was selected, so a lit panel can only be the unit just
            # placed. Skips the next check's select-click and the toggle-off
            # recovery it would need (HANDOFF 2.38).
            if use_panel:
                self._park_cursor(rect)
                if self.ctx.panel_shows_unit(rect):
                    if placed > 1:
                        self.ctx.log(f"#{step.id} placed after {placed} attempts.")
                    return True

        if use_panel:
            why = "most likely never affordable"
        elif self._busy:
            why = ("the spot never stopped moving, so nothing could be "
                   "confirmed - check the marker isn't on the enemy path")
        else:
            why = ("most likely never affordable (verified by watching the "
                   "map; calibrate upgrade_level_roi for the reliable check)")
        self.ctx.log(f"#{step.id} place FAILED: {placed} attempt(s) over "
                     f"{timeout}s and no unit ever appeared there - {why}. "
                     "Continuing without it; later steps for this spot will "
                     "find nothing.")
        return False

    def _after_place(self, step, rect, target: Target):
        """Priority + auto-upgrade bundled onto a verified placement.

        The panel is ALREADY OPEN on this unit when we get here: placing a unit
        auto-selects it (Step.md / IMG_9374), and panel-mode verification only
        returns once that panel is up. So each sub-action must re-open it
        through select_verified, NOT a bare select() - a bare click on the
        already-open panel would toggle the selection back OFF and the action
        would land on nothing (this is the exact trap HANDOFF 2.20's "placing
        does not select" note pre-dated; that note is superseded). UnitPanel's
        methods already route through select_verified, so this just calls
        them."""
        if step.priority != "none":
            self.panel.set_priority(rect, target.sx, target.sy, step)

        if step.upgrade_mode == "times":
            self.panel.upgrade_times(rect, target.sx, target.sy, step, step.times)
        elif step.upgrade_mode == "max":
            self.panel.upgrade_max(rect, target.sx, target.sy, step)
        self.panel.deselect(rect)
