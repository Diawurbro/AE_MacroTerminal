"""macOS virtual keycodes (Carbon/HIToolbox Events.h numbering) - the mac
equivalent of input_driver_win.py's Windows hardware scan-code SCAN dict.
Same key set, so callers (core/hotbar.py's use_unit_keys path, etc.) don't
need to know which platform they're on."""

VK = {
    "w": 0x0D, "a": 0x00, "s": 0x01, "d": 0x02, "e": 0x0E, "q": 0x0C,
    "r": 0x0F, "f": 0x03, "g": 0x05, "space": 0x31, "esc": 0x35,
    "enter": 0x24, "tab": 0x30, "shift": 0x38, "ctrl": 0x3B,
    "1": 0x12, "2": 0x13, "3": 0x14, "4": 0x15, "5": 0x17,
    "6": 0x16, "7": 0x1A, "8": 0x1C, "9": 0x19, "0": 0x1D,
    # Rest of the alphabet - kept for parity with the Windows SCAN dict.
    "b": 0x0B, "c": 0x08, "h": 0x04, "i": 0x22, "j": 0x26, "k": 0x28,
    "l": 0x25, "m": 0x2E, "n": 0x2D, "o": 0x1F, "p": 0x23, "t": 0x11,
    "u": 0x20, "v": 0x09, "x": 0x07, "y": 0x10, "z": 0x06,
}

# Function keys - separate table since only hotkeys_mac.py needs these, not
# the SCAN-equivalent path above.
FUNCTION_VK = {
    "f1": 0x7A, "f2": 0x78, "f3": 0x63, "f4": 0x76, "f5": 0x60,
    "f6": 0x61, "f7": 0x62, "f8": 0x64, "f9": 0x65, "f10": 0x6D,
    "f11": 0x67, "f12": 0x6F,
}
