"""Base class and shared types for the per-action step handlers."""

from abc import ABC, abstractmethod
from typing import NamedTuple

from core.hotbar import Hotbar


class Target(NamedTuple):
    """A step's resolved position, in both coordinate systems.

    Upgrade/sell steps point at another step's marker (Step.anchor), so this
    is the RESOLVED position, not necessarily the step's own x/y. Both forms
    are carried because they're both needed: screen pixels to click, and the
    normalized pair to build the placement-verification ROI from.
    """
    ax: float   # normalized 0-1
    ay: float
    sx: int     # screen pixels
    sy: int


class StepAction(ABC):
    """One profile action type, as executable behaviour.

    Replaces the if/elif chain that used to live in Executor._run_step. Each
    subclass owns exactly one action, so changing how placement works can't
    disturb selling, and each can be exercised on its own with a fake context.
    """

    #: the data.profile.ACTIONS name this class handles
    name: str = ""

    def __init__(self, ctx, panel):
        self.ctx = ctx
        self.panel = panel
        self.hotbar = Hotbar(ctx)

    @abstractmethod
    def execute(self, step, rect, target: Target):
        """Perform this step's action. The precondition wait and the
        stop-check have already happened; the note log and inter-step gap
        happen after, both handled by StepRunner."""
