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
        it reports a unit exactly when there isn't one (HANDOFF 2.30)."""
        if self.ctx.panel_empty is None:
            self.select(sx, sy)
            return None
        if self.ctx.panel_shows_unit(rect):
            # Whatever is selected was selected by an earlier step and is not
            # necessarily the unit at this spot - it would answer for it.
            self.deselect(rect)
        self.select(sx, sy)
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
        # when you click away from a unit, and unlike deselect_btn that
        # doesn't depend on an anchor being calibrated right. Safe because no
        # hotbar card is ever armed here: arming is immediately followed by
        # its placement click.
        self.ctx.drv.click(*rect.to_screen(
            *self.ctx.execution("cursor_park", [0.02, 0.5])))
        self.ctx.drv.wait(120)
        if self.ctx.panel_shows_unit(rect) and not self._warned_deselect:
            self._warned_deselect = True
            self.ctx.log("The unit panel won't close - deselect_btn looks "
                         "mis-calibrated (Calibrate tab > 'Unit panel close "
                         "(X)') and clicking bare ground didn't do it either. "
                         "It will sit over the map.")

    # ---------------- the three action buttons ----------------

    def action(self, rect, name: str):
        """Trigger the selected unit's Upgrade / Sell / Priority control.

        Clicks the measured ui_anchors position. The panel does print a
        keybind badge on each button ([T]/[X]/[R]) and there used to be a
        game.use_unit_keys escape hatch that pressed those instead; it's gone
        (HANDOFF 2.22) - this macro sends no keystrokes to the game at all
        now, so there is one code path here and it's the one that gets
        exercised on every run.

        Requires a unit to already be selected; does nothing otherwise."""
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
            self.ctx.log(f"#{step.id} priority '{step.priority}': no unit at "
                         f"{step.x:.3f}, {step.y:.3f} - skipping (the placement "
                         "for this spot probably failed).")
            return
        label_roi = self.ctx.anchor("priority_label_roi")
        target = step.priority

        if not ocr.HAS_TESSERACT or not label_roi:
            reason = ("Tesseract not installed" if not ocr.HAS_TESSERACT
                      else "priority_label_roi not calibrated")
            self.ctx.log(f"#{step.id} priority '{target}': {reason} - "
                         "activating once, unverified.")
            self.action(rect, "priority")
            self.ctx.drv.wait(150)
            return

        def read():
            word = ocr.read_word(self.ctx.cap.grab_roi(rect, label_roi))
            return (word or "").strip().lower()

        if read() == target.lower():
            self.ctx.log(f"#{step.id} priority already '{target}'.")
            return

        limit = max(1, len(PRIORITY_TYPES))
        cur = None
        for _ in range(limit):
            self.ctx.check_stop()
            self.action(rect, "priority")
            self.ctx.drv.wait(150)
            cur = read()
            if cur == target.lower():
                self.ctx.log(f"#{step.id} priority -> {target}.")
                return
        self.ctx.log(f"#{step.id} priority '{target}' not reached after "
                     f"{limit} attempt(s) (last read: {cur!r}) - PRIORITY_TYPES "
                     "may not match this game's actual options.")

    # ---------------- upgrading ----------------

    def upgrade_once(self, rect, step) -> bool:
        """Buy exactly ONE level: click Upgrade until the panel's level
        readout actually changes.

        "Nothing happened" almost always means "can't afford the next level
        yet", which is a wait, not a failure - so it keeps clicking on a slow
        interval instead of moving on (the user's ask: click until it
        upgrades). execution.upgrade_timeout_s is only the give-up guard, and
        reaching it is the signal for "maxed out, or never affordable".

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
                return True
            if time.monotonic() >= deadline:
                return False
            self.ctx.drv.wait(interval)

    def _open_panel(self, rect, sx, sy, step) -> bool:
        """Select the unit and refuse to work on empty ground. Shared by the
        upgrade and sell paths, so the message stays action-neutral."""
        opened = self.select_verified(rect, sx, sy)
        if opened is False:
            self.ctx.log(f"#{step.id}: no unit at {step.x:.3f}, {step.y:.3f} - "
                         "skipping (the placement for this spot probably "
                         "failed).")
            return False
        return True

    def upgrade_times(self, rect, sx, sy, step, times: int):
        """Buy N levels, each one verified before counting it."""
        if not self._open_panel(rect, sx, sy, step):
            return
        n = max(1, times)
        for i in range(n):
            self.ctx.check_stop()
            if not self.upgrade_once(rect, step):
                self.ctx.log(f"#{step.id} upgrade: got {i} of {n} level(s) - "
                             "the next one never applied (maxed out, or not "
                             "affordable within execution.upgrade_timeout_s).")
                return
        self.ctx.log(f"#{step.id} upgraded x{n}.")

    def upgrade_max(self, rect, sx, sy, step):
        """Keep buying levels until one doesn't apply - that is what "maxed
        out or unaffordable" looks like from the outside.

        Replaces the spam-click version (HANDOFF 2.19), which fired
        max_upgrade_clicks clicks blind and reported nothing about what it
        bought. That was the right call when there was no signal to read;
        the level readout diff is one, and it needs no Tesseract."""
        if not self._open_panel(rect, sx, sy, step):
            return
        cap = self.ctx.execution("max_upgrade_clicks", 30)
        got = 0
        for _ in range(cap):
            self.ctx.check_stop()
            if not self.upgrade_once(rect, step):
                break
            got += 1
        tail = " (hit execution.max_upgrade_clicks)" if got >= cap else ""
        self.ctx.log(f"#{step.id} upgrade-to-max: bought {got} level(s){tail}.")

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
