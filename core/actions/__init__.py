"""Step actions, one class per profile action type.

Adding a new action means adding a module here and listing its class in
ACTION_CLASSES - no dispatch code to edit anywhere else.
"""

from .base import StepAction, Target
from .ability import AbilityAction
from .click import ClickAction
from .place import PlaceAction
from .sell import SellAction
from .upgrade import UpgradeAction
from .wait import WaitAction

ACTION_CLASSES = (PlaceAction, ClickAction, UpgradeAction, SellAction,
                  AbilityAction, WaitAction)

__all__ = ["StepAction", "Target", "ACTION_CLASSES", "build_actions",
           "PlaceAction", "ClickAction", "UpgradeAction", "SellAction",
           "AbilityAction", "WaitAction"]


def build_actions(ctx, panel) -> dict:
    """{action name: handler} for one run."""
    return {cls.name: cls(ctx, panel) for cls in ACTION_CLASSES}
