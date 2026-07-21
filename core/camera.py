"""Camera normalization (Phase 2.5) - right-drag top-down technique.

Sequence, every loop, before any click coordinate is trusted:
  0. Left-click the centre of the Roblox viewport first. SetForegroundWindow
     alone does NOT make Roblox capture the mouse - without an actual click
     into the game window the camera input below goes nowhere.
  1. Zoom all the way IN to its hard clamp (reliable regardless of starting
     zoom).
  2. Hold the RIGHT mouse button and drag straight down to the pitch clamp -
     also a hard clamp, so it needs no per-stage calibration. The drag STARTS
     near the top of the window so its downward travel stays on-screen.
  3. Zoom all the way back OUT to its hard clamp, for the widest possible
     top-down view of the stage.

Every step drives to a hard clamp, so this needs no per-stage tuning at
all - it's the same fixed sequence for every stage.

This used to tap Shift to engage Shift Lock and then move the bare cursor
(HANDOFF 2.3). Right-drag rotates the camera just as well without a
keystroke (HANDOFF 2.22), and it deleted the sequence's worst failure mode
along with the key: Shift Lock has no queryable state, only a toggle, so a
process that died mid-sequence left the NEXT run's tap turning it off
instead of on - silently breaking every coordinate that run touched. A
right-button drag holds no state between runs, so there's nothing to desync.

The centre click (step 0) lands on empty ground/character - this always
runs before any hotbar slot is armed, so it can't place a unit. If you ever
call normalize() while a "Start Game?"-style dialog is up, that click could
hit it; normalize is meant to run in-stage.

Yaw is NOT reset here - the drag is vertical, so it only pitches. Nothing in
this macro ever moves the character or turns the camera sideways, so yaw
stays wherever the stage loaded it. If the user spins the camera by hand
mid-run, the reference-image check (StageSetup.reference_matches) is what
catches it.
"""


class CameraNormalizer:
    def __init__(self, input_driver, cfg):
        c = cfg["camera"]
        self.zoom_in_clamp_ticks = c["zoom_in_clamp_ticks"]
        self.zoom_out_clamp_ticks = c["zoom_out_clamp_ticks"]
        self.pitch_down_clamp_drag = c["pitch_down_clamp_drag"]
        self.drag_step_px = c["drag_step_px"]
        self.drag_step_delay_ms = c["drag_step_delay_ms"]
        self.drv = input_driver

    def normalize(self, rect):
        cx, cy = rect.x + rect.w // 2, rect.y + rect.h // 2

        # Click into the game so Roblox actually captures the mouse (see step 0).
        self.drv.click(cx, cy)
        self.drv.wait(150)

        self.drv.scroll(abs(self.zoom_in_clamp_ticks))
        self.drv.wait(150)

        # Start the downward drag near the top of the window so its full
        # travel stays inside the viewport / on-screen (a drag from centre
        # would run off the bottom of a 1080p screen).
        drag = abs(self.pitch_down_clamp_drag)
        start_y = min(rect.y + 60, cy)
        self.drv.right_drag((cx, start_y), drag,
                            self.drag_step_px, self.drag_step_delay_ms)
        self.drv.wait(150)

        self.drv.scroll(-abs(self.zoom_out_clamp_ticks))
        self.drv.wait(150)
