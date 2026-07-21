"""Global hotkeys (F9 start, F12 emergency stop) via RegisterHotKey.

Qt's event loop doesn't pump WM_HOTKEY, and Roblox has focus while the
macro runs, so this needs its own thread with a real Win32 message loop
bound to a hidden message-only window.
"""

import threading
import time

try:
    import win32api
    import win32con
    import win32gui
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

WM_HOTKEY = 0x0312

_VK = {"f9": 0x78, "f12": 0x7B}
if HAS_WIN32:
    _VK = {"f9": win32con.VK_F9, "f12": win32con.VK_F12}


class GlobalHotkeys:
    def __init__(self, log=lambda m: None):
        self._callbacks = {}
        self._ids: dict[int, tuple[str, object]] = {}
        self._thread = None
        self._thread_id = None
        self._hwnd = None
        self._log = log

    def register(self, key: str, callback):
        vk = _VK.get(key.lower())
        if vk is None:
            raise KeyError(f"unsupported hotkey: {key}")
        self._callbacks[key.lower()] = (vk, callback)

    def start(self):
        if not HAS_WIN32 or self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        for _ in range(50):
            if self._thread_id is not None:
                break
            time.sleep(0.02)

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        entry = self._ids.get(wparam)
        if entry:
            _, cb = entry
            try:
                cb()
            except Exception:
                pass
        return 0

    def _run(self):
        self._thread_id = win32api.GetCurrentThreadId()
        try:
            wc = win32gui.WNDCLASS()
            wc.lpfnWndProc = {WM_HOTKEY: self._wnd_proc}
            wc.lpszClassName = "TDMacroHotkeyWnd"
            wc.hInstance = win32api.GetModuleHandle(None)
            atom = win32gui.RegisterClass(wc)
            self._hwnd = win32gui.CreateWindow(
                atom, "TDMacroHotkeyWnd", 0, 0, 0, 0, 0, 0, 0, wc.hInstance, None)

            for i, (name, (vk, cb)) in enumerate(self._callbacks.items(), start=1):
                # RegisterHotKey raises (not just returns False) when another
                # app already owns the combo - never let that kill the thread.
                try:
                    ok = win32gui.RegisterHotKey(self._hwnd, i, 0, vk)
                except Exception:
                    ok = False
                if ok:
                    self._ids[i] = (name, cb)
                else:
                    self._log(f"Hotkey '{name}' is already bound by another "
                              "app - it won't fire here.")

            win32gui.PumpMessages()
        except Exception as e:
            self._log(f"Hotkey listener stopped unexpectedly: {e}")
        finally:
            for i in list(self._ids):
                try:
                    win32gui.UnregisterHotKey(self._hwnd, i)
                except Exception:
                    pass

    def stop(self):
        if HAS_WIN32 and self._thread_id and self._thread and self._thread.is_alive():
            try:
                win32api.PostThreadMessage(self._thread_id, win32con.WM_QUIT, 0, 0)
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=1.5)
        self._thread = None
        self._thread_id = None
