"""
Smoke test 3 (mac port): what's the actual points-to-pixels scale factor on
this display, and does mss's pixel-based capture agree with it? mss (vision/
capture.py, unchanged by the port) captures in physical pixels; CoreGraphics/
Accessibility window frames are reported in points. Getting this ratio wrong
would silently offset every click and capture region by the scale factor
(2x on most Retina Macs) - this script nails the math down empirically
before window_mac.py / input_driver_mac.py get written for real.

Needs: pip install mss pyobjc-framework-Quartz pyobjc-framework-Cocoa

How to run: open Roblox (for the cross-check at the end), then run this.
"""
import sys

try:
    import mss
except ImportError:
    print("Missing mss. Run: pip install mss")
    sys.exit(1)

try:
    from Quartz import (
        CGWindowListCopyWindowInfo, kCGWindowListOptionOnScreenOnly,
        kCGNullWindowID,
    )
    from AppKit import NSScreen
except ImportError:
    print("Missing pyobjc. Run: pip install pyobjc-framework-Quartz "
          "pyobjc-framework-Cocoa")
    sys.exit(1)


def main():
    screen = NSScreen.mainScreen()
    scale = screen.backingScaleFactor()
    frame = screen.frame()
    print(f"NSScreen main frame (points) : {frame.size.width} x {frame.size.height}")
    print(f"NSScreen backingScaleFactor  : {scale}")

    with mss.mss() as sct:
        mon = sct.monitors[1]  # primary monitor, per mss convention
        print(f"mss primary monitor (pixels) : {mon['width']} x {mon['height']}")

    expected_px_w = frame.size.width * scale
    expected_px_h = frame.size.height * scale
    print(f"points * scale = {expected_px_w} x {expected_px_h}  "
          "(should match the mss line above)")

    print("\nLooking for a Roblox window to cross-check its bounds too...")
    info_list = CGWindowListCopyWindowInfo(
        kCGWindowListOptionOnScreenOnly, kCGNullWindowID)
    for w in info_list:
        if "roblox" in w.get("kCGWindowOwnerName", "").lower():
            b = w.get("kCGWindowBounds")
            print(f"Roblox window bounds (points): {b}")
            print(f"  x scale -> should be pixels: "
                  f"{b['Width'] * scale} x {b['Height'] * scale}")
            break
    else:
        print("(no Roblox window found - open it to cross-check, not "
              "required for the main scale-factor answer above)")


if __name__ == "__main__":
    main()
