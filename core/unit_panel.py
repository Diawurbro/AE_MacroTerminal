"""The selected-unit panel: selecting a unit, and its Upgrade / Sell /
Priority controls.

The panel may already be open when a method here runs: placing a unit
auto-selects it, so its info panel is up by the time the place step goes on
to set priority / buy upgrades (Step.md / IMG_9374; place.py leans on the
same behaviour to verify a placement). It may equally be closed - a
standalone upgrade/sell step acts on some arbitrary earlier unit. So a method
must OPEN the panel defensively rather than assume a state, and must never do
so with a BARE click on an already-open panel: that click toggles the current
selection back OFF. select_verified is the safe primitive - it deselects
whatever is open first, then selects this spot - so one path is correct either
way. Upgrade, priority and sell all go through it.
"""

import time

from core import ocr
from vision import capture as vcap


class UnitPanel:
    def __init__(self, ctx):
        self.ctx = ctx
        self._warned_deselect = False

    # ---------------- selection ----------------

    def select(self, sx, sy, settle_ms: int = 150):
        """Click a placed unit to open its info panel."""
        self.ctx.drv.click(sx, sy)
        self.ctx.drv.wait(settle_ms)

    def level_shot(self, rect):
        """The panel's "Upgrade N/M" caption, or None if it isn't calibrated.

        This one small region answers both questions this class needs: it is
        blank when no unit is selected (so it says whether a unit is selected,
        compared against the loop's empty-panel baseline) and its text changes
        when a level is bought (so it says whether an upgrade actually
        applied). No OCR involved - a pixel diff is enough for both, which is
        the point: it works on a machine without Tesseract (HANDOFF 2.27)."""
        roi = self.ctx.anchor("upgrade_level_roi")
        return self.ctx.cap.grab_roi(rect, roi) if roi else None

    def select_verified(self, rect, sx, sy) -> bool | None:
        """Click a spot and report whether a unit got selected. Returns None
        when there's no empty-panel baseline to compare against - callers
        treat that as "carry on regardless".

        Compares against ctx.panel_empty (captured once per loop with nothing
        selected) rather than against a snapshot taken a moment ago: a
        relative baseline reads "changed" when a leftover panel CLOSES, i.e.
        it reports a unit exactly when there isn't one (HANDOFF 2.30).

        No deselect-first (HANDOFF 2.38): clicking unit B while A's panel is
        open SWITCHES the panel to B, and clicking empty ground deselects - so
        the click itself resolves a leftover panel either way, without
        depending on deselect_btn / deselect_point being calibrated (the
        dependency behind the skipped-placement failures). The one trap is
        clicking the SAME already-selected unit, which toggles its panel OFF
        and reads as "no unit here" - recovered with one more click, which
        re-selects it.

        The recovery click is UNCONDITIONAL on a False first read - it used to
        be gated on "was a panel showing before the click", but that read
        can't tell "closed" from "still selected but mis-read" (a mis-aimed
        deselect can collapse the panel without deselecting, and the region
        then reads empty). That gap made the upgrade row right after a
        placement toggle its own just-placed unit off and skip with "no unit"
        (HANDOFF 2.40). An empty spot just pays one extra harmless click.

        Waits place_select_wait_ms (400) for the panel to draw before reading
        it, same as the placement check (place.py) - a slow panel draw used to
        read as "no unit here" (bug 1.2)."""
        settle = self.ctx.execution("place_select_wait_ms", 400)
        if self.ctx.panel_empty is None:
            self.select(sx, sy, settle)
            return None
        self.select(sx, sy, settle)
        if self.ctx.panel_shows_unit(rect):
            return True
        # May have toggled OFF the very unit being selected - one more click
        # re-selects it. An empty spot stays empty (correct False).
        self.select(sx, sy, settle)
        return self.ctx.panel_shows_unit(rect)

    def deselect(self, rect):
        """Close the panel so it stops covering the map before the next
        placement click. Clicks the panel's own X - tapping Escape would open
        Roblox's own game menu instead. No-ops if deselect_btn isn't set.

        Checks that it actually worked. A mis-calibrated deselect_btn leaves
        the panel open, and a panel that outlives its step used to poison the
        next one's placement check (HANDOFF 2.30). That's fixed, but a stuck
        panel still covers the map, so say so once rather than never."""
        if self.ctx.click_anchor(rect, "deselect_btn"):
            self.ctx.drv.wait(120)
        if not self.ctx.panel_shows_unit(rect):
            return

        # Still open. Fall back to clicking bare ground - the game deselects
        # when you click away from a unit, and unlike deselect_btn that doesn't
        # depend on an anchor being calibrated right. Safe because no hotbar
        # card is ever armed here: arming is immediately followed by its
        # placement click.
        #
        # Retried a few times because ONE stuck panel breaks the whole rest of
        # the loop: every later "is a unit already here?" check then reads the
        # leftover panel as "yes", so subsequent placements are skipped without
        # a click (the reported "not even placing" bug). A swallowed click or a
        # frame of lag is enough to need a second try.
        #
        # deselect_point is its own point, NOT cursor_park: the unit panel is
        # bottom-LEFT (~x 0.01-0.33, y 0.30-0.71) and cursor_park's [0.02, 0.5]
        # lands INSIDE it, so that click hit the panel and never closed it.
        point = self.ctx.execution("deselect_point", [0.62, 0.25])
        for _ in range(max(1, self.ctx.execution("deselect_attempts", 3))):
            self.ctx.drv.click(*rect.to_screen(*point))
            self.ctx.drv.wait(150)
            if not self.ctx.panel_shows_unit(rect):
                return
        if not self._warned_deselect:
            self._warned_deselect = True
            self.ctx.log("Couldn't close the unit panel — calibrate 'Unit "
                         "panel close (X)' in the Calibrate tab, or move the "
                         "deselect point onto empty ground. Until then it may "
                         "sit over the map and cause skipped placements.")

    # ---------------- the three action buttons ----------------

    def action(self, rect, name: str):
        """Trigger the selected unit's Upgrade / Sell / Priority control.

        Default (game.use_unit_keys, HANDOFF 2.38): tap the control's own
        keybind - the panel prints one on each button ([T] Upgrade, [X] Sell,
        [R] Priority, measured in 2.14). A keypress can't land a few px off
        the button or get eaten by an overlay the way a click can, which
        stalled real runs. Falls back to clicking the measured ui_anchors
        position when keys are off or the key isn't mapped.

        Requires a unit to already be selected; does nothing otherwise."""
        if self.ctx.game("use_unit_keys", True):
            key = (self.ctx.game("unit_keys", {}) or {}).get(name)
            if key:
                try:
                    self.ctx.drv.tap(str(key))
                    return
                except KeyError:
                    self.ctx.log(f"{key!r} isn't a valid key for {name} — "
                                 "clicking the button instead.")
        self.ctx.click_anchor(rect, f"{name}_btn")

    # ---------------- priority ----------------

    def set_priority(self, rect, sx, sy, step):
        """Set targeting priority by cycling the button and reading its own
        label back.

        The priority control is a CYCLE button, not a dropdown menu
        (HANDOFF 2.14/2.18): it displays its current selection as text
        ('None', 'First', ...) and each activation advances to the next
        option. There's no way to jump straight to a target, so this cycles
        and re-reads until the label matches, bounded by len(PRIORITY_TYPES)
        so an unreadable label - or a game whose real options differ from our
        guess - warns instead of spinning forever. `priority_options` (a
        per-option coordinate map) is retired; it modeled a menu that doesn't
        exist.

        Only 'none' and 'first' are confirmed values; the rest of
        PRIORITY_TYPES is still a guess at the game's real option set, which
        is exactly what the bounded loop below is defending against."""
        from data.profile import PRIORITY_TYPES

        # Open THIS unit's panel without assuming it isn't already open. Placing
        # a unit auto-selects it (Step.md / IMG_9374), so by the time
        # _after_place gets here the panel is already up on this very unit - a
        # bare select() would click the already-selected unit and TOGGLE THE
        # PANEL CLOSED, and every priority read below would then run against a
        # shut panel, so the priority silently never got set. select_verified
        # deselects whatever is open first, then selects this spot (the same
        # guard the upgrade path uses). It returns False only when the spot is
        # genuinely empty (the placement here failed) and None when there's no
        # baseline to judge, in which case we carry on exactly as before.
        if self.select_verified(rect, sx, sy) is False:
            self.ctx.log(f"Step {step.id}: can't set priority '{step.priority}' "
                         f"— no unit at {step.x:.3f}, {step.y:.3f} (its "
                         "placement likely failed).")
            return
        label_roi = self.ctx.anchor("priority_label_roi")
        target = step.priority

        if not ocr.HAS_TESSERACT or not label_roi:
            reason = ("Tesseract not installed" if not ocr.HAS_TESSERACT
                      else "priority_label_roi not calibrated")
            self.ctx.log(f"Step {step.id}: priority '{target}' — {reason}; "
                         "setting it once without checking.")
            self.action(rect, "priority")
            self.ctx.drv.wait(150)
            return

        def read():
            word = ocr.read_word(self.ctx.cap.grab_roi(rect, label_roi))
            return (word or "").strip().lower()

        if read() == target.lower():
            self.ctx.log(f"Step {step.id}: priority already '{target}'.")
            return

        limit = max(1, len(PRIORITY_TYPES))
        cur = None
        for _ in range(limit):
            self.ctx.check_stop()
            self.action(rect, "priority")
            self.ctx.drv.wait(150)
            cur = read()
            if cur == target.lower():
                self.ctx.log(f"Step {step.id}: priority set to {target}.")
                return
        self.ctx.log(f"Step {step.id}: couldn't set priority to '{target}' "
                     f"after {limit} tries (last read: {cur!r}) — the option "
                     "list may not match this game.")

    # ---------------- upgrading ----------------

    def _read_level(self, rect):
        """(N, M) from the panel's "Upgrade N/M" caption, or None when it
        can't be read (no Tesseract, ROI uncalibrated, or a bad frame).

        This is the DEFINITIVE "is it maxed?" signal. N>=M means the unit
        can't go higher - which the pixel-diff in upgrade_once cannot tell
        apart from "can't afford the next level yet" (both look like "nothing
        changed"), so without this an already-maxed unit gets clicked for the
        whole upgrade_timeout_s before the loop gives up (the "doesn't stop
        after upgrade to max" report)."""
        if not ocr.HAS_TESSERACT:
            return None
        roi = self.ctx.anchor("upgrade_level_roi")
        if not roi:
            return None
        n, m = ocr.read_fraction(self.ctx.cap.grab_roi(rect, roi))
        if n is None or m is None:
            return None
        return n, m

    def upgrade_once(self, rect, step) -> bool:
        """Buy exactly ONE level: click Upgrade until the panel's level readout
        CHANGES - that change is the only reliable "a level was bought" signal.

        A readout that doesn't change is either maxed or not-yet-affordable, and
        those need opposite handling, so ONLY on a no-change is the N/M caption
        read (OCR): N>=M means maxed - stop now; N<M means "can't afford yet" -
        keep clicking on a slow interval until income arrives (the user's ask).

        Reading OCR only here, never to pre-empt a click, is what keeps a MISREAD
        max from stopping an upgrade early: a level that can actually buy changes
        the readout and is counted before OCR is ever looked at - so "5/8"
        misread as "5/5" no longer maxes a unit at level 5 (the reported bug).

        Falls back to a single unverified click when upgrade_level_roi isn't
        calibrated - there is nothing to watch, and one click is what the old
        code did."""
        before = self.level_shot(rect)
        if before is None:
            self.action(rect, "upgrade")
            self.ctx.drv.gap()
            return True

        timeout = self.ctx.execution("upgrade_timeout_s", 120)
        interval = self.ctx.execution("upgrade_retry_interval_ms", 1200)
        confirm = self.ctx.execution("upgrade_confirm_wait_ms", 400)
        deadline = time.monotonic() + timeout
        while True:
            self.ctx.check_stop()
            self.action(rect, "upgrade")
            self.ctx.drv.wait(confirm)
            if vcap.region_changed(before, self.level_shot(rect)):
                return True   # a level was bought
            # No change: maxed, or can't afford the next level yet?
            lvl = self._read_level(rect)
            if lvl and lvl[0] >= lvl[1]:
                return False   # maxed - stop now instead of waiting out the timeout
            if time.monotonic() >= deadline:
                return False
            self.ctx.drv.wait(interval)

    def _open_panel(self, rect, sx, sy, step) -> bool:
        """Select the unit and refuse to work on empty ground. Shared by the
        upgrade and sell paths, so the message stays action-neutral."""
        opened = self.select_verified(rect, sx, sy)
        if opened is False:
            self.ctx.log(f"Step {step.id}: no unit at {step.x:.3f}, "
                         f"{step.y:.3f} — skipping (its placement likely "
                         "failed).")
            return False
        return True

    def upgrade_times(self, rect, sx, sy, step, times: int):
        """Buy N levels, each one verified by the readout changing. Stops early
        if the unit maxes out before N - upgrade_once returns False once a level
        can't be bought (maxed, per the N/M read on no-change)."""
        if not self._open_panel(rect, sx, sy, step):
            return
        n = max(1, times)
        for i in range(n):
            self.ctx.check_stop()
            if not self.upgrade_once(rect, step):
                self.ctx.log(f"Step {step.id}: upgraded {i} of {n} levels — "
                             "the next one wouldn't apply (maxed out, or "
                             "couldn't afford it in time).")
                return
        self.ctx.log(f"Step {step.id}: upgraded {n}×.")

    def upgrade_max(self, rect, sx, sy, step):
        """Buy levels until the unit is maxed.

        Each iteration buys one level (upgrade_once), which returns False the
        moment a level can't be bought - a readout that won't change AND an N/M
        read of N>=M (see upgrade_once). The max check lives THERE, not as a
        top-of-loop pre-check, so a misread max ("5/8" -> "5/5") can't stop the
        loop early: a buyable level changes the readout and is counted first."""
        if not self._open_panel(rect, sx, sy, step):
            return
        cap = self.ctx.execution("max_upgrade_clicks", 30)
        got = 0
        for _ in range(cap):
            self.ctx.check_stop()
            if not self.upgrade_once(rect, step):
                break
            got += 1
        lvl = self._read_level(rect)
        where = f" (now {lvl[0]}/{lvl[1]})" if lvl else ""
        tail = " — reached the upgrade limit" if got >= cap else ""
        self.ctx.log(f"Step {step.id}: upgraded to max — bought {got} levels{where}{tail}.")

    # ---------------- selling ----------------

    def sell(self, rect, sx, sy, step):
        """Select the unit, hit Sell, then confirm if a confirm dialog is
        calibrated. confirm_btn is still an unmeasured guess - no sell-confirm
        dialog has ever been captured (HANDOFF 2.18).

        Goes through _open_panel (not a bare select) so a sell that lands with
        a leftover panel open doesn't toggle THAT panel shut and sell nothing -
        the same toggle trap the priority/upgrade paths guard against."""
        if not self._open_panel(rect, sx, sy, step):
            return
        self.action(rect, "sell")
        self.ctx.drv.wait(150)
        self.ctx.click_anchor(rect, "confirm_btn")
