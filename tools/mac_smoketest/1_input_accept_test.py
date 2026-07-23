"""
Smoke test 1 (mac port): does synthetic input via CGEventPost register in
real Roblox at all? This is the go/no-go gate for the whole macOS port -
Windows needed real SendInput (SetCursorPos/mouse_event were ignored by
Roblox), and the same kind of filtering may or may not apply on mac's
Quartz event path. Don't write any real mac backend code until this passes.

Needs: pip install pyobjc-framework-Quartz
Needs: Accessibility permission for whatever runs this (Terminal / python3)
  in System Settings > Privacy & Security > Accessibility - otherwise
  CGEventPost silently no-ops and nothing will happen at all.

How to run: switch to Roblox (in a stage, character visible, nothing
blocking screen centre), then run this script and don't touch the mouse/
keyboard until it's done. Watch whether the cursor visibly moves + clicks,
and whether the character turns/moves in response to the W tap.
"""
import sys
import time

try:
    from Quartz import (
        CGEventCreateMouseEvent, CGEventCreateKeyboardEvent, CGEventPost,
        kCGHIDEventTap, kCGEventMouseMoved, kCGEventLeftMouseDown,
        kCGEventLeftMouseUp, kCGMouseButtonLeft,
    )
except ImportError:
    print("Missing pyobjc. Run: pip install pyobjc-framework-Quartz")
    sys.exit(1)

# Pick a screen point that's harmless to click in-game (open ground, not a
# button) - adjust to your screen/stage before running.
TARGET = (640, 400)
KEY_W = 0x0D  # macOS virtual keycode for 'W'


def post_mouse(event_type, point, button=kCGMouseButtonLeft):
    ev = CGEventCreateMouseEvent(None, event_type, point, button)
    CGEventPost(kCGHIDEventTap, ev)


def post_key(keycode, key_down):
    ev = CGEventCreateKeyboardEvent(None, keycode, key_down)
    CGEventPost(kCGHIDEventTap, ev)


def main():
    print(f"Target point: {TARGET} - edit TARGET in this file if that's not "
          "over your Roblox window.")
    print("Switch to Roblox now. Starting in:")
    for n in (5, 4, 3, 2, 1):
        print(n)
        time.sleep(1)

    print(f"Moving + clicking at {TARGET} ...")
    post_mouse(kCGEventMouseMoved, TARGET)
    time.sleep(0.1)
    post_mouse(kCGEventLeftMouseDown, TARGET)
    time.sleep(0.05)
    post_mouse(kCGEventLeftMouseUp, TARGET)

    time.sleep(0.5)
    print("Tapping 'W' for 300ms ...")
    post_key(KEY_W, True)
    time.sleep(0.3)
    post_key(KEY_W, False)

    print("\nDone. Report back one of:")
    print("  - both worked (cursor moved+clicked, character reacted to W)")
    print("  - only the click worked")
    print("  - only the key worked")
    print("  - neither worked (this is the important one to know)")


if __name__ == "__main__":
    main()
