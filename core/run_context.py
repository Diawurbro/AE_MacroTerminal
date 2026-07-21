"""Services and config shared by every stage of a run.

Every helper used to hang off Executor and reach into `self` for cfg /
profile / drv / cap / log - which is exactly why that class grew past 600
lines and resisted being split. Bundling the shared state here lets
UnitPanel, the step actions, StageSetup and MatchFlow be independent
classes in their own files: each is constructible with a fake context in a
test, instead of needing a fake Executor.

Collaborators HOLD a context rather than inheriting from one, deliberately -
so none of them can reach into another's internals by accident.
"""

import time

from vision import capture as vcap


class StopRequested(Exception):
    """Raised internally to unwind out of a run cleanly on stop/emergency stop."""


class RunContext:
    def __init__(self, cfg, profile, drv, cap, log, check_stop):
        self.cfg = cfg
        self.profile = profile
        self.drv = drv
        self.cap = cap
        self.log = log                # callable(str)
        self.check_stop = check_stop  # callable, raises StopRequested
        # What the unit panel's level readout looks like with NOTHING
        # selected, captured once per loop by StageSetup. Every "is a unit
        # there?" check compares against this fixed picture rather than
        # against whatever was on screen a moment ago - see HANDOFF 2.30 for
        # what a relative baseline does when a panel is left open or the
        # screen is still mid-transition. None = not calibrated/unavailable.
        self.panel_empty = None

    # ---------------- config sections ----------------

    def execution(self, key, default=None):
        return self.cfg.get("execution", {}).get(key, default)

    def game(self, key, default=None):
        return self.cfg.get("game", {}).get(key, default)

    def vision(self, key, default=None):
        return self.cfg.get("vision", {}).get(key, default)

    def poll_seconds(self) -> float:
        return self.vision("poll_interval_ms", 400) / 1000.0

    # ---------------- profile anchors ----------------

    @property
    def anchors(self) -> dict:
        return self.profile.ui_anchors

    def anchor(self, name, default=None):
        return self.anchors.get(name, default)

    def click_anchor(self, rect, name) -> bool:
        """Click a normalized [x, y] anchor. Returns False WITHOUT clicking if
        the anchor isn't set, so an uncalibrated profile degrades to a no-op
        rather than clicking (0, 0) - which on this UI is the Roblox menu."""
        pos = self.anchor(name)
        if not pos:
            return False
        x, y = rect.to_screen(*pos)
        self.drv.click(x, y)
        return True

    def grab_anchor(self, rect, name, default=None):
        """Capture a normalized [x1, y1, x2, y2] anchor region, or None if
        that anchor isn't set."""
        roi = self.anchor(name, default)
        if not roi:
            return None
        return self.cap.grab_roi(rect, roi)

    def panel_shows_unit(self, rect) -> bool:
        """Is a unit selected right now? False when there's no baseline to
        compare against, so an uncalibrated profile falls back to the map
        check instead of guessing."""
        if self.panel_empty is None:
            return False
        cur = self.grab_anchor(rect, "upgrade_level_roi")
        return cur is not None and vcap.region_changed(self.panel_empty, cur)

    # ---------------- capture helpers ----------------

    def settle_roi(self, rect, roi, interval_ms=250, tries=6):
        """Read an ROI until two consecutive reads agree. Returns
        (image, settled) - the last read either way, so a caller always has
        something to work with."""
        prev = self.cap.grab_roi(rect, roi)
        for _ in range(tries):
            self.check_stop()
            self.drv.wait(interval_ms)
            cur = self.cap.grab_roi(rect, roi)
            if not vcap.region_changed(prev, cur):
                return cur, True
            prev = cur
        return prev, False

    # ---------------- polling ----------------

    def poll_until(self, predicate, timeout_s, poll_s=None):
        """Call predicate() until it returns something truthy or the timeout
        expires; returns that value, or None on timeout.

        Checks for a stop request between polls, so every wait in a run stays
        interruptible by the Stop button / F12 rather than blocking shutdown
        for up to result_timeout_s.
        """
        poll_s = self.poll_seconds() if poll_s is None else poll_s
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            self.check_stop()
            got = predicate()
            if got:
                return got
            time.sleep(poll_s)
        return None
