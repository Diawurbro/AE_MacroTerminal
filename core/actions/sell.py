"""Selling a placed unit."""

from .base import StepAction, Target


class SellAction(StepAction):
    name = "sell"

    def execute(self, step, rect, target: Target):
        self.panel.sell(rect, target.sx, target.sy)
