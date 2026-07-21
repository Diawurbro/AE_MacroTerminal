"""Running one profile step: satisfy its precondition, then dispatch to the
action that owns it."""

from core import ocr
from core.actions import Target, build_actions


class PreconditionWaiter:
    """Blocks until a step's `wait` condition is met, or the timeout expires.

    Preconditions are the whole defence against the classic failure of this
    kind of macro - clicking to place when cash is insufficient, which
    desynchronizes everything after it (HANDOFF 2.6).

    A timeout logs and RETURNS rather than aborting: a stalled OCR read
    shouldn't kill an otherwise fine run, and the placement itself is
    separately verified.
    """

    def __init__(self, ctx):
        self.ctx = ctx

    def wait_for(self, step, rect):
        w = step.wait
        if w.type == "none":
            return
        if w.type == "delay":
            self.ctx.drv.wait(w.value)
            return

        roi, read = self._reader_for(w.type)
        if not roi:
            self.ctx.log(f"#{step.id} {w.label()}: that HUD region isn't "
                         "calibrated - continuing without waiting.")
            return

        def satisfied():
            val = read(self.ctx.cap.grab_roi(rect, roi))
            return val is not None and val >= w.value

        if not self.ctx.poll_until(satisfied, self.ctx.execution("wait_timeout_s", 30)):
            self.ctx.log(f"Timed out waiting for {w.label()}.")

    def _reader_for(self, wait_type: str):
        """(roi, reader) for a wait type. Which OCR reader matters: the wave
        pill reads "<current> / <total>", so joining its digit groups the way
        read_int does returns e.g. 315 for "3 / 15" and every `wave >= N`
        gate passes on the first poll (HANDOFF 2.12)."""
        if wait_type == "cash":
            return self.ctx.anchor("cash_roi"), ocr.read_int
        return self.ctx.anchor("wave_roi"), ocr.read_leading_int


class StepRunner:
    def __init__(self, ctx, panel):
        self.ctx = ctx
        self.precondition = PreconditionWaiter(ctx)
        self.actions = build_actions(ctx, panel)

    def run(self, step, rect):
        wait_note = (f" (waiting: {step.wait.label()})"
                     if step.wait.type != "none" else "")
        self.ctx.log(f"Step #{step.id}: {step.summary()}{wait_note}")

        self.precondition.wait_for(step, rect)
        self.ctx.check_stop()

        target = self._resolve(step, rect)
        action = self.actions.get(step.action)
        if action is None:
            self.ctx.log(f"#{step.id} unknown action {step.action!r} - skipped.")
        else:
            action.execute(step, rect, target)

        if step.note:
            self.ctx.log(f"#{step.id} {step.summary()} - {step.note}")
        self.ctx.drv.gap()

    def _resolve(self, step, rect) -> Target:
        """Upgrade/sell steps act on another step's marker, not their own
        coordinates - Step.anchor() resolves that, so moving a placement
        marker automatically moves everything targeting it (HANDOFF 2.7)."""
        ax, ay = step.anchor(self.ctx.profile.steps)
        sx, sy = rect.to_screen(ax, ay)
        return Target(ax=ax, ay=ay, sx=sx, sy=sy)
