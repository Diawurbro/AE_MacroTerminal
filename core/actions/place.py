"""Placing a unit - the step type most likely to desync a run."""

import time

from core import ocr
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
            self.ctx.log(f"Step {step.id}: skipped — hotbar slot {step.slot} "
                         "isn't in your loadout.")
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

    def _read_cash(self, rect) -> int | None:
        """Current cash, or None if it can't be read."""
        roi = self.ctx.anchor("cash_roi")
        if not roi or not ocr.READY:
            return None
        return ocr.read_int(self.ctx.cap.grab_roi(rect, roi))

    def _landed(self, rect, cash_before, timeout_ms: int) -> bool:
        """Did the placement click we just issued actually buy a unit?

        Polls TWO independent signals and takes either:

        - the unit panel opening, because placing auto-selects the new unit;
        - cash going DOWN from what it was immediately before the click.

        The cash signal is what stops this step stacking units. Every check
        here used to run through the panel, so a placement that worked but
        whose panel didn't open - the click lands only intermittently, and
        the panel takes a variable moment to draw - was read as failure and
        the loop placed ANOTHER unit on the same spot, burning cash and
        reporting it as "placed after N tries". Cash can only go up on its
        own (income, kills, selling), so a drop within a moment of our own
        click means the purchase went through, whatever the panel is doing.
        Both signals are optional: with neither available this returns False
        and the caller falls back to watching the map."""
        deadline = time.monotonic() + timeout_ms / 1000.0
        can_panel = self.ctx.can_check_panel
        while True:
            if can_panel and self.ctx.panel_shows_unit(rect):
                return True
            if cash_before is not None:
                now = self._read_cash(rect)
                if now is not None and now < cash_before:
                    return True
            if time.monotonic() >= deadline:
                return False
            self.ctx.check_stop()
            self.ctx.drv.wait(100)

    # ---------------- the retry loop ----------------

    def _unit_is_there(self, rect, target: Target, use_panel, roi, baseline) -> bool:
        """Is a unit standing on this spot? NEVER places anything, and NEVER
        clicks THIS spot's coordinates - a prior version clicked target.sx/sy
        itself to "test/clear" whatever panel was showing, but that click can
        land on a NEARBY already-placed unit instead of this exact spot
        (hotbar markers can sit close together) and read THAT neighbor's
        panel as evidence THIS spot succeeded - reporting a placement that
        never happened (confirmed on a real run). A leftover panel from the
        previous step is cleared once, safely, before the retry loop even
        starts (see _place_until_verified) - by the time this runs, a plain
        read of the panel is sufficient. Our own placement click, a few lines
        down in the retry loop, is what triggers Roblox's own auto-select if
        it actually landed."""
        if use_panel:
            return self.ctx.panel_shows_unit(rect)

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

        **Checks before placing AND verifies its own click before looping.**
        Stacking units on one spot is the failure this guards against - five
        units where one was wanted, reported as "placed on attempt 5"
        (HANDOFF 2.29). The pre-check keeps a placement click from ever being
        issued at an occupied spot; the post-click verification (_landed)
        keeps a placement that DID work from being retried because its panel
        happened not to open. Verifying only before, as this did, left that
        second hole wide open: every signal ran through the panel, so an
        unopened panel looked exactly like a failed placement.

        Re-arms the hotbar card before every placement click, not just the
        first. A click that fails to place (bad terrain, an overlay in the
        way) can also cost the card's ARMED state - Roblox drops back to
        "nothing selected" rather than leaving it ready, so retrying with only
        another click fails identically every time (HANDOFF 2.20).

        A verified placement still can't be told apart from a queued ghost,
        which is why phantom/pre-placement must be OFF in-game (HANDOFF
        section 7); with it off, an underfunded click is a clean no-op."""
        use_panel = self.ctx.can_check_panel
        if use_panel and self.ctx.panel_shows_unit(rect):
            # A panel left open by the previous step would otherwise answer
            # for this one - close it via deselect_point (curated specifically
            # to be off any unit, see config.example.yaml), not by clicking
            # this spot's own coordinates: doing that here used to risk
            # landing on a NEARBY unit instead and reading its panel as this
            # spot's answer (see _unit_is_there). Once per placement, not
            # once per retry.
            self.ctx.drv.click(*rect.to_screen(*self.ctx.execution("deselect_point", [0.62, 0.25])))
            self.ctx.drv.wait(self.ctx.execution("place_select_wait_ms", 400))
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
                    self.ctx.log(f"Step {step.id}: unit placed (after {placed} tries).")
                return True
            # `placed` guard: always make at least one real attempt, however
            # tight the timeout is set.
            if placed and time.monotonic() >= deadline:
                break

            if placed:
                # Nothing landed last time. Almost always "can't afford it
                # yet", so wait rather than burning attempts at click speed.
                self.ctx.drv.wait(interval)
            # Read cash IMMEDIATELY before the click - _landed compares
            # against it to spot the purchase.
            cash_before = self._read_cash(rect)
            self.hotbar.select(rect, step.slot)
            self.ctx.drv.click(target.sx, target.sy)
            self.ctx.drv.wait(self.ctx.execution("place_select_wait_ms", 400))
            placed += 1
            # Verify OUR click before looping, so a placement that worked is
            # never followed by a second one on the same spot.
            self._park_cursor(rect)
            if self._landed(rect, cash_before,
                            self.ctx.execution("place_verify_wait_ms", 900)):
                if placed > 1:
                    self.ctx.log(f"Step {step.id}: unit placed (after {placed} tries).")
                return True

        if use_panel:
            why = "you probably never had enough cash"
        elif self._busy:
            why = ("the spot kept changing, so it couldn't be confirmed — "
                   "check the marker isn't on the enemy path")
        else:
            why = ("you probably never had enough cash (checked by watching "
                   "the map — calibrate the unit-level readout for a more "
                   "reliable check)")
        self.ctx.log(f"Step {step.id}: couldn't place a unit after {placed} "
                     f"tries in {timeout}s — {why}. Continuing without it.")
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
