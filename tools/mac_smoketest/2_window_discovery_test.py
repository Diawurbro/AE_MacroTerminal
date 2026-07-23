"""
Smoke test 2 (mac port): can we find the Roblox window via CoreGraphics, and
read its frame via the Accessibility API? Validates window discovery AND
the Accessibility-permission story in one step, before window_mac.py gets
built for real.

Needs: pip install pyobjc-framework-Quartz pyobjc-framework-ApplicationServices
Needs: Accessibility permission (System Settings > Privacy & Security >
  Accessibility) for whatever runs this (Terminal / python3) - without it,
  the AX calls below return an error instead of data.

How to run: open Roblox, then run this script.
"""
import sys

try:
    from Quartz import (
        CGWindowListCopyWindowInfo, kCGWindowListOptionOnScreenOnly,
        kCGNullWindowID,
    )
except ImportError:
    print("Missing pyobjc. Run: pip install pyobjc-framework-Quartz")
    sys.exit(1)

try:
    from ApplicationServices import (
        AXUIElementCreateApplication, AXUIElementCopyAttributeValue,
        kAXWindowsAttribute, kAXPositionAttribute, kAXSizeAttribute,
        kAXErrorSuccess,
    )
    HAS_AX = True
except ImportError:
    HAS_AX = False
    print("pyobjc-framework-ApplicationServices missing - skipping the AX "
          "read, doing window-list discovery only.\n")


def find_roblox_windows():
    info_list = CGWindowListCopyWindowInfo(
        kCGWindowListOptionOnScreenOnly, kCGNullWindowID)
    return [w for w in info_list
            if "roblox" in w.get("kCGWindowOwnerName", "").lower()]


def main():
    matches = find_roblox_windows()
    if not matches:
        print("No window with owner name containing 'Roblox' found on screen.")
        print("Make sure Roblox is open and visible, then run again.")
        return

    for w in matches:
        print("---")
        print("Owner name   :", w.get("kCGWindowOwnerName"))
        print("Window name  :", w.get("kCGWindowName"))
        print("Window number:", w.get("kCGWindowNumber"))
        print("Owner PID    :", w.get("kCGWindowOwnerPID"))
        print("Bounds (pt)  :", w.get("kCGWindowBounds"))

    if not HAS_AX:
        return

    pid = matches[0].get("kCGWindowOwnerPID")
    print(f"\nTrying AX read on PID {pid} ...")
    app_ref = AXUIElementCreateApplication(pid)
    err, windows = AXUIElementCopyAttributeValue(app_ref, kAXWindowsAttribute, None)
    if err != kAXErrorSuccess or not windows:
        print(f"AX error {err} reading windows - most likely missing "
              "Accessibility permission. Grant it in System Settings > "
              "Privacy & Security > Accessibility for Terminal/python3, "
              "then try again.")
        return

    print(f"AX sees {len(windows)} window(s) for this app.")
    win_ref = windows[0]
    for name, attr in (("position", kAXPositionAttribute), ("size", kAXSizeAttribute)):
        err, val = AXUIElementCopyAttributeValue(win_ref, attr, None)
        print(f"AX {name}: err={err} value={val}")


if __name__ == "__main__":
    main()
