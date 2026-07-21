"""Where the hotbar's unit slots are on screen.

A slot used to be armed by tapping its number key (1-6). Nothing this macro
sends to the game is a keystroke anymore (HANDOFF 2.22), so a slot now has
to resolve to a POSITION.

The bar is CENTRE-anchored: it grows outwards from the middle of the client
area, so slot 1's x depends on how many units the loadout carries. Measuring
one loadout and hard-coding six coordinates would silently mis-click every
loadout with a different unit count - which is why the geometry is stored as
centre/spacing/count and each slot's position is derived from it. Change
`game.hotbar.slot_count` when the loadout size changes and every slot moves
with it.

Defaults measured off a real 1280x720 capture (6 units): card centres at
x = 445.5, 523, 600.5, 677.5, 755, 832.5 and y = 650 - i.e. 77.4px apart,
symmetric about x = 640.
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
            self.ctx.log(f"Hotbar slot {slot} is outside game.hotbar.slots "
                         f"({len(explicit)} entries) - skipping the select click.")
            return None

        count = int(g.get("slot_count", 6))
        if not 1 <= slot <= count:
            self.ctx.log(f"Hotbar slot {slot} is outside the {count}-slot bar "
                         "(game.hotbar.slot_count) - skipping the select click.")
            return None
        spacing = float(g.get("spacing", 0.0605))
        cx = float(g.get("center_x", 0.5))
        y = float(g.get("y", 0.903))
        return cx + (slot - (count + 1) / 2) * spacing, y

    def select(self, rect, slot: int, settle_ms: int = 120) -> bool:
        """Arm a unit slot by clicking its card. Returns False if the slot
        couldn't be resolved, so a caller doesn't go on to click the map with
        nothing armed."""
        pos = self.position(slot)
        if pos is None:
            return False
        sx, sy = rect.to_screen(*pos)
        self.ctx.drv.click(sx, sy)
        self.ctx.drv.wait(settle_ms)
        return True
