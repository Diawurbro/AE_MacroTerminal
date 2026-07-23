# Roblox TD Macro

Automation tool for a Roblox tower-defense game (Windows only).

Status: **feature-complete, pre-release** — window manager, dashboard dock UI,
stage editor, OCR-gated executor (place/upgrade/sell/ability/click/wait),
win/loss detection with auto-repeat, stats DB, Discord webhook. Not yet
verified against a live game session — see [Before first release](#before-first-release).

---

## Install

```bat
cd roblox_td_macro
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

OCR (cash/wave reads, priority verification) needs Tesseract installed
separately:
https://github.com/UB-Mannheim/tesseract/wiki

---

## Run

**Option 1 — double-click `run.bat`** (recommended)

First run creates the venv and installs dependencies for you; takes a bit.
Later runs open immediately.

**Option 2 — run it yourself**

```bat
python main.py
```

A single full-screen dashboard opens: it frames the Roblox window with a
click-through hole cut exactly over it, docks the control column to the
right, and the log strip beneath. Roblox itself isn't moved by this window —
attaching (below) is what resizes/positions the actual game window.

---

## Build `run.exe`

Double-click **`build.bat`**, wait 3-8 minutes, get `dist\run\run.exe`.

Take the whole `dist\run` folder, not just the exe — the Qt DLLs live in
there.

Notes:

- Roughly 180-250 MB because of PySide6 + OpenCV.
- Windows Defender may flag a false positive — normal for unsigned
  PyInstaller builds, add an exclusion.
- `config.yaml` and the `profiles` folder sit next to the exe and can be
  edited without rebuilding.
- If it opens and closes immediately with no visible error, set
  `console=True` in `run.spec` and rebuild to see the traceback.

---

## Usage — first-time setup, in order

1. Launch Roblox, enter the game, go to the stage you want to farm.
2. In Roblox settings: display mode **windowed**, Windows display scaling
   **100%** (Settings > Display > Scale). The macro clicks fixed positions —
   fullscreen or non-100% scaling breaks them.
3. Click **Attach game window** — Roblox's client area is resized to
   1280×720 and the dashboard docks around it. Readiness panel should show
   "Roblox connected" in green at 1280×720.
4. Click **Test camera view** — Roblox zooms to the top-down farming angle.
5. Click **Stage editor** → name the stage → **Capture ref** to snapshot it
   as the reference image.
6. In the editor's **Calibrate** tab: **Set point** + click each button on
   the image (upgrade / sell / confirm / priority / Start Game); **Set box**
   + drag over the cash number, wave number, and the Win/Loss banner area.
7. On the **Steps** tab: **+ Add step** for each unit, click the image where
   it goes, then set:
   - **Action**: place / click / upgrade / sell / ability / wait
   - **Slot**: hotbar unit slot (place/click) — `none` for a bare click with
     no arming
   - **Times**: upgrade click count
   - **Target step**: which placed unit an upgrade/sell/ability refers to
   - **Wait for**: precondition before acting — cash / wave / delay

   Drag pins on the image to reposition; coordinates update automatically.
8. Click **Save** → writes `profiles/xxx.json`.
9. Install Tesseract-OCR (link above) so cash/wave waits and priority
   verification work; if not on PATH, set `vision.tesseract_cmd` in
   `config.yaml`.
10. Back on the dashboard, click **Re-check**, fix any red readiness items,
    then press **Start (F9)**. Press **F12** for an emergency stop.

---

## In-game settings (critical — set before use)

Changing any of these after a profile is built will break it immediately:

- Camera Mode: **Classic**
- Movement Mode: **Keyboard**
- Shift Lock: **OFF**
- Graphics Quality: locked, do not change
- Full screen: **OFF** (windowed only)

---

## Structure

```
core/window.py          find + position/pin the Roblox window
core/input_driver.py     SendInput for mouse/keyboard/scroll/drag
core/hotbar.py           unit arming — number-key taps (default) or card clicks
core/unit_panel.py       select/upgrade/sell/deselect on the unit panel
core/executor.py         run loop — OCR gating, camera normalize, repeats
core/step_runner.py      per-step dispatch to core/actions/*
core/actions/            place, click, upgrade, sell, ability, wait
core/match_flow.py       win/loss detection, reward-screen clearing, repeat
core/stage_setup.py      camera normalize + reference-image verification
core/ocr.py              cash/wave/fraction OCR readers
core/run_recorder.py     stats DB writer
core/notify.py           Discord webhook
vision/capture.py        mss capture + template matching
vision/result_detector.py   win/loss banner + result-screen template match
vision/reward_screen.py  reward-screen clear + Repeat-button click
data/profile.py          stage profile model + save/load JSON
data/stats.py            SQLite stats
ui/main_window.py        full-screen dashboard dock (frames the game window)
ui/panels.py             control column + log panel
ui/stage_editor.py       pin-and-configure stage editor
main.py                  entry point, dock layout, app wiring
config.yaml              all settings (gitignored; seeded from config.example.yaml)
```

---

## Before first release

Full findings live in `RELEASE_REVIEW.md` (bug list) and `HANDOFF.md`
(session history). Current blockers:

- [ ] Sell flow verified end-to-end (may be a single click, no confirm
      dialog — unconfirmed)
- [ ] One clean supervised live loop, win and loss both handled
- [ ] `build.bat` output smoke-tested on a clean machine

Should-have before wider use:
- [ ] Minimal automated test suite (placement retry, priority cycle, OCR
      parsing — none exists yet)
- [ ] Shared `Capture` instance cleanup verified under a long session

Deliberately out of scope for v1: session-level pacing/breaks, ghost/phantom
placement detection, DPI scaling other than 100%, multi-resolution support.

---

