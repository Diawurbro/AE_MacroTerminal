"""A step that only waits.

Intentionally empty: the wait itself is the step's PRECONDITION, which
StepRunner already satisfied before dispatching here. This class exists so
dispatch stays uniform - every action name maps to a handler, with no
special case for "the one that does nothing".
"""

from .base import StepAction, Target


class WaitAction(StepAction):
    name = "wait"

    def execute(self, step, rect, target: Target):
        return
