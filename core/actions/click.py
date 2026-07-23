"""A bare click at a marker's position - no unit placed, no panel logic.

Unit = none (slot 0): a plain click - dismiss a popup, hit a stage button,
click to deselect, or trigger something at a spot. Nothing is armed, so it
can't place a unit.

Unit = a slot (1..N): arm that hotbar card first, then click - i.e. drop a
unit WITHOUT the placement machinery a real 'place' step brings (verification,
retry, priority/upgrade). Rare; 'place' is the robust way to put a unit down.
"""

from .base import StepAction, Target


class ClickAction(StepAction):
    name = "click"

    def execute(self, step, rect, target: Target):
        if step.slot and step.slot >= 1:
            if not self.hotbar.select(rect, step.slot, settle_ms=100):
                self.ctx.log(f"Step {step.id}: slot {step.slot} isn't in your "
                             "loadout — clicking without a unit.")
        self.ctx.drv.click(target.sx, target.sy)
