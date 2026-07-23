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

    def probe_color(self, rect, point, radius: float = 0.004):
        """Mean (r, g, b) of a small patch centred on a normalized point, or
        None if it can't be read. Averaged rather than single-pixel so one
        stray antialiased pixel can't decide anything."""
        x, y = point
        roi = [max(0.0, x - radius), max(0.0, y - radius),
               min(1.0, x + radius), min(1.0, y + radius)]
        patch = self.cap.grab_roi(rect, roi)
        if patch is None or patch.size == 0:
            return None
        b, g, r = patch.reshape(-1, 3).mean(axis=0)   # capture is BGR
        return float(r), float(g), float(b)

    @property
    def can_check_panel(self) -> bool:
        """True when panel_shows_unit() has something to go on at all -
        either the colour probe (preferred) or the per-loop empty-panel
        baseline. Callers use this to choose between the panel check and
        their weaker fallback, so it has to cover BOTH mechanisms: gating on
        the baseline alone would silently ignore a profile that only has the
        probe calibrated."""
        if self.anchor("panel_probe") and self.anchor("panel_probe_rgb"):
            return True
        return self.panel_empty is not None

    def panel_shows_unit(self, rect) -> bool:
        """Is a unit selected right now?

        Primary check is a COLOUR PROBE: one small patch at a fixed spot on
        the unit panel (panel_probe) compared against the colour that spot
        shows while the panel is open (panel_probe_rgb). The panel's own
        controls are big flat blocks of saturated colour that nothing on the
        map matches, so this is a direct "is the panel there" reading.

        It replaces diffing the level readout against a per-loop empty-panel
        baseline, which was indirect and fragile in both directions: an
        overlay drifting across the readout (an ability tooltip, a floating
        damage number) read as "a unit is selected" when none was, and a
        baseline captured a frame early read as "no unit" when one was
        plainly there - the reported "no unit at x, y - skipping" on a unit
        that had just been placed successfully. The reference macro this is
        modelled on (Cys) probes a single panel pixel for exactly this
        reason.

        Falls back to the old baseline diff when panel_probe isn't calibrated,
        so profiles saved before this existed keep working unchanged."""
        probe = self.anchor("panel_probe")
        want = self.anchor("panel_probe_rgb")
        if probe and want:
            got = self.probe_color(rect, probe)
            if got is None:
                return False
            tol = self.execution("panel_probe_tolerance", 60)
            return all(abs(a - b) <= tol for a, b in zip(got, want))

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
