# macOS port smoke tests

Throwaway scripts, not part of the app. Answer the 3 unknowns that decide
whether a real macOS port is worth building, before any of `core/window.py` /
`core/input_driver.py` / `core/hotkeys.py` gets a mac backend written.

## Setup

```
pip install mss pyobjc-framework-Quartz pyobjc-framework-ApplicationServices pyobjc-framework-Cocoa
```

Grant Accessibility permission **before** running anything: System Settings >
Privacy & Security > Accessibility > add Terminal (or whatever runs
`python3`). Without this, script 1's clicks/keys silently no-op and script 2's
AX read fails - both look like "nothing happened," which is confusing if you
don't do this first.

## Run in order

1. **`1_input_accept_test.py`** - the actual go/no-go gate. With Roblox open
   and in view, run this and watch: does the cursor move + click, does the
   character react to a W tap? If neither happens, Roblox's mac client may be
   filtering synthetic input the same way Windows filtered plain
   `SetCursorPos` (which is *why* the Windows side uses raw `SendInput`) -
   report this back before anything else gets built.
2. **`2_window_discovery_test.py`** - confirms Roblox's window can be found
   via `CGWindowListCopyWindowInfo`, and that its frame is readable via the
   Accessibility API (same permission as script 1, read instead of write).
3. **`3_retina_scale_test.py`** - prints the points-vs-pixels scale factor and
   cross-checks it against `mss`'s pixel capture and (if found) the Roblox
   window's own bounds. This is the exact math `window_mac.py` and
   `input_driver_mac.py` both depend on to avoid every click landing at half
   the intended coordinate on a Retina display.

Report the output of all three back before requesting the real backend
implementation - it decides whether the port is straightforward, needs a
workaround (e.g. a different `CGEventSourceStateID`), or isn't worth pursuing.
