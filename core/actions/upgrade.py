"""Upgrading a unit that an earlier step placed.

This is its OWN row in the editor now, sitting at the same position as the
placement it upgrades (HANDOFF 2.27): the run clicks that spot to select the
unit, then buys levels there. The position comes from Step.anchor(), so a row
can either carry the coordinates itself or point at another step via
target_step - in which case moving that placement's marker moves this with it
(HANDOFF 2.7).
"""

from .base import StepAction, Target


class UpgradeAction(StepAction):
    name = "upgrade"

    def execute(self, step, rect, target: Target):
        if step.upgrade_mode == "max":
            self.panel.upgrade_max(rect, target.sx, target.sy, step)
        else:
            self.panel.upgrade_times(rect, target.sx, target.sy, step, step.times)
        # Leave the map clear for the next step - upgrading ends with the
        # unit's panel still open over it.
        self.panel.deselect(rect)
