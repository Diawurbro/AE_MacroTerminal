"""Firing a hotbar ability at a map position."""

from .base import StepAction, Target


class AbilityAction(StepAction):
    name = "ability"

    def execute(self, step, rect, target: Target):
        # Same arm-then-click shape as placement, but abilities are fire-and-
        # forget: there's no persistent object left behind to verify against,
        # so there's nothing for a region-diff to check.
        if not self.hotbar.select(rect, step.slot, settle_ms=100):
            self.ctx.log(f"#{step.id} ability skipped - hotbar slot "
                         f"{step.slot} has no position.")
            return
        self.ctx.drv.click(target.sx, target.sy)
