"""Arming a hotbar unit slot.

Default path (game.use_unit_keys, HANDOFF 2.38): tap the slot's NUMBER KEY.
A keypress is atomic - a card click that lands a few px off or gets eaten by
an overlay silently fails to arm and the placement stalls, which happened on
real runs. (2.22 removed keys entirely; this reverses that for unit actions
at the user's request, after those click drops caused losses.)

Fallback path (use_unit_keys: false): click the card's position. The bar is
CENTRE-anchored - it grows outwards from the middle of the client area, so
slot 1's x depends on how many units the loadout carries; the geometry is
stored as centre/spacing/count and each slot's position derived from it.
Change `game.hotbar.slot_count` when the loadout size changes and every slot
moves with it. Defaults measured off a real 1280x720 capture (6 units): card
centres 77.4px apart at y=650, symmetric about x=640.

Either way, slot_count bounds which slots exist - a key for a card that
isn't in the loadout would arm nothing (or the wrong thing), same as a click.
"""


class Hotbar:
    def __init__(self, ctx):
        self.ctx = ctx

    def _geom(self) -> dict:
        return self.ctx.game("hotbar", {}) or {}

    def position(self, slot: int) -> tuple[float, float] | None:
        """Normalized centre of a 1-based slot, or None if it can't be placed.

        An explicit `slots` list wins when present - a loadout whose bar
        doesn't follow the even-spacing assumption (a different UI scale, a
        stage that adds a special card) can be pinned coordinate by
        coordinate without touching this."""
        g = self._geom()
        explicit = g.get("slots") or []
        if explicit:
            if 1 <= slot <= len(explicit):
                x, y = explicit[slot - 1]
                return float(x), float(y)
            self.ctx.log(f"Hotbar slot {slot} isn't in your loadout "
                         f"({len(explicit)} units) — skipping it.")
            return None

        count = int(g.get("slot_count", 6))
        if not 1 <= slot <= count:
            self.ctx.log(f"Hotbar slot {slot} isn't in your {count}-unit "
                         "loadout — skipping it.")
            return None
        spacing = float(g.get("spacing", 0.0605))
        cx = float(g.get("center_x", 0.5))
        y = float(g.get("y", 0.903))
        return cx + (slot - (count + 1) / 2) * spacing, y

    def _slot_count(self) -> int:
        g = self._geom()
        return len(g.get("slots") or []) or int(g.get("slot_count", 6))

    def select(self, rect, slot: int, settle_ms: int = 120) -> bool:
        """Arm a unit slot - number key by default, card click as the fallback.
        Returns False if the slot isn't in the bar, so a caller doesn't go on
        to click the map with nothing armed."""
        if self.ctx.game("use_unit_keys", True):
            if not 1 <= slot <= min(9, self._slot_count()):
                self.ctx.log(f"Hotbar slot {slot} isn't in your "
                             f"{self._slot_count()}-unit loadout — "
                             "skipping it.")
                return False
            self.ctx.drv.tap(str(slot))
            self.ctx.drv.wait(settle_ms)
            return True

        pos = self.position(slot)
        if pos is None:
            return False
        sx, sy = rect.to_screen(*pos)
        self.ctx.drv.click(sx, sy)
        self.ctx.drv.wait(settle_ms)
        return True
