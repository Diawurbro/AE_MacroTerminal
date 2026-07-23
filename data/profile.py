"""Stage profile: reference image + numbered marker steps."""

import json
import os
from dataclasses import dataclass, field, fields, asdict

ACTIONS = ["place", "click", "upgrade", "sell", "ability", "wait"]
WAIT_TYPES = ["none", "cash", "wave", "delay"]
MAX_STEPS = 100

# Target priority set right after a 'place' step, if the unit supports it.
# The priority button is a CYCLE, read back via OCR (see UnitPanel.set_priority).
# CONFIRMED against the real game from live captures (2026-07-22): the button
# cycles First -> Last -> Closest -> Strongest -> Boss -> Weakest -> Shielded
# -> Fastest -> None -> (wraps). All nine labels render as plain words and read
# cleanly. "none" is kept first as the default; the cycle order in this list
# doesn't have to match the game's - set_priority cycles and re-reads until the
# label matches, bounded by len(PRIORITY_TYPES), so what matters is that every
# real option is present (an earlier 7-entry guess with a bogus "farthest"
# could not reach Shielded/Fastest/None at all).
PRIORITY_TYPES = ["none", "first", "last", "closest", "strongest",
                  "boss", "weakest", "shielded", "fastest"]

# Bundled onto a 'place' step: "off" does nothing extra, "times" clicks
# upgrade_btn Step.times times, "max" clicks it until cash stops moving
# (core/executor.py) instead of a fixed count.
UPGRADE_MODES = ["off", "times", "max"]


@dataclass
class WaitCond:
    type: str = "none"      # none | cash | wave | delay
    value: int = 0          # amount / wave number / milliseconds

    def label(self) -> str:
        if self.type == "cash":
            return f"cash >= {self.value}"
        if self.type == "wave":
            return f"wave >= {self.value}"
        if self.type == "delay":
            return f"delay {self.value}ms"
        return "immediate"


@dataclass
class Step:
    id: int
    action: str = "place"
    x: float = 0.5              # normalized 0-1 in client area
    y: float = 0.5
    slot: int = 1               # hotbar slot for 'place'; 0 = none (no unit armed)
    times: int = 1              # repeat count for 'upgrade', or for 'place' when upgrade_mode="times"
    target_step: int | None = None   # 'upgrade'/'sell' reference another marker
    wait: WaitCond = field(default_factory=WaitCond)
    note: str = ""
    priority: str = "none"      # 'place' only - targeting priority to set after placing
    upgrade_mode: str = "off"   # 'place' only - "off" | "times" | "max"

    def anchor(self, steps: list["Step"]) -> tuple[float, float]:
        """Upgrade/sell click the position of their target step, not their own."""
        if self.target_step is not None:
            for s in steps:
                if s.id == self.target_step:
                    return s.x, s.y
        return self.x, self.y

    def summary(self) -> str:
        if self.action == "place":
            extra = []
            if self.priority != "none":
                extra.append(self.priority)
            if self.upgrade_mode == "times":
                extra.append(f"upg x{self.times}")
            elif self.upgrade_mode == "max":
                extra.append("upg max")
            tail = f" ({', '.join(extra)})" if extra else ""
            return f"place unit slot {self.slot}{tail}"
        if self.action == "click":
            return "click" if not self.slot else f"click (arm unit {self.slot})"
        if self.action == "upgrade":
            tgt = f" -> #{self.target_step}" if self.target_step else ""
            what = "to max" if self.upgrade_mode == "max" else f"x{self.times}"
            return f"upgrade {what}{tgt}"
        if self.action == "sell":
            return f"sell -> #{self.target_step}"
        if self.action == "ability":
            return f"ability slot {self.slot}"
        return "wait"


@dataclass
class StageProfile:
    stage: str = "Untitled stage"
    reference_image: str = ""
    # No per-stage camera settings - core/camera.py drives zoom and pitch to
    # hard clamps every time, so the same sequence works for every stage.
    ui_anchors: dict = field(default_factory=lambda: {
        # cash_roi / wave_roi are MEASURED off a real 1280x720 capture
        # (profiles/test_ref.png), not guessed like the rest below.
        # cash: the gold "¥ N" readout at bottom-centre, above the hotbar.
        # VERIFIED across 4/5/6-digit live captures (2026-07-22): the number is
        # LEFT-anchored just right of the coin icon (which ends ~x0.473) and
        # grows RIGHTWARD as it gets longer - it does NOT recentre. Measured
        # spans: "2,003" 0.483-0.528, "113,498" 0.480-0.536. The prior default
        # started at x0.492 and CLIPPED the leading digit of any 5+-digit value
        # (read "13,498" for "113,498"), silently breaking every `cash >=` wait.
        # Left edge now clears the coin; right edge covers 6 digits with margin.
        # A 7-digit value (rare) would clip on the right - widen then if seen.
        "cash_roi": [0.474, 0.807, 0.552, 0.840],
        # wave: covers the whole "<current> / <total>" text but starts just
        # right of the compass icon (x~543). Reading it needs
        # ocr.read_leading_int, NOT read_int - see that function's docstring.
        "wave_roi": [0.425, 0.033, 0.456, 0.056],
        # MEASURED off a real selected-unit capture. The unit panel sits at the
        # BOTTOM-LEFT of the client area - these used to be at x=0.86 (the
        # right edge), i.e. wrong by nearly the full screen width. All three
        # action buttons share one row at y=0.623.
        # These are clicked, always - the macro sends no keystrokes to the
        # game, so the [T]/[X]/[R] badges the panel prints are decoration
        # here (HANDOFF 2.22).
        "upgrade_btn": [0.216, 0.623],
        "sell_btn": [0.126, 0.623],
        "priority_btn": [0.061, 0.623],
        # The panel's red close button. Clicking it is the safe way to deselect
        # a unit so its panel stops covering the map before the next placement
        # click - tapping Escape is NOT safe, Roblox opens its own game menu.
        "deselect_btn": [0.318, 0.325],
        # "Upgrade N/M" caption above the upgrade button (MEASURED, confirmed
        # on two different units: "0/3" and "0/8"). Read with ocr.read_fraction,
        # NOT read_int - see that function's docstring for why. Full button
        # width so a longer M ("0/12") isn't clipped.
        "upgrade_level_roi": [0.1586, 0.585, 0.2766, 0.607],
        # The priority button's own current-selection text ("None", "First",
        # ...) - MEASURED, confirmed on two captures. Confined to the priority
        # button's own width so it can't pick up the Sell button's "¥xxx" text
        # sitting immediately to its right. Read with ocr.read_word (letters,
        # not digits). See _set_priority in core/executor.py: this button
        # turned out to be a CYCLE, not a menu, so there is no per-option
        # coordinate to click - priority_options is retired.
        "priority_label_roi": [0.0289, 0.600, 0.0961, 0.645],
        # Where the post-match "(Click anywhere to close) [N/M]" caption sits.
        # Measured across 5 real reward screens (caption at y 0.922-0.940,
        # horizontally centred); padded so it survives a few px of window
        # width variation. Only the search region - the match itself is a
        # template (vision/reward_screen.py).
        "reward_strip_roi": [0.36, 0.90, 0.64, 0.96],
        # Result screen (MEASURED). Next Stage / Repeat Stage / View Party all
        # sit on one row at y=0.790; repeat_btn is the middle one. The search
        # band is deliberately wider than the button so a few px of panel
        # drift can't hide it.
        "repeat_btn": [0.375, 0.790],
        "result_screen_roi": [0.15, 0.70, 0.70, 0.88],
        # The Victory ribbon at the panel's top-left. NOTE it is BLUE, so
        # result_detector's green-vs-red colour fallback cannot classify this
        # game - win/loss goes through victory.png instead.
        "result_roi": [0.15, 0.15, 0.37, 0.22],
        # Still unmeasured - no sell-confirm dialog has been captured yet.
        "confirm_btn": [0.50, 0.72],
    })
    steps: list[Step] = field(default_factory=list)

    # ---------- step management ----------

    def next_id(self) -> int:
        return max((s.id for s in self.steps), default=0) + 1

    def add_step(self, x: float, y: float) -> Step | None:
        if len(self.steps) >= MAX_STEPS:
            return None
        s = Step(id=self.next_id(), x=x, y=y)
        self.steps.append(s)
        return s

    def remove_step(self, step_id: int):
        self.steps = [s for s in self.steps if s.id != step_id]
        for s in self.steps:
            if s.target_step == step_id:
                s.target_step = None

    def get(self, step_id: int) -> Step | None:
        return next((s for s in self.steps if s.id == step_id), None)

    def move(self, index: int, delta: int):
        j = index + delta
        if 0 <= j < len(self.steps):
            self.steps[index], self.steps[j] = self.steps[j], self.steps[index]

    # ---------- persistence ----------

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    def save(self, path: str):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, path: str) -> "StageProfile":
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        steps = []
        for sd in d.get("steps", []):
            wd = sd.pop("wait", {}) or {}
            steps.append(Step(wait=WaitCond(**wd), **sd))
        d["steps"] = steps
        # Drop keys from an older schema (e.g. the retired per-stage
        # "camera" block) instead of erroring on an unknown kwarg.
        known = {f.name for f in fields(cls)}
        d = {k: v for k, v in d.items() if k in known}
        return cls(**d)


# Anchor defaults shipped by earlier builds. Kept only so is_default_anchors()
# can still recognise a profile saved back then as uncalibrated.
RETIRED_DEFAULT_ANCHORS = [
    # Interim set: unit-panel buttons + deselect/reward/result-screen anchors
    # all measured, but priority still modeled as a coordinate menu
    # (priority_options) and no upgrade_level_roi/priority_label_roi yet -
    # both replaced by OCR reads once the priority button turned out to be a
    # cycle, not a menu (HANDOFF 2.14/2.18).
    {
        "cash_roi": [0.492, 0.805, 0.547, 0.842],
        "wave_roi": [0.425, 0.033, 0.456, 0.056],
        "upgrade_btn": [0.216, 0.623],
        "sell_btn": [0.126, 0.623],
        "priority_btn": [0.061, 0.623],
        "deselect_btn": [0.318, 0.325],
        "reward_strip_roi": [0.36, 0.90, 0.64, 0.96],
        "repeat_btn": [0.375, 0.790],
        "result_screen_roi": [0.15, 0.70, 0.70, 0.88],
        "result_roi": [0.15, 0.15, 0.37, 0.22],
        "confirm_btn": [0.50, 0.72],
        "priority_options": {
            "first": [0.80, 0.20], "last": [0.86, 0.20],
            "strongest": [0.80, 0.26], "weakest": [0.86, 0.26],
            "closest": [0.80, 0.32], "farthest": [0.86, 0.32],
        },
    },
    # Interim set: cash/wave measured, but the unit-panel buttons still at the
    # right edge. Short-lived, but profiles were saved against it.
    {
        "cash_roi": [0.492, 0.805, 0.547, 0.842],
        "wave_roi": [0.425, 0.033, 0.456, 0.056],
        "upgrade_btn": [0.86, 0.42],
        "confirm_btn": [0.50, 0.72],
        "sell_btn": [0.86, 0.52],
        "result_roi": [0.30, 0.35, 0.70, 0.65],
        "priority_btn": [0.86, 0.32],
        "priority_options": {
            "first": [0.80, 0.20], "last": [0.86, 0.20],
            "strongest": [0.80, 0.26], "weakest": [0.86, 0.26],
            "closest": [0.80, 0.32], "farthest": [0.86, 0.32],
        },
    },
    # The original all-guesses set.
    {
        "cash_roi": [0.44, 0.93, 0.56, 0.99],
        "wave_roi": [0.46, 0.02, 0.54, 0.06],
        "upgrade_btn": [0.86, 0.42],
        "confirm_btn": [0.50, 0.72],
        "sell_btn": [0.86, 0.52],
        "result_roi": [0.30, 0.35, 0.70, 0.65],
        "priority_btn": [0.86, 0.32],
        "priority_options": {
            "first": [0.80, 0.20], "last": [0.86, 0.20],
            "strongest": [0.80, 0.26], "weakest": [0.86, 0.26],
            "closest": [0.80, 0.32], "farthest": [0.86, 0.32],
        },
    },
]


def is_default_anchors(anchors: dict) -> bool:
    """True if these anchors are untouched placeholders. Compares against the
    RETIRED sets as well as the current defaults: a profile saved by an older
    build carries that build's placeholders, so checking only today's defaults
    would report it as calibrated (green) while it still holds pure guesses.

    Heuristic, not proof - a profile missing some anchor keys entirely matches
    nothing here and still reads as calibrated."""
    return any(anchors == d
               for d in (StageProfile().ui_anchors, *RETIRED_DEFAULT_ANCHORS))
