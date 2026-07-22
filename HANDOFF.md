# HANDOFF — Roblox TD Macro

Context document for continuing this project in Claude Code.
Everything below was decided across a prior design conversation.

---

## 1. What this is

A Windows automation tool for a Roblox tower-defense game (Anime Expeditions).
The game owner permits macro use; platform-level Roblox ToS still applies and the
user accepts that risk. Recommended: run on an alt account.

**Not a memory/injection tool.** It only sends OS-level input and reads pixels
from the screen. No DLL injection, no memory reads, no game code modification.

---

## 2. Core design decisions (do not re-litigate these)

### 2.1 No macro recording — mark positions on a reference image instead

The original plan was record/playback of raw input. That was **replaced**.
The user marks numbered points by clicking on a screenshot of the stage.
Each marker becomes a step with an action and a precondition.

Reason: individual steps can be edited without re-recording the whole run,
and the reference screenshot doubles as the camera-verification target.

### 2.2 The game has its own "teleport to spawn"

This **removed** an entire subsystem from the original plan. No character
reset, no walk paths, no px-per-ms calibration, no servo correction loop,
no stuck detection. Do not reintroduce these.

What remains from that subsystem: camera normalization only.

### 2.3 Camera normalization — top-down technique

> **Superseded in part by 2.22**: the Shift Lock steps below are now a
> right-button drag (no keystroke). The structure — focus click, zoom-in
> clamp, pitch-down clamp, zoom-out clamp, no per-stage calibration — is
> unchanged, and the reasoning for each clamp still applies.

Character moves freely and the camera rotates, so the camera must be returned
to a known state before any click coordinate is valid. `core/camera.py`:

- **Focus click first (step 0)**: `normalize()` left-clicks the centre of
  the Roblox viewport before anything else. `SetForegroundWindow` (what
  `RobloxWindow.focus()` does) is NOT enough for Roblox to capture the mouse
  — without a real click into the game window, Shift Lock never engages and
  the absolute mouse-moves below just slide the visible cursor across and
  off the bottom of the screen (a user reported exactly this). The click
  lands on empty ground and always runs before any hotbar slot is selected,
  so it can't place a unit. (Runs in-stage; wouldn't be safe over a lobby
  "Start Game?" dialog.)
- **Yaw**: comes free. Roblox resets camera yaw on teleport/respawn.
- **Shift Lock** is toggled ON for the duration of this sequence (tap
  `shift`). While locked, plain mouse movement rotates the camera directly —
  no right-click-drag needed — which is what makes a repeatable top-down
  angle possible without per-stage pitch calibration.
- **Zoom in**: has a clamp. Scroll IN `camera.zoom_in_clamp_ticks` (config.yaml,
  default 30) to hit the fully-zoomed-in limit — a hard, stage-independent
  clamp.
- **Pitch**: has a clamp. With Shift Lock engaged, drag-look down
  `camera.pitch_down_clamp_drag` px (config.yaml, default 600) to hit the
  straight-down limit — also a hard clamp. The drag STARTS near the top of
  the window (`rect.y + 60`), not centre, so its full downward travel stays
  on-screen even if Shift Lock momentarily fails to hold the cursor (a
  centre-start drag of 600px runs off the bottom of a 1080p screen).
- **Zoom back out**: also driven to its hard clamp — scroll OUT
  `camera.zoom_out_clamp_ticks` (config.yaml, default 30) for the widest
  possible top-down view. Every step in the sequence now drives to a hard
  clamp, so **there is no per-stage camera calibration at all** —
  `StageProfile` no longer has a `camera` field (removed; `load()` drops it
  silently from any older saved JSON that still has one).
- Shift Lock is toggled OFF again before any step executes, so cursor
  movement during placement clicks doesn't spin the camera.
- Both the zoom-in and pitch-down moves must be issued in small steps
  (`drag_step_px` / `drag_step_delay_ms`, ~12px/8ms) — a single large jump
  gets dropped by the Roblox camera controller.
- **Known risk**: Shift Lock has no queryable state, only a toggle. If the
  process dies mid-sequence, the next run's toggle desyncs it. No cheap fix
  without reading the Shift Lock HUD icon via template match — watch for a
  run clicking in the wrong place right after a crash/force-kill.

### 2.4 Coordinates are normalized 0–1

All step coordinates and ROIs are fractions of the client area, never absolute
pixels. This keeps profiles valid across machines and resolutions.

### 2.5 Client area is forced to 1280×720, centered

`core/window.py` computes the frame padding (outer window size minus client
size) and sets the outer size so the *client* lands at exactly 1280×720.
The macro's own UI is a separate, independently-positioned window now (2.8)
— it no longer docks to this rect.

### 2.6 Every step is gated on a precondition

The main failure mode of this kind of macro is clicking to place a unit when
cash is insufficient, which desynchronizes the whole sequence. So each step
waits on one of: `cash >= N` (OCR), `wave >= N` (OCR), `delay N ms`, or none.

After placing, capture the ROI around the point and compare to the pre-click
capture. If unchanged, the placement failed — retry twice, then skip and log.

### 2.7 Upgrade steps reference other steps, not their own coordinates

`Step.target_step` points at a `place` step. `Step.anchor()` resolves it.
Moving the place marker automatically moves everything that upgrades it.

### 2.8 UI is two windows: a bottom bar dashboard + the stage editor

Went through several designs here before landing on this one:

1. **Original**: three windows — frameless `ControlPanel` + `StatusPanel`
   (`Qt.Tool`, always-on-top, docked left/right of the Roblox window), plus
   a `StageEditor` popup opened on demand.
2. **One-window attempt**: merged all three into one big resizable window.
   **Reverted** — it overlapped the centered Roblox window and buried its own
   buttons.
3. **Left column**: a narrow (`DASH_W = 300`) full-height dashboard docked to
   the left edge, Roblox positioned to its right. **Reverted** — stacking
   Setup & Run + Readiness + Statistics + Webhooks + Log vertically ran off
   the bottom of the screen on the user's monitor.
4. **Current**: **a short full-width bottom bar** + the on-demand editor,
   modeled on the InformaalFrog reference tool (Current Process / Settings /
   Statistics / Webhooks laid out side by side along the bottom):
   - `ui/main_window.py:MainWindow` (`BAR_H = 250`) — a `QHBoxLayout` bar
     `main.py` docks to the **bottom edge at full screen width**
     (`availableGeometry`). Left to right: Setup & Run, Readiness, Statistics,
     Webhooks, Current Process (log, stretches to fill leftover width).
   - To fit the short bar, `SetupRunPanel` is a compact `QGridLayout` (3 cols)
     instead of a tall vertical stack, and `ReadinessPanel`'s checklist lives
     in a `QScrollArea` so it scrolls instead of stretching the window.
   - `ui/stage_editor.py:StageEditor` — its own window, **not shown at
     startup**: opened on demand from the "Stage editor" button
     (`App.open_editor`). Canvas + steps table + Calibrate tab (2.24).
   - On attach, `RobloxWindow.layout(bottom_bound=BAR_H+10)` centers the
     Roblox window in the screen area ABOVE the bar, so the two never overlap.
     `layout()` still accepts `left_bound` too (unused now, kept for a possible
     future side dock). The editor floats on top when open. Note: this needs a
     monitor tall enough for a 720px client + the 250px bar (~1000px); on a
     shorter screen the client is clamped to the top and can touch the bar.

Button placement (after the user's cleanup pass):
- Dashboard "Setup & Run": Attach + center window, **Test camera view**
  (moved here from the editor — routed via `SetupRunPanel.camera_test_requested`
  → `App.test_camera_view`, which drives `CameraTestThread` and re-enables
  the button on done/fail), **Stage editor** (opens the editor), Load
  profile, Screenshot, Start, Emergency stop, Exit. (No loop count - runs
  are always infinite, see 2.23.)
- Editor top bar: Capture ref, Load, Save. ("Open image" removed as
  redundant with Capture ref.) Editor step row: Add, Delete only ("Up"/"Down"
  reorder buttons removed).

Consequences:
- `App.profile` (main.py) is a **property** reading `self.editor.profile`
  instead of a separately-tracked copy. This fixed a real desync bug: the
  editor's own "Load" button used to update `editor.profile` without
  touching `App.profile`, so a run could silently execute against a stale
  profile if you loaded via that button instead of the dashboard's.
- **`capture_reference` raises Roblox to the front first** (`focus_fn`)
  before grabbing — `mss` captures whatever's drawn at those screen coords,
  so if the editor window is sitting over Roblox you'd otherwise capture the
  editor instead of the game.
- `QLocale.setDefault(English/US)` + `app.setFont(Segoe UI)` are set in
  `main()` before any widget is built. Without the locale, `QSpinBox` renders
  digits in the system locale (the user's machine is Thai → showed ๐-๙
  instead of 0-9). Keep this if you add more numeric widgets.
- **A row edit must NOT rebuild the rows.** The old code rebuilt the whole
  card grid on every field change, destroying the very widget whose signal
  was still on the stack — that was the "can't save the index after editing"
  bug. Still the rule in 2.24's table (`_on_row_edited` never calls
  `_refresh_list`): widgets write straight to the step object, and only
  structural changes (add / delete / load) rebuild.
- No `app.setQuitOnLastWindowClosed` override needed: both windows are
  normal top-level widgets, so Qt's default only quits once every open
  window is closed. The editor starts hidden, so at startup closing the
  dashboard (the only visible window) quits, as expected.
- The stage editor's step-settings form sits in a `QSplitter` between the
  Index grid and the form, both wrapped in scroll areas — a `QSplitter`
  still honors a child's `minimumSizeHint` as a floor, and a 9-row
  `QFormLayout`'s hint is tall enough to eat the whole split otherwise. Also
  note: `QSplitter.setSizes()` called before the widget's first `show()`
  gets renormalized once Qt actually lays it out — defer it with
  `QTimer.singleShot(0, ...)`, or your requested split ratio gets ignored.
  (This no longer matters much now that the editor has its full original
  1180×720 to itself again, but the gotcha is real if that layout changes.)

### 2.9 Auto Start-Game, non-fatal ref verify, game-state detection

Added when the user first tried to actually run it and reported "doesn't
work at all" — the real cause is that every game-specific value is still an
uncalibrated placeholder (open items 3-8), but two things made it fail
*silently and immediately*, plus a new gate to prevent wrong-state misfires:

- **Auto "Start Game"** (`game.press_start_game`, default on; dashboard
  checkbox "Press Start Game at run start"; position `game.start_game_btn`
  normalized, default `[0.50, 0.32]`). `Executor._press_start_game` clicks it
  after camera-normalize + ref-verify, before the placement steps, each loop.
  The checkbox writes into the shared `cfg` dict so the executor sees it live.
- **Reference verify was made non-fatal here** (`execution.abort_on_ref_mismatch`,
  default **false**), because the 0.92 threshold rarely matched a real
  capture and hard-aborting was the single most likely "nothing happens"
  cause. **Reversed in 2.28**: the threshold was the broken part (0.92 was
  unreachable), and continuing past a mismatch is what put units at the edge
  of the map. Default is `true` again, with a threshold that works.
- **Verbose per-phase logging** in the executor ("Teleporting...",
  "Normalizing camera...", "Pressed Start Game.", "Step #N: <summary>
  (waiting: ...)"), so the user can report exactly where a real run stalls.
- **Game-state detection** (`vision/game_state.py:GameStateDetector`) —
  crop-template match for lobby / loading / in-stage / result, same optional-
  template pattern as `result_detector.py`. Gated by
  `execution.wait_for_in_stage` (default **false**) and only active if
  `vision/templates/states/in_stage.png` exists; otherwise a safe no-op that
  returns "unknown" and never blocks a run. `Executor._ensure_in_stage`
  waits for the in-stage HUD before a loop acts, so it can't misfire on a
  loading screen / in the lobby. Near-black frames read as "loading" even
  without a template.

**Found and fixed while reviewing this** (a whole-project consistency pass,
prompted by the user asking to check every file for errors): the webhook
Save button called `save_config()`, a full `yaml.safe_dump()` rewrite of the
entire config dict — which **silently deletes every comment in
`config.yaml`** the first time anyone clicks Save (confirmed live: went from
23 comments to 0). Worse, the naive fix (dump `{key: value}` then
`.split(":", 1)` to extract just the value) broke on the very first realistic
webhook URL, because URLs contain their own colons — it left a stray `}` in
the file and corrupted it (`yaml.parser.ParserError` on next load). Fixed
properly: `save_config_value(section, key, value)` (main.py) edits exactly
one line of the file **in place** via line-based text search, dumps the bare
scalar (not wrapped in a dict, so there's no wrapper syntax to strip back
off), and leaves every comment and every sibling key untouched. Verified
with a byte-for-byte round-trip test including a colon-heavy URL.
`save_config()` (full rewrite) is kept only as a documented fallback for a
future case `save_config_value` can't reach - prefer the latter.

### 2.10 Visual calibration tab (Phase 1 of the "make it usable" plan)

The single biggest barrier to a real run was that every game-specific anchor
(`ui_anchors` in the profile + `game.start_game_btn` in config.yaml) was a
hand-guessed number a non-technical user would have to edit as JSON/YAML with
pixel math. The stage editor now has a third tab, **"Calibrate"**
(`ui/stage_editor.py`), that sets every anchor by clicking the reference
image — no numbers typed by hand.

- **Point anchors** (`POINT_ANCHORS`): `upgrade_btn`, `sell_btn`,
  `confirm_btn`, `priority_btn`, `start_game_btn`. "Set point" arms the canvas
  (`StageCanvas.set_calib_mode(name, "point")`); the next left-click emits
  `calib_point(name, nx, ny)` and stores the normalized position.
- **Box anchors** (`BOX_ANCHORS`): `cash_roi`, `wave_roi`, `result_roi`.
  "Set box" arms a drag; a rubber-band rect emits
  `calib_box(name, x1, y1, x2, y2)`. A click-without-drag (zero-size) is
  ignored so a misclick just needs a retry.
- **Scope**: all anchors write to `StageProfile.ui_anchors` (saved with the
  profile via the existing Save button) **except** `start_game_btn`, which is
  config-scoped — `_on_calib_point` routes it through
  `save_start_game_fn` → `App._save_start_game_btn` →
  `save_config_value("game", "start_game_btn", xy)`, persisting to config.yaml
  immediately (comment-safe, per 2.9).
- **Live overlay**: `StageCanvas.draw_anchors(points, boxes)` paints teal dots
  (points) and translucent rects (boxes) with labels over the reference image,
  visually distinct from the purple/orange step markers. Redrawn after
  Capture ref and after Load (both call `set_image`, which does
  `scene_.clear()` and wipes overlays — `_redraw_anchors()` repaints them).
- Calibration is refused until a reference image exists (buttons no-op with a
  status hint), so anchors are always set against a real capture.
- Verified headless (`scratchpad/calib_test.py` +full-App config round-trip):
  point→profile, box→profile, `start_game_btn`→config.yaml (23 comments
  intact, byte-for-byte restore), overlay items drawn, profile round-trip
  preserves calibration, and calibration blocked before a reference exists.

This was **Phase 1** of a 3-phase "make the macro actually usable" plan the
user asked for (organize proposed changes into 3 phases, do Phase 1 first).
All three phases were built in the same session:

### 2.11 Readiness self-check (Phase 2) + guided setup (Phase 3)

**Phase 2 — Readiness panel** (`ui/panels.py:ReadinessPanel`, inserted in the
dashboard below Setup & Run). A plain-English green/yellow/red checklist so
Start names what's missing instead of a run silently timing out.
`App._compute_readiness()` returns `(label, level, detail)` rows; level is
`ok` / `warn` (run works but limited) / `bad` (fix before a real run):

- **Roblox attached** — bad if not attached; warn if the client size isn't the
  wanted 1280x720 (fullscreen/scaling); ok otherwise.
- **Profile has steps** — bad if zero steps.
- **Reference image** — bad unless `profile.reference_image` exists on disk.
- **Buttons/HUD calibrated** — warn while `ui_anchors` still equals the fresh
  defaults (`_anchors_calibrated()` compares against `StageProfile().ui_anchors`),
  ok once the Calibrate tab has changed anything.
- **Win/Loss templates** — warn if `vision/templates/victory.png`+`defeat.png`
  are missing (color-ratio fallback still runs), ok if present.
- **Tesseract OCR** — probes the actual engine via `ocr.tesseract_ready()`
  (new): `HAS_TESSERACT` only means the *wrapper* imported, so readiness calls
  `pytesseract.get_tesseract_version()` to confirm the *binary* is installed —
  the #1 thing users miss. Warn (not bad) since delay-only profiles still run.

Recomputed on: startup, after attach, after Load profile, after Test camera,
on the "Re-check" button, and at the top of `run()` (so it's current the
instant Start is pressed). Confirmed via a headless test: fresh state shows
3 bad / 3 warn and summarizes "Not ready: 3 item(s)"; changing an anchor flips
"calibrated" to green; the Tesseract probe correctly reports not-installed.

**Phase 3 — Guided setup** (`App.show_guide`, "Guide" button next to Re-check
in the Readiness panel). A single ordered walkthrough dialog: windowed mode +
100% scaling → Attach → Test camera → Capture ref → Calibrate tab → add steps
+ Save → install Tesseract → Re-check → Start. The Readiness panel says WHAT
is missing; the guide says the ORDER to do it in. Kept inside the Readiness
panel to avoid the button clutter the user objected to earlier.

**Phase 3 — HUD-digit OCR hardening + live test button** (done). `core/ocr.py`
`read_int` was rewritten from "try both Otsu polarities, longest digit string
wins" to a confidence-scored multi-candidate reader:

- **Normalization** (`_normalize`): flip if mostly-dark so digits are always
  dark-on-light, then pad a 12px white quiet border (Tesseract needs one).
- **Two binarizations** (`_binarizations`): Otsu (clean high-contrast HUD) +
  adaptive-Gaussian (survives a gradient/busy background behind the number).
- **Multi-PSM** (7 line / 8 word / 13 raw) via `image_to_data`, scored by
  **mean per-digit confidence** instead of string length — a longer garbage
  read no longer beats a short clean one (the old failure mode).
- **Early exit** at confidence >= 80, so the clean common case is ~1 tesseract
  call, not 6 — important because the executor calls `read_int` in polling
  loops (cash/wave waits, upgrade-to-max).
- Still returns `int | None` and still no-ops safely when the engine is
  absent. Verified: graceful `None` with Tesseract not installed, binarization
  helpers run engine-free.

Because Tesseract isn't installed on the dev machine, the read itself can't be
validated here — so the **Calibrate tab gained "Test read cash/wave" buttons**
(`StageEditor._test_ocr` -> `App._test_ocr_read`) that grab the live HUD box
and print what OCR reads into the editor status bar. This lets the user
confirm/adjust a cash/wave box in the morning without a code round-trip, and
gives clear guidance when the box is unset / the engine is missing / the read
is empty. This is the tuning loop that replaces "guess blindly against no
data": box it, Test read, nudge the box, repeat.

### 2.12 First real-capture calibration + the wave-OCR concatenation bug

`profiles/test_ref.png` turned out to be a genuine 1280x720 in-game capture
(School Grounds - Act 1, "Start Game?" dialog up), which finally allowed the
HUD anchors to be **measured instead of guessed**. Measuring them immediately
exposed a silent run-breaking bug.

- **`core/ocr.py` `read_int` concatenated every digit group it found.** The
  wave HUD reads `0 / 15`, so the ROI returned `"0"+"15"` -> **15**. Any
  `wave >= N` precondition with N <= 15 therefore passed on the very first
  poll, at wave 0 — silently desynchronizing the whole run, which is the exact
  failure mode the precondition system exists to prevent (2.6).
  Fixed by splitting the reader in two, because the two HUD readouts need
  *opposite* handling and no single function can serve both:
  - `read_int` — joins groups. Correct for cash, where a thousands separator
    (`1,050`) makes Tesseract emit `"1"` + `"050"` and they must rejoin.
  - `read_leading_int` — takes only the leftmost group. Correct for wave.
  Groups are now sorted by x (`image_to_data`'s reading order isn't guaranteed
  left-to-right) and `_scan()` holds the shared best-confidence search, so the
  early-exit-at-80 behaviour is unchanged. `Executor._wait_condition` picks the
  reader by wait type.
- **Measured anchors** (replacing pure guesses in `data/profile.py`):
  `cash_roi` was pointing at the XP bar (y 0.93-0.99); the real gold digits are
  at y 0.805-0.842, x from 0.492 (deliberately tight, to exclude the coin icon
  ending at x~628) and only ~6 digits wide so a busy map background can't feed
  `read_int` spurious groups. `wave_roi` now covers the whole `0 / 15` text
  starting just right of the compass icon. Both verified by cropping them back
  out of the real capture.
- **`game.start_game_btn` missed the button.** The green button spans
  y 198-229px, centre **0.296**; the old `0.32` guess resolved to y=230 — one
  pixel past the bottom edge, landing on the dialog border. Fixed in
  config.yaml.
- **Still guesses** (no evidence in the capture — no unit was selected, so the
  upgrade/sell/priority panel was never on screen): `upgrade_btn`, `sell_btn`,
  `confirm_btn`, `result_roi`, `priority_btn`, `priority_options`.
- **Unresolved**: cash was only ever observed at `600`, so whether a longer
  value grows rightward (assumed) or recentres is unknown. A single mid-run
  screenshot with 4-5 digit cash settles it; if a big number reads short,
  widen `cash_roi`'s left edge.
- Changing the defaults would have made stale profiles read as *calibrated*
  (green) in the Readiness panel, since `_anchors_calibrated()` compared
  against the current defaults only. `data/profile.py` now exports
  `RETIRED_DEFAULT_ANCHORS` + `is_default_anchors()`, which main.py uses so a
  profile saved with an older build's placeholders still reports uncalibrated.
  Known hole: a profile missing some anchor keys matches nothing and still
  reads as calibrated (`profiles/stage7_sample.json` does this).

**Camera normalization (2.3) is confirmed working** — the reference capture is
correctly top-down and fully zoomed out. That was the largest untested
subsystem; it needs no further work.

Note the reference image was captured *with* the "Start Game?" dialog visible,
which is correct and should stay that way: `_verify_reference` runs **before**
`_press_start_game`, so the dialog is on screen at the moment of comparison.

### 2.13 Post-placement logic (upgrade / sell / priority)

Two bugs in the bundled post-place actions, both found by reading rather than
running (the coordinates they use are still uncalibrated, so a live run
couldn't have shown either):

- **`_click_upgrade_max` stopped upgrading too early.** It ended the loop on
  the first read where cash didn't drop. But cash also *rises* from kills
  mid-wave, so income landing inside the same ~220ms window as a successful
  upgrade produced exactly that reading. Now requires
  `execution.upgrade_stall_reads` (default 2) **consecutive** non-drops, and
  any real deduction resets the count. Still deliberately cannot distinguish
  "maxed out" from "can't afford the next level" - both stop.
- **`_click_upgrade_times` clicked blind.** A step's wait precondition guards
  its *placement* only, so "place, then upgrade x3" funded for the placement
  alone clicked three times and silently applied fewer. It now reads cash
  either side of the burst and warns if nothing was spent. Deliberately a
  warning, not a verdict — income can mask a real spend.

### 2.14 The selected-unit panel, measured (this changed the design)

A capture of a unit selected mid-wave settled most of what was guesswork:

- **The actions have keybinds.** The panel renders a badge on each button:
  **[R] Priority, [X] Sell, [T] Upgrade**. Pressing the key beats clicking a
  coordinate — resolution-independent, can't land on the wrong control. The
  executor now prefers keys (`game.use_unit_keys`, `game.unit_keys`) and falls
  back to the measured coordinates when that's false, via `_unit_action()`.
- **`game.teleport_key: "t"` COLLIDES with Upgrade.** It was always a guess at
  the teleport-to-spawn bind; as it stands, a teleport press with a unit
  selected buys an upgrade. Must be resolved before a real run.
- **The panel is BOTTOM-LEFT, not right.** Every action anchor used to be at
  x=0.86 — wrong by nearly the whole screen width. Measured, all on one row:
  `priority_btn [0.061, 0.623]`, `sell_btn [0.126, 0.623]`,
  `upgrade_btn [0.216, 0.623]`. Panel bounds ≈ x 0.014-0.332, y 0.299-0.708.
- **Deselect is solved** — the panel has its own red close button at
  `deselect_btn [0.318, 0.325]`. `_deselect()` clicks it after `_after_place`,
  which fixes 2.13's open problem without going near Escape.
- **Priority looks like a CYCLE button, not a menu.** It displays its current
  value ("None") rather than opening a list, so `priority_options` (a map of
  per-option coordinates) is probably modelling the wrong interaction, and
  `PRIORITY_TYPES` is still an unverified guess at the available values.
  Unresolved — needs a capture taken right after pressing R.
- **Upgrade shows "0/3"** — a readable per-unit cap. OCRing that would be a far
  better max-upgrade signal than the cash-watching heuristic in 2.13, which
  can't separate "maxed" from "can't afford". Not implemented yet.
- Cost text turns red when unaffordable (`¥1,100` at cash 50), so an
  affordability check by colour is also possible.
- `cash_roi` survives the in-wave layout (digits landed inside it), but a
  "+888 next wave" pill appears to its right during waves with only ~16px of
  clearance, and large cash values may still shift left past the ROI edge.

Note this capture was a whole-window screenshot including the 25px title bar,
unlike the app's own Screenshot button which grabs the client area — the
measurements above are converted to client coordinates.

### 2.15 UI redesign pass (supersedes parts of 2.8's detail, not its rules)

The two-window architecture in 2.8 is unchanged and still binding — this was
styling, wording and proportion only. What changed:

- **Both windows now share `DASHBOARD_QSS`.** The stage editor previously had
  *no stylesheet at all* and rendered in the default light Windows theme
  beside a dark dashboard. `main()` also applies it app-wide so `QMessageBox`
  dialogs parented to `None` (attach warnings, the Guide, the startup error)
  and Qt's file dialogs stop popping up bright white.
- **Wheel-scroll can no longer change any spin box or combo** (`_NoWheelFilter`
  / `install_no_wheel_filter()` in `ui/panels.py`, installed app-wide). It was
  silently changing hotbar slots and loop counts, and scrolling a *panel*
  mutated whatever control passed under the cursor. The event is forwarded to
  the nearest scroll-area ancestor instead, so panels still scroll. Verified:
  7 visible widgets across both windows, none respond to a wheel event.
  Spin-box arrow buttons were deliberately KEPT — with the wheel gone they're
  the only mouse-driven nudge left. Note for anyone tempted to restyle them:
  any `QSpinBox::up-button` rule makes Qt drop the native arrow unless you also
  supply an `::up-arrow` image, and a CSS-triangle arrow renders as a solid
  block. There's a comment in the QSS saying so.
- **Profile dropdown** on the dashboard (`profile_selected` / `set_profile_list`
  / `set_current_profile`). The panel displays only — `main.py` enumerates
  `paths.profiles` and calls `editor.load_profile_path()` (split out of
  `load_profile()` so loading by name needs no file dialog). It listens on
  `activated`, so repopulating can't fire a reload loop.
- **Readiness sorts bad → warn → ok.** Previously the green rows filled the
  visible area and the one blocking item sat below the fold behind a
  scrollbar — inverting the panel's whole purpose (2.11).
- **Stage editor canvas is height-for-width**, so the reference image fills its
  frame instead of letterboxing inside ~150px of black bands. Right column
  400 → 560px. Freed space holds a marker legend and a "getting started" card
  that auto-hides once a profile has a reference and at least one step.
- **Wording de-jargoned** (much of this is moot since 2.24 replaced the
  tabs and the form with one table): tab "Index grid" → **Placements**;
  Slot → Hotbar key (now "Unit", 2.23), Target step → Applies to, Upgrade mode → Auto-upgrade, Times → How many,
  Wait for → Start when, "Steps 0 / 100" → "3 steps, 3 placements". Rows that
  don't apply to the selected action are now hidden rather than greyed, so the
  form no longer needs scrolling. **`show_guide` in main.py references tab
  names — keep it in sync.** The Calibrate tab name and its "Set point" /
  "Set box" / "Test read" button labels were deliberately left alone because
  the guide and readiness details name them.

### 2.16 Post-match reward screens (part A of the auto-repeat loop)

When a match ends the game shows a run of item-reward screens before the
result screen. Each carries the caption **"(Click anywhere to close) [N/M]"**
at bottom-centre. `vision/reward_screen.py:RewardScreenDetector` template-
matches that caption; `Executor._clear_reward_screens` clicks through them.

Three decisions worth not re-litigating:

- **Presence, not counting.** The user described "about 5-6 clicks", and the
  caption does show `[N/M]` — but M varies per run, and reading it needs
  Tesseract while presence detection needs nothing. So the loop clicks while
  the caption is visible and stops when it isn't. `execution.max_reward_clicks`
  (15) is a runaway guard, *not* the expected count.
- **Check before every click, never after.** This is what makes it safe: N
  reward screens produce exactly N clicks, so a click can never land on the
  result screen — where "Back to lobby" is sitting. Asserted in testing for
  N = 0, 1, 5.
- **The template excludes the `[N/M]` counter**, since that part changes
  between screens. It's the caption text only.

Measured separation on real frames: reward screens score **0.838-1.000**,
gameplay frames **0.073-0.156**. `vision.reward_match_threshold` is 0.70, in
the middle of that gap.

`_wait_for_result` now also treats the reward caption as proof the match
ended. Without that, a game whose outcome only appears on the post-reward
result screen would block for the full `result_timeout_s` (15 min) every loop.
`_finish_run` still runs *before* the reward clicks so the result screenshot
captures the outcome rather than an item card.

### 2.17 Result screen + auto-repeat (part B — the loop now closes)

The result screen is `Victory` ribbon + Game Stats + Gained Rewards, with a
button row: **Next Stage / Repeat Stage / View Party** (all on y=0.790;
`repeat_btn` is the middle at x=0.375).

- **Detected by its Repeat Stage button, not the Victory ribbon** — the button
  is there whether you won or lost, so a loss is still recognised and still
  repeated. Measured: 1.000 on a real result screen, 0.23-0.37 on gameplay
  and reward frames, against the 0.85 `result_match_threshold`.
- **The victory ribbon is BLUE.** `result_detector`'s green-vs-red colour
  fallback therefore cannot classify this game at all — it reads a win as
  neither. `victory.png` is now cut from a real capture, and
  `classify_result_screen()` works from that alone: the caller has already
  confirmed the result screen is up, which makes a *negative* victory match
  meaningful (no ribbon on a result screen = loss). `defeat.png` is still
  wanted, but only to sharpen the in-match banner check.
- **`_click_repeat` re-confirms the result screen before clicking.** That
  button sits beside "Back to lobby"; clicking blind on a mistimed frame is
  how a run ends up out of the stage. Off via `execution.auto_repeat`.
- **`_finish_run` moved to after the result screen appears.** The outcome only
  exists there, and the screenshot now captures stats + the full reward list —
  a far better Discord attachment than a frame of the map.

End-of-match order is now: `_wait_for_result` (match ended) →
`_clear_reward_screens` (item screens) → `_wait_for_result_screen` (classify) →
`_finish_run` (record + screenshot) → `_click_repeat` (next loop).

Templates now shipped: `reward_close.png`, `result_repeat.png`, `victory.png`.

### 2.18 Upgrade-to-max via OCR level, priority as a confirmed cycle, defensive deselect

Closes the two things left open from 2.14: the upgrade cap being unknown, and
priority's interaction model being unconfirmed. All three anchors here were
measured off two different real captures (a "Stone Alchemist" unit showing
`Upgrade 0/3` / `Priority None`, and a "Lady Giant" unit showing `Upgrade 0/8`
/ `Priority First`) — cross-checked so a stray x/y off one screenshot alone
couldn't slip through.

- **`upgrade_level_roi`** — the panel's own "Upgrade N/M" caption, confirmed
  on both captures (different unit, different cap: 3 vs 8). Read with the new
  `ocr.read_fraction()`, NOT `read_int` — the ROI also contains the word
  "Upgrade", and while the digit whitelist excludes letters, a stray glyph can
  occasionally misread as a digit. `read_fraction` takes the **last two**
  digit groups by x-position rather than the first two, since reading order
  is left-to-right and the label always precedes the numbers, never follows.
- **`_click_upgrade_max` rewritten**: N reaching M is now a *definite* stop,
  where the old cash-only heuristic could only ever infer "maxed or can't
  afford" without telling the two apart. The cash-stall logic from 2.13
  is kept as the fallback whenever the level can't be read (no Tesseract,
  ROI uncalibrated, or one bad frame) — so behaviour degrades to the old
  design rather than breaking.
- **Priority confirmed as a CYCLE, not a menu.** The two captures show `None`
  and `First` on the same physical button — proof R advances through a fixed
  option list rather than opening a picker. `priority_options` (a per-option
  coordinate map) modeled a menu that doesn't exist and is **removed**.
  `priority_btn`'s coordinate is kept only as the `use_unit_keys: false`
  click fallback.
- **`priority_label_roi`** — confined to the priority button's own width
  (x 0.029–0.096). A wider first attempt bled into the Sell button next to it
  and picked up its `¥xxx` cost text as part of the "word". Read with the new
  `ocr.read_word()` (letters-only whitelist, psm 8/single-word primary,
  7/single-line fallback — separate from the digit reader's config).
- **`Executor._set_priority`**: presses R and reads the label back, stopping
  the moment it matches `step.priority`; bounded to `len(PRIORITY_TYPES)`
  presses so a mismatched guess or unreadable label can't spin forever — it
  warns instead. Without Tesseract or an uncalibrated ROI it presses once,
  unverified, rather than not acting at all.
- **Still only `none`/`first` are confirmed.** `last`/`strongest`/`weakest`/
  `closest`/`farthest` in `PRIORITY_TYPES` remain a guess at the game's real
  option set and cycle order — this is exactly the case the bounded loop and
  its warning exist to catch.
- **Defensive deselect before every teleport press.** A plain `place` step
  with no priority/upgrade never called `_deselect` (that only fired inside
  `_after_place`), so a unit panel could still be open when the next loop's
  teleport key fires. Since `teleport_key` is unverified and `"t"` is
  confirmed to be Upgrade (2.14), an open panel at that moment would spend
  real currency instead of teleporting. `_run_once` now calls `_deselect`
  unconditionally right before the teleport tap — a no-op if `deselect_btn`
  isn't set, and a harmless click on empty ground otherwise (the same pattern
  `camera.normalize()`'s own focus click already relies on).
- **Calibrate tab caught up.** It predated `deselect_btn`, `repeat_btn`,
  `reward_strip_roi`, `result_screen_roi` (added earlier this session) as
  well as `upgrade_level_roi`/`priority_label_roi` (added here) — none of
  them were clickable from the UI. All six are now in `POINT_ANCHORS`/
  `BOX_ANCHORS` (`ui/stage_editor.py`). "Test read" is now also wired for
  `upgrade_level_roi` and `priority_label_roi` — `main.py`'s
  `_test_ocr_read(roi, name)` dispatches to `read_int`/`read_leading_int`/
  `read_fraction`/`read_word` by anchor name (`_OCR_TEST_READERS`) instead of
  always calling `read_int`.
- Verified with a stubbed Tesseract engine (same technique as 2.12): both new
  OCR functions against synthetic digit-group/word inputs including the
  "stray-digit-in-label" case; `_set_priority`'s cycle-until-match, its
  bounded give-up, its already-correct short-circuit, and its no-Tesseract
  fallback; `_click_upgrade_max`'s OCR-level path and its cash-stall fallback
  (the latter was replaced in 2.19 — see there for the current design).
  Cannot be verified against a live Tesseract engine or the real game from
  this machine — still needs a real run once Tesseract is installed.

### 2.19 Simplified after a real run: mouse-only, upgrade just spam-clicks

The user ran the macro for real. The log showed the pipeline working end to
end — attach, teleport, camera normalize (`0.789`, below the `0.92`
threshold but the non-fatal path let it continue correctly), Start Game,
three placement steps — and then, exactly as flagged in 2.18: `#3
upgrade-to-max: cash and level both unreadable, stopping after 1 click(s).`
Tesseract still isn't installed on the user's machine, so 2.18's whole
multi-signal fallback chain never got to do anything — it correctly detected
"no signal at all" and bailed immediately. The user's response: stop trying
to be clever, use the mouse for everything, spam-click upgrade until it's
done.

- **`game.use_unit_keys` now defaults to `false`.** Upgrade/Sell/Priority all
  click the measured `ui_anchors` coordinates instead of pressing
  [T]/[X]/[R]. The keybind path (`game.unit_keys`) still exists and works —
  set the flag back to `true` to use it — but it's no longer the default.
  This also makes `game.teleport_key` unambiguous: with nothing else sending
  "t", a teleport press can only ever mean teleport, even though "t" is
  still confirmed to be the Upgrade bind and the real teleport key is still
  unverified. (The defensive `_deselect` before every teleport press, added
  in 2.18, stays either way — cheap, and still matters if `use_unit_keys` is
  flipped back on.)
- **`_click_upgrade_max` rewritten again, much shorter.** It now just clicks
  `upgrade_btn` up to `execution.max_upgrade_clicks` times and stops — no
  cash reads, no stall counting, no `upgrade_stall_reads` (removed from
  config.yaml, nothing references it anymore). The insight: once a unit is
  maxed out or the next level is unaffordable, the game's OWN button rejects
  further clicks — there is nothing for the macro to detect, so detecting it
  was pure overhead that produced nothing without OCR anyway. If
  `upgrade_level_roi` happens to be calibrated and Tesseract happens to be
  installed, it still exits the moment the panel reports `N >= M` — a nice
  early-out, but no longer anything the loop depends on to function.
- **`_click_upgrade_times`** (the fixed-count mode) was already this simple
  and needed no change — its cash-before/after check is a log-only sanity
  warning that already no-ops safely when OCR is unavailable.
- Verified with the same stubbed-engine technique: `_unit_action` against the
  real `config.yaml` confirms it clicks (not taps) for all three unit
  actions, at the exact `to_screen()`-mapped `ui_anchors` coordinates; the
  new `_click_upgrade_max` spam-clicks to the cap with no OCR at all, still
  early-exits when OCR is available and reaches `N>=M`, and behaves
  identically whether or not `upgrade_level_roi` is even set. The old
  cash-stall test cases from 2.18 now fail against this version by design —
  that fallback path no longer exists.

### 2.20 Placing does not select — priority was skipping the panel entirely

Two related bugs, both reported by the user from watching a real run (not
from a log this time — direct observation of the game).

- **`_set_priority` never selected the unit.** It didn't even take `sx, sy`
  as parameters. Placing a unit only drops it — a SEPARATE click on the
  placed unit opens its info panel, which is where Upgrade/Sell/Priority
  live. `_click_upgrade_times`/`_click_upgrade_max` already clicked the unit
  first (needed for the standalone `action: "upgrade"` step type, which can
  target any previously-placed unit, not just one just placed) — priority
  was the one path missing it, so `#{id} priority -> X` could log success
  while the click actually landed on empty map. Fixed: `_set_priority(rect,
  sx, sy, step)` now selects first, exactly like the other two. Deliberately
  self-contained (not "select once at the top of `_after_place`, shared by
  all three sub-actions") — every sub-action reselects independently, so if
  Priority running first happens to leave the panel in a state Upgrade
  doesn't expect, Upgrade's own click still recovers it. A shared single
  select would not have that property.
- **`_click_and_verify`'s retry could not actually retry.** It re-clicked the
  same screen position up to 3 times on a failed placement, but never
  re-tapped the hotbar slot. If the failed click's real cause was Roblox
  dropping the slot back to unarmed (landing on invalid terrain, an overlay
  eating the click), every subsequent "retry" clicked with nothing selected
  — guaranteed to fail identically 3 times, logged as 3 separate failures
  that were actually the same one failure repeated. Now re-taps
  `step.slot` before every attempt after the first. Retry count is also
  configurable now (`execution.place_retry_attempts`, default 3, unchanged).
- Verified with a stubbed driver: `_set_priority`'s first click lands exactly
  on the placed unit's own coordinate before its second click reaches
  `priority_btn`; `_click_and_verify` re-taps the slot on attempts 2+ but NOT
  on attempt 1, succeeds without any wasted taps when the first click already
  works, and fails cleanly after exhausting `place_retry_attempts` with
  `clicks == attempts` and `taps == attempts - 1`.

### 2.20b Stage editor: moving a step created a new one instead

Reported from real use ("when I tried to move placement step it keep create
a new step"), reproduced headlessly, two separate causes:

- **A near-miss on a marker added a step.** `mousePressEvent` used
  `scene_.itemAt()` - an exact shape hit-test. `MARKER_R` is 13 *scene*
  units, and the reference image is fit-to-view, so markers render at only
  ~10 screen px radius. A press that missed by a few pixels fell straight
  through to the "clicked empty canvas → add a step" branch. The denser the
  stage, the easier to trigger; the reported profile had 12 markers.
  Fixed with `StageCanvas._marker_near()` - distance-to-centre within
  `MARKER_GRAB_R` (= MARKER_R + 12), nearest-wins so a generous radius still
  can't grab the wrong marker. Trade-off: adding a step within that radius of
  an existing one now grabs the existing marker instead; use "+ Add step" and
  drag if two really need to be that close.
- **An armed "Move" clicked onto another marker did nothing.** The marker
  branch intercepted first, so the move stayed armed and the click was
  swallowed - and the spot you want to move a step to is very often right
  next to another marker. Fixed by checking the armed move BEFORE marker
  hit-testing (same precedence calibration mode already had).
  `_start_select` now arms the canvas (`set_move_armed`) and `_on_add`
  disarms it, so the crosshair cursor also reflects the state.

Verified: a 20px near-miss now grabs the marker instead of adding (was:
added); a far-from-anything click still adds; an armed move onto another
marker moves and disarms; an armed move onto empty space moves.

### 2.21 Executor split into collaborating classes

`core/executor.py` had grown to 615 lines doing eight unrelated jobs, and
every helper reached into `self` for cfg/profile/drv/cap/log - which is
exactly what made it impossible to split or test a piece in isolation.
Now 133 lines of pure orchestration; `_run_once()` reads as the shape of a
loop and nothing else.

Behaviour is unchanged. Every case in the pre-refactor test suites was
re-run against the new structure (11 groups, incl. the retry/re-tap logic,
the priority cycle bounds, the OCR reader selection, and `run_out`'s
ordering) - see below.

```
core/run_context.py    RunContext: cfg/profile/drv/cap/log/check_stop, plus the
                       lookup helpers everything shared (execution()/game()/
                       vision(), anchor(), click_anchor(), grab_anchor(),
                       poll_until()). Collaborators HOLD one rather than
                       inheriting - none can reach into another's internals.
                       Also owns StopRequested (re-exported from executor).
core/unit_panel.py     UnitPanel: select/deselect + the Upgrade/Sell/Priority
                       controls, incl. the priority cycle-and-read-back and
                       both upgrade modes.
core/actions/          One class per profile action, replacing the if/elif
                       chain: place.py (+ its verify/retry and after-place
                       bundle), upgrade.py, sell.py, ability.py, wait.py.
                       Add an action = add a module + list it in
                       ACTION_CLASSES; no dispatch code to edit.
core/step_runner.py    PreconditionWaiter (the cash/wave/delay gate, and which
                       OCR reader each type needs) + StepRunner (resolve
                       target_step, dispatch, note log, inter-step gap).
core/stage_setup.py    StageSetup: in-stage gate, teleport, camera normalize,
                       reference verify, Start Game.
core/match_flow.py     MatchFlow: wait out the match, clear reward screens,
                       read the result screen, click Repeat. run_out() owns
                       the ordering (see its docstring - recording MUST happen
                       while the result screen is still up).
core/run_recorder.py   RunRecorder: screenshot + SQLite row + Discord. Takes an
                       on_result callback rather than a Qt signal, so it works
                       without Qt.
core/executor.py       Executor(QThread): builds the collaborators on the
                       worker thread (InputDriver's ctypes handles must be
                       created there), runs the loop, emits signals.
```

Public API is untouched - `main.py` needed no changes. Same constructor,
same `log`/`state`/`progress`/`result`/`finished` signals, same
`request_stop()`/`start()`/`wait()`.

Two things worth knowing before extending this:

- **Actions receive a `Target`** (`actions/base.py`) carrying the resolved
  position in BOTH coordinate systems - normalized and screen pixels. Both
  are needed: pixels to click with, normalized to build the placement
  verification ROI from. It's the RESOLVED position, so an upgrade/sell step
  pointing at another step via `target_step` already reads as that step's
  spot (HANDOFF 2.7).
- **`MatchFlow.run_out(rect, record)` takes the recorder as a callback**
  rather than calling it directly, because the ordering constraint is
  MatchFlow's to enforce, not the Executor's: record must happen after the
  result screen appears (that's the only place this game names the outcome)
  and before Repeat is clicked (which replaces the screen the screenshot
  needs). Keeping those three next to each other in one method is what stops
  that ordering being re-broken later.

---

### 2.22 Mouse only — every keystroke to the game is gone

User instruction, direct: *"change every keyboard key with mouse (every
key!)"*. This finishes what 2.19 started (which flipped Upgrade/Sell/Priority
from keys to clicks but left three key presses behind). **Nothing the macro
sends to the game is a keystroke anymore.** Verified with a stubbed driver
that records every event: place, ability, all three unit-panel actions,
camera normalize and teleport produce zero key events on every path,
including the retry paths.

The four that were left, and what replaced each:

- **Hotbar slot select (`tap("1")`…`tap("6")`) → click the card.** This was
  the one the user named. New `core/hotbar.py`. The bar is **centre-anchored**
  — it grows outward from the middle — so slot 1's x depends on how many
  units the loadout carries, and six hard-coded coordinates would silently
  mis-click every different-sized loadout. Geometry is stored instead
  (`game.hotbar`: `slot_count` / `center_x` / `y` / `spacing`) and each card
  is derived: `x = center_x + (slot − (count+1)/2) × spacing`. Measured off
  `profiles/Untitled_stage_ref.png` (a real 1280×720 capture, 6 units): card
  edges at 410–481, 487–559, 565–636, 642–713, 719–791, 797–868, i.e. centres
  77.4px apart (0.0605) at y=650 (0.903), symmetric about x=640. The formula
  reproduces all six to within 1px. `game.hotbar.slots` (explicit `[x, y]`
  pairs) overrides it entirely if a bar ever doesn't follow the pattern.
  `Hotbar.select()` returns False for a slot the bar doesn't cover, and
  place/ability **skip the map click** in that case rather than clicking with
  nothing armed. `_click_and_verify` re-arms by clicking the card on retries,
  same rule as 2.20.
- **`game.use_unit_keys` / `game.unit_keys` deleted.** The escape hatch that
  pressed [T]/[X]/[R] is gone, not just defaulted off — `UnitPanel.action()`
  has one code path now, and it's the one every run exercises.
- **`game.teleport_key` deleted → `game.teleport_btn`** (a normalized click
  target, unset by default, so the teleport step no-ops). This also closes
  the open item that `"t"` was both the teleport guess and the confirmed
  in-game Upgrade bind. Losing it is cheap: **nothing in this macro ever
  moves the character**, so a run that starts at spawn stays at spawn —
  teleport was only ever a recovery path for a character walked away by
  hand, and `reference_matches()` is what actually catches a bad starting
  position. Set `teleport_btn` if the game turns out to have a clickable
  teleport control.
- **Shift Lock (`tap("shift")`) → right-button drag** in `core/camera.py`,
  reverting 2.3's technique but keeping its structure (focus click → zoom-in
  clamp → pitch-down clamp → zoom-out clamp; all hard clamps, still no
  per-stage tuning). Right-drag rotates the Roblox camera without any key,
  and this **deletes 2.3's worst failure mode along with the keystroke**:
  Shift Lock had no queryable state, only a toggle, so a process that died
  mid-sequence left the next run's tap turning it OFF instead of ON —
  silently corrupting every coordinate that run touched. A drag holds no
  state between runs. `camera.shift_lock_settle_ms` removed. Caveat: the
  drag is vertical, so it pitches but does not reset **yaw** — 2.3 got yaw
  free from the teleport reset, which is now off by default. Nothing here
  turns the camera sideways either, so yaw only drifts if the user spins it
  by hand; the reference check catches that.

New readiness row, **Hotbar slots**: red if any place/ability step uses a
slot outside the configured bar (with the fix — set `slot_count` to your
loadout size), green listing the slots in use otherwise. A wrong
`slot_count` is now the one way to silently mis-click every placement, so it
gets a check rather than a log line.

`InputDriver`'s key methods and scan-code table stay — unused by the run
path, kept so key support doesn't have to be rebuilt if some future control
turns out to have no clickable equivalent. The macro's own **F9/F12 global
hotkeys are unaffected**: those are RegisterHotKey listeners for the user,
not input sent to the game.

---

### 2.23 Loop count deleted; the slot field is a "Unit" dropdown

Both from the user looking at the running UI.

- **The "Loops" spin box is gone and every run is infinite.** The user's read
  of it: *"they [the arrows] are not even functional"* — the box showed the
  word `infinite` (its `setSpecialValueText` for 0) and stepping it looked
  like nothing happened, because 0 → 1 replaces the word with a number
  rather than doing anything visible. Rather than making the arrows clearer,
  the whole control went: it defaulted to infinite, a farming macro is
  something you stop when you're done, and Stop / F12 already does that.
  `SetupRunPanel.loops_changed`, `App.loops` and `App._set_loops` are all
  removed; `Executor(..., loops=0, ...)` is passed literally, and the
  Executor's own `loops < 0` = infinite handling is untouched (so a future
  caller can still bound a run). Screenshot now spans the row the spin box
  vacated.
- **`Hotbar key` → `Unit`, spin box → dropdown of 1..N.** Same reasoning as
  2.22: the field stopped being a keystroke, so calling it a "key" was a lie,
  and its 1–9 range could name cards that don't exist. The list is built
  from `game.hotbar` via `hotbar_slot_count()`, the same source
  `core/hotbar.py` clicks from, so the editor can't offer a slot the run
  can't click. Both places that edit a slot use it: the per-placement
  `IndexCard` and the shared "Selected step" form.
  `set_slot_value()` handles a profile saved against a **bigger** loadout —
  `QComboBox.setCurrentText()` on a missing entry is a silent no-op, which
  would have displayed (and then saved) some other slot, quietly rewriting
  the user's steps. It appends the impossible value instead so it stays
  visible and the Readiness "Hotbar slots" row can flag it.

---

### 2.24 One steps table, and a canvas click can no longer create a step

Two reports in one message, and they turned out to be the same problem seen
from two sides.

**The bug: *"every time I tried to move, it keeps creating a new one."*** Not
a regression of 2.20b - that fixed a near-miss ON a marker. This is the
other half: **a bare click on empty canvas ADDED a step** (`mark_mode`), so
a user who selected a row and clicked where they wanted it got a brand-new
step at that spot instead of a move. 2.20b's "Move" button did work, but it
was a per-card arm-then-click most people never found; the obvious gesture
did the wrong thing. Both routes are now replaced by one rule with no modes
in it:

> **A click on the image puts the SELECTED row's spot there. That is the
> click's only meaning.**

`StageCanvas.marker_added` became `canvas_clicked` (it reports a click; it
no longer names an outcome), `mark_mode`/`move_armed`/`_start_select`/
`_select_target_id` are gone, and steps can ONLY be created by "+ Add step",
which adds a row, selects it, and says "now click the image to place it".
Clicking a marker still selects its row; dragging one still moves it, and
the row's X/Y cells follow. Nothing a user does on the canvas can create a
step by accident anymore, because nothing on the canvas creates steps at all.

**The layout the user actually wanted**, drawn on paper and handed over: one
table, `POS | X | Y | Unit | What to do`. That replaced all THREE step views
(the `IndexCard` grid, the read-only "All steps" table, and the shared
"Selected step" form) with a single `StepRow`-per-row table. Consequences
worth knowing:

- **"What to do" is Place / Upgrade to N / Upgrade to max** - i.e. it edits
  `upgrade_mode` on a step whose action is always `place`. The N spin box
  shares the cell and only appears for "Upgrade to N", so the table keeps
  the four columns as drawn. A profile carrying a `sell`/`ability`/`wait`
  step still loads: its action is appended to that row's combo and selected,
  so it round-trips instead of being silently rewritten into a placement.
- **X and Y are editable** (0-1, 3 decimals) as well as click-set, so a spot
  can be nudged without touching the canvas.
- **Priority, wait conditions, notes and `target_step` are no longer
  editable** - they weren't in the drawing. The fields still exist in
  `data/profile.py` and the executor still honours them; saved values
  round-trip untouched. Cash gating (`wait: cash >= N`) is the one that
  might be missed - re-add a column if it's ever wanted.
- Row edits **never rebuild the table**. Rebuilding destroys the widget the
  user is still holding - the same trap the card grid hit ("can't save after
  editing"). `_refresh_list()` is for structural changes only (add / delete /
  load); `_on_row_edited()` just redraws markers.

`ui/stage_editor.py` lost ~300 lines net.

---

### 2.25 Placement retries until it verifies, and the verify got a lot harder to fool

User ask: *"I want the macro to keep placing until it was placed - is there a
way to detect it?"*

**The retry policy was wrong, not just short.** Three fast attempts and skip
(2.20) treats "not enough cash yet" as an error, when it's a *not now* that
resolves itself in a few seconds of wave income. Now `PlaceAction` keeps
clicking on a slow interval until the placement verifies or
`execution.place_timeout_s` (default 45s) expires -
`place_retry_attempts` is gone. Each retry still re-arms the hotbar card
first (2.20's reason is unchanged). The waiting is the point: an expensive
unit scheduled early just needs a longer `place_timeout_s`.

**The detector could not tell a placement from an enemy walking past.** The
old check was one before/after diff of the map under the marker, and
`region_changed(ground, enemy) == region_changed(ground, unit) == True` -
the two cases are indistinguishable to it. What separates them is not
*change* but *permanence*: a placed unit is new, stationary and stays;
traffic keeps moving. So `_settle()` reads the ROI every
`place_settle_interval_ms` (250) until **two consecutive reads agree**, up to
`place_settle_reads` (6), and only then compares against the baseline:

| after the click | verdict |
|---|---|
| settled, differs from baseline | **placed** |
| settled, matches baseline | not placed - click again |
| never settled | can't judge - click again, and say so at the end |

Three things that fall out of this and are easy to get wrong later:

- **The baseline is settled too**, not just snapped before the click. A
  baseline captured while an enemy happened to be crossing the spot is
  poisoned: the empty ground that follows differs from it, so an *unplaced*
  unit reports itself placed. This was a real failure in the test suite
  before the baseline got the same treatment.
- **A "settled, unchanged" read re-baselines.** Over a 45s wait, slow drift
  (lighting, a HUD element bleeding into the ROI) would otherwise accumulate
  until it crossed the change threshold and faked a placement.
- **"Never settled" is not treated as placed.** Guessing "placed" there
  would silently skip a unit; guessing wrong the other way just costs
  another click on a tile that's usually occupied anyway. The failure log
  distinguishes the two causes - a mostly-busy ROI says the marker may be
  sitting on the enemy path, otherwise it points at cost/placeability.

Still true: this cannot tell a real placement from a **queued ghost**, so
phantom/pre-placement must stay OFF (section 7). And a failed placement is
still logged-and-continued rather than aborting the loop, because a farming
run losing one match beats a run that stops.

Verified with a simulated game feeding scripted frames: placed on the first
click; placed on the 12th when unaffordable until then (the old code gave up
at 3); gave up loudly when never affordable; an enemy crossing an empty spot
did NOT read as placed; a real placement during traffic still verified once
the spot cleared; a poisoned baseline did not produce a false positive; and
non-stop traffic failed with the "never stopped moving" diagnosis rather
than a wrong verdict.

---

### 2.26 The map is the wrong thing to watch - verify with the unit's own panel

2.25's settled-ROI check survived one real run and then failed exactly where
it was weakest. From the log:

```
:08 Step #1: place unit slot 5
:09 Step #2: place unit slot 5
:24 #2 placed on attempt 8.
:24 Step #3: place unit slot 1
:26 Step #4: place unit slot 1 (upg max)
```

Step #3 "verified" in 2s. It cannot have placed anything: the stage starts
at ¥600, slot 5 costs ¥550, so #1 left ~¥50 and #2 spent the next 15s
earning its own ¥550 - and slot 1 costs ¥850. There was no money.

The cause is geometry, and it was hiding in the profile all along:

| step | position | verification window (px) |
|---|---|---|
| #1 | 0.440, 0.545 | its unit lands at **(563, 393)** |
| #2 | 0.456, 0.489 | x 545-621, y 330-373 |
| #3 | 0.491, 0.449 | x 590-667, y 301-344 - **unit #2 (583, 352) is inside this** |

The window is `r = 0.03` around the marker: 77x43px, about the size of a
unit model. On a real stage the markers are packed closer than that, so a
step's window contains the unit the PREVIOUS step just placed - and that
unit's spawn animation finishing is a change that settles and stays.
"Settled + different from baseline" describes it perfectly. Every refinement
in 2.25 (settling, a settled baseline, re-baselining) filters things that
MOVE; none of them can filter a neighbour that appears once and then sits
there, because that is indistinguishable from the thing being detected.

**So stop watching the map.** A placed unit has an unambiguous tell that
isn't on the map at all: clicking it opens its info panel. Each attempt is
now: click to place → park the cursor → click the spot again to select
whatever is there → did the panel open? `upgrade_level_roi` (the "Upgrade
N/M" caption, already measured) is empty with nothing selected and shows
text with a unit selected. It's static UI in a fixed position - no
neighbours, no animations, no enemy traffic, nothing on the map can fake it.

- If the first click placed the unit, the card is spent and the second click
  selects it → panel opens → verified.
- If the first click failed and the card is still armed, the second click is
  just another placement attempt. Costs one extra iteration, converges.
- `cursor_park` (config, default `[0.02, 0.5]`) moves the mouse off the spot
  before judging. An armed card draws a preview under the cursor, so a
  cursor parked on the marker sits inside whatever is being checked.
- A plain "Place" row now deselects at the end - panel verification leaves
  the panel open, and it would cover the map for the next step.

The map check survives as the **fallback** for when `upgrade_level_roi`
isn't calibrated, unchanged. Its own test suite is still green; it's just no
longer what runs.

Verified by reproducing the exact reported situation - an unaffordable unit
whose window contains a neighbour that finishes spawning mid-step. The map
check calls it placed (bug reproduced); the panel check reports "no unit
panel ever opened there, so nothing was placed"; and it still verifies a
real placement, on the first attempt or the fifth.

**Also worth telling the user**: their profile's steps #3 and #4 are two
placements at the SAME spot (0.4914, 0.4486 and 0.4910, 0.4490), the second
one carrying `upg max`. That looks like "place it, then upgrade it" written
as two rows back when the editor made that natural. In the 2.24 table it is
one row: What to do = "Upgrade to max". The second placement can only ever
fail - the tile is occupied.

---

### 2.27 Upgrading is its own row, and every level is verified

User's description of the flow they want: *"1. Select the position first
2. Unit 3. If you want to upgrade that unit enter the same pos to make mouse
click that pos and select how many upgrade (no timeout, just click until it
upgrades)."*

That is a different model from 2.24's, and a better one. Upgrading was a
MODIFIER on a placement row (`upgrade_mode` on a `place` step, applied by
`_after_place`). It is now its own **row at the same position**, which reads
the way the run actually behaves: click the spot, work the panel.

- **"What to do" now picks the action**, not a post-place extra:
  `Place` → `place`, `Upgrade to N` → `upgrade` + `times`, `Upgrade to max` →
  `upgrade` + `upgrade_mode="max"`. The Unit column greys out on upgrade rows
  (they act on whatever is standing there). Position resolution is unchanged
  (`Step.anchor()`), so a row can carry its own coordinates - the normal case
  now - or still point at another step via `target_step`.
- Old profiles are NOT rewritten. A `place` row carrying a bundled
  `upgrade_mode` shows its `summary()` as a fourth combo entry and keeps
  working through `_after_place`, which is still there. Only the editor
  stopped creating them.

**"Click until it upgrades" needed a way to know an upgrade happened**, and
there is one that needs no OCR: the panel's "Upgrade N/M" caption changes
when a level is bought. `UnitPanel.upgrade_once()` clicks Upgrade and waits
for `upgrade_level_roi` to change, retrying on `upgrade_retry_interval_ms`
until it does. "Nothing happened" is nearly always "can't afford the next
level yet" - a wait, not a failure - which is exactly the mistake 2.25 fixed
for placement, repeated here for upgrades. `upgrade_timeout_s` (120s, per
level) is only the give-up guard; reaching it IS the signal for "maxed out
or never affordable", which is what ends `Upgrade to max`.

This replaces 2.19's spam-clicker, which fired `max_upgrade_clicks` clicks
blind and could report `activated 30 time(s)` having bought nothing - the
exact line in the user's log that started this. 2.19 was right at the time
(there was no signal without Tesseract); the level-caption diff is a signal
and needs no Tesseract. `max_upgrade_clicks` survives as the hard bound on
levels per unit.

The same region also answers "is a unit even there": it's blank with nothing
selected, so `select_verified()` refuses to upgrade empty ground and says
which spot was empty (`no unit at 0.491, 0.449 - the placement for this spot
probably failed`) instead of clicking Upgrade at nothing 30 times. Same
signal as 2.26's placement check - one small, static, well-behaved region
doing all the work.

Verified with a simulated panel: N levels bought and reported; a level that
takes five clicks' worth of waiting still lands (it waits rather than moving
on); a unit that maxes early reports `got 2 of 5 level(s)`; `Upgrade to max`
buys until the button stops working; and an upgrade row over empty ground
issues zero Upgrade clicks.

---

### 2.28 A mismatched camera now stops the loop instead of placing at the map edge

Reported: *"there's a bug when cam doesn't match the screenshot - the macro
places at the edge of the screen."*

Not a coordinate bug. Every click position is fixed by the profile, so a
wrong camera doesn't nudge them - it changes what those positions MEAN. At a
shallow angle a click aimed at mid-screen hits the ground plane far away,
near the horizon, so the unit lands at the far edge of the map. That is
exactly what "the camera didn't normalize" looks like from the outside, and
the run was **designed to continue anyway**: `abort_on_ref_mismatch`
defaulted to `false`, so the mismatch was logged as a warning and every
following step ran against coordinates that no longer meant anything.

Three changes, and the middle one is the one that matters:

- **`vision.ref_match_threshold: 0.92 → 0.65`.** 0.92 was never reachable: a
  *correct* camera scored **0.789** on the real run in 2.19. The compared
  frame contains moving enemies, a ticking wave counter and a changing cash
  readout, so a perfect score isn't a thing. The old default therefore
  reported "mismatch" on every single loop, which is precisely why the
  non-fatal path existed - the check had been calibrated into uselessness and
  then routed around. **Flipping the abort default without fixing the
  threshold would have blocked every run instead.**
- **The camera sequence is retried before giving up** (`camera_attempts`,
  default 3). Worth doing because it has a known flaky step: Roblox must
  capture the mouse for the drag to register, and the focus click that
  arranges that can be swallowed. `StageSetup.normalize_and_verify()` now
  owns normalize-then-check-then-maybe-again, and the executor calls that
  instead of driving the two separately.
- **`abort_on_ref_mismatch` now defaults to `true`**, so a loop that can't
  get the camera right skips the match rather than filling the map with
  misplaced units. With auto-repeat and infinite loops that could spin
  forever doing nothing, so `execution.max_consecutive_aborts` (3) stops the
  whole run after three loops in a row that ended before a single step ran.
  `_run_once()` returns False for those; a loop that reached its steps resets
  the counter.

**Tuning is now a measurement, not a guess.** "Test camera view" prints the
live reference score and says whether a run would accept it - point the
camera somewhere you can SEE is right, press it, and set the threshold just
under what it reports. Without that, picking this number blind either blocks
every run or lets a bad camera through, and the user has no way to tell which
they've done until units start landing at the edge again.

Verified with a fake camera: correct first time → accepted after one
normalize (0.988); wrong first time then fixed → retried and accepted;
never right → refused after 3 attempts and reported the best score it saw,
so no step ever reached the map.

Also fixed in passing: a stray `they` on its own line at the end of
`main.py` (a chat message that landed in the editor). At module scope that
is a `NameError` at import - the app would not have started.

---

### 2.29 Verify BEFORE placing - the retry loop was stacking units

Reported with a screenshot: *"macro keep placing even it already placed."*
The log read `#1 placed on attempt 5` / `#2 placed on attempt 5` with ¥3,925
banked - those were not four unaffordable attempts. Each retry placed
another unit. Five units where one was wanted, twice.

Two faults, and the first is the design one:

**1. Verification ran AFTER the placement click.** 2.25/2.26 assumed a
failed placement leaves nothing behind, so retrying costs nothing. That holds
only while the check never returns a false NEGATIVE. The moment it does, the
retry re-clicks an *occupied* tile - and if the tile is only "occupied"
because the last attempt worked, that just places another unit. The loop is
now inverted: **every iteration asks "is a unit already here?" first, and
only issues a placement click at a spot it has just confirmed empty.** A
false negative can then cost an extra select-click; it can no longer cost an
extra unit.

**2. The likely source of the false negative: placing auto-selects.** The
game opens the new unit's panel by itself, and clicking a selected unit
toggles the selection back OFF. The old sequence was click-to-place →
click-to-select → read the panel, i.e. it closed the panel it was about to
look for. `_unit_is_there()` therefore **reads the panel before clicking**
and only clicks to select when nothing is selected. Both games are covered:
one that auto-selects and one that doesn't.

**And the bug that made it certain rather than likely:** `execute()` armed
the hotbar card up front (left over from when the loop armed only on
retries), so the loop's very first "is a unit here?" click landed with a
live card and placed a unit - one extra per step, every step, before any
verification logic ran at all. `execute()` now resolves the card position
without arming it (`Hotbar.position`, not `Hotbar.select`); arming belongs to
the loop, immediately before each placement click. This was caught by the new
test, not by reading - the two mechanisms produce identical logs.

Verified against a simulated game: a game that auto-selects on placement gets
exactly **1** unit (was 5); a game that doesn't also gets 1; an unaffordable
unit gets 0 and says so; and a spot that ALREADY holds a unit gets nothing
added - the loop recognises it and returns immediately.

Also, per the same message: **`game.start_game_wait_ms` 1500 → 400.** The
first placement is gated on its own verification anyway, so that wait was
pure delay.

---

### 2.30 The verification baseline has to be absolute, not "what was on screen a second ago"

Reported: *"runs very fine in the first round, but on the second round the
place-until-placed doesn't work."* Loop 2's log:

```
22:30:38 Step #1: place unit slot 5
22:30:39 Step #2: place unit slot 5     <- 1s later, no "placed after N"
22:30:41 Step #3: place unit slot 1
22:30:52 #3 placed after 5 attempts
22:30:52 #4: no unit at 0.493, 0.454 - nothing to upgrade
```

Steps #1 and #2 "succeeded" in about a second each without placing anything,
and #4 proves #3 didn't place either.

**The check was relative.** Each place step snapshotted the panel region at
its own start and asked "did this change?". That is only equivalent to "is a
unit selected?" if the snapshot was taken with nothing selected and nothing
moving - and on loop 2 it was neither:

- **A panel left open by the previous step.** The snapshot then records the
  OPEN panel. The next check clicks the spot, that click CLOSES the panel,
  the region changes - and a change reads as "a unit is here". The check
  reports a unit precisely when there isn't one.
- **A loop starting mid-transition.** Loop 2 begins the instant Repeat Stage
  is clicked, with the screen still wiping. The snapshot catches the
  transition; a moment later it clears, which is also a change, which also
  reads as "a unit is here". Loop 1 started from a settled stage, which is
  exactly why loop 1 looked perfect.

**Fix: one absolute reference per loop.** `StageSetup.capture_panel_baseline()`
runs after Start Game - the single moment in a loop that is provably empty,
because no unit has been placed yet, so nothing CAN be selected. It settles
the region first (a baseline caught mid-animation isn't a baseline) and
stores it on `RunContext.panel_empty`. Every later check is
`ctx.panel_shows_unit(rect)`: current versus that fixed picture. Nothing
compares against "a moment ago" anymore.

Three supporting changes, each closing a way the same class of bug gets back
in:

- **A place step deselects anything left selected before it starts.** Even
  with an absolute baseline, a leftover panel from an earlier step means
  "something is selected" - and every check reads that as "a unit is standing
  on THIS spot". It belongs to a different unit.
- **`UnitPanel.select_verified()` does the same** before selecting its
  target, for the same reason: otherwise an upgrade row can act on whichever
  unit was already selected.
- **`deselect()` verifies itself and has a fallback.** If `deselect_btn` is
  mis-calibrated the panel never closes; it now clicks bare ground
  (`cursor_park`) as a second attempt - which works regardless of that anchor
  being right - and warns once if the panel still won't close. Safe because
  no hotbar card is ever armed at a deselect: arming is immediately followed
  by its placement click.

Verified with a simulated game covering both original failures: with the old
per-step baseline, a leftover panel and a mid-transition start each place
**0** units (bug reproduced); with the per-loop baseline both place exactly
1, including when `deselect_btn` is broken and the ground-click fallback has
to clear the panel; a clean start still places exactly 1; and the baseline
capture waits out a 2-frame transition instead of recording it.

### 2.31 Upgrade-to-max stops at the real max (OCR), and match-end/repeat got a reliable third signal

Two reports in one: *"macro not stop after done upgrade to max"* and *"add
repeat stage system"* (an auto-repeat already existed - the ask was to make it
actually fire).

- **Upgrade-to-max hammered a maxed unit for the full timeout.** `upgrade_once`
  confirms a level bought by a pixel-diff of the "Upgrade N/M" caption, which
  cannot tell "maxed out" (will NEVER change) from "can't afford the next level
  yet" (changes once income arrives) - both read as "nothing changed". So a unit
  that was already max got its dead Upgrade button clicked every ~1.6s for the
  whole `upgrade_timeout_s` (120s) before the loop gave up. Fix:
  `UnitPanel._read_level()` reads the N/M caption via `ocr.read_fraction`, and
  `upgrade_max`/`upgrade_times` check it at the top of each iteration - N>=M
  stops immediately. The user chose the OCR route (over a shorter blind
  timeout), so this needs Tesseract; without it, it falls back to the old
  pixel-diff give-up unchanged. The pixel-diff still confirms each individual
  buy - OCR is only the max detector.
- **Match-end detection now also triggers on the result screen itself.**
  `wait_for_match_end` watched only the win/loss banner (scale/timing sensitive)
  and the reward caption. A loss shows no reward screens, so if its `defeat.png`
  matched poorly the loop sat until `result_timeout_s` (15 min) and never
  repeated. Added the result screen (its Repeat Stage button, `result_repeat.png`,
  matches ~1.0 on BOTH win and loss) as a third end-of-match signal. Combined
  with the same session's bug-1.1 fix (bounded wait for the caption/result
  screen before "nothing to clear") and bug-1.7 fix (click Repeat at the
  template-matched column, not the fixed win-layout anchor), the repeat loop now
  closes on a win and a loss. Repeat uses templates only - no Tesseract needed.

Both unverified against the live game - needs Tesseract installed for the max
readout, and one supervised loop to confirm repeat fires on a real win and loss.

### 2.32 The N/M readers never actually worked on a real Tesseract engine

Tesseract got installed on the Windows machine (v5.4.0, UB-Mannheim) and the
first real read exposed this: `read_fraction` and `read_leading_int` were only
ever "verified" against a STUBBED engine that handed them pre-split digit
groups (HANDOFF 2.18/2.12). Against the real engine they were broken, same root
cause for both - Tesseract returns "N/M" as a SINGLE token, and with a
digits-only whitelist the slash is stripped so N and M concatenate:

- `read_fraction("Upgrade 0/8")` returned `(None, None)` - `_scan` gave one
  group `"08"`, never the two it needed. So the 2.31 upgrade-to-max stop, which
  depends on it, was dead: it would never see N>=M.
- `read_leading_int("0 / 15")` returned `15`, not `0` - the exact wave-gate
  desync 2.12 believed it had fixed. Any `wave >= N` with N<=total passes on
  the first poll.

Fix: a `_read_slashed()` helper reads with the slash KEPT in the whitelist and
returns the raw "N/M" string; `read_fraction` regexes out the `(d)/(d)` pair
(last one, so a label like "Upgrade" can't interfere) and `read_leading_int`
takes the first digit run before the slash. `read_int` (cash) is unchanged - it
joins groups and has no slash. Verified against rendered captions: read_fraction
and read_leading_int now correct for 0/8, 3/8, 8/8, "0 / 15", "12 / 15", etc.

Still to check live: `read_int` on a comma cash value ("2,003"). A synthetic
Arial comma OCR'd as a "1" (-> 21003); the real HUD's comma showed up as a
group GAP in the 2.12 captures (-> rejoins to 2003), but confirm with the
Calibrate tab's "Test read cash" on the live HUD - an over-read cash would let
an underfunded placement through.

### 2.33 Camera set once per run, and the log no longer slows the app down

Two user reports.

- *"set view 1 time per stage join and not change after pressing start"* - the
  camera was normalized+verified on EVERY loop, and re-running that flaky
  sequence each round is what corrupted a good camera and then failed the
  reference check ("mismatch screenshot"). Repeat Stage restarts the same stage
  without moving the camera and nothing here moves the character, so the
  top-down view set on entry holds. `Executor` now normalizes+verifies ONCE per
  run and reuses it for every repeat, gated by `execution.normalize_camera_once`
  (default true; false restores per-round normalize+verify). Gated on a
  `_camera_set` flag rather than `loop_no == 1`, so a first attempt that aborts
  on mismatch still retries next loop instead of skipping the camera forever.
  Risk it trades for: if the camera ever drifts mid-session, nothing re-checks
  it - units land at the map edge and the fix is to stop and Start again.
- *"app runs slow after each click"* - `LogPanel` was a `QTextEdit` that grew
  without bound. A farming run emits many lines per loop, and QTextEdit
  re-lays-out its whole document on every insert, so each logged action got
  slower than the last. Switched to `QPlainTextEdit` with
  `setMaximumBlockCount(600)` (a ring buffer - O(1) append, oldest lines drop)
  via `appendHtml`, keeping the per-line colour. Also fixed RELEASE_REVIEW 1.4
  in passing: the GUI-thread Test camera / Screenshot / Test read handlers each
  did `vcap.Capture()`, leaking an mss handle per click; they now share one
  `App._shared_cap()` (the executor keeps its own on the worker thread - mss
  handles are per-thread).

### 2.34 L-shaped side-dock dashboard + Nocturne theme (branch: dashboard-side-dock)

Implemented from `design_handoff_dashboard_side_dock` (README + a 1920x1080 HTML
mock). Layout + visual redesign only - every panel class keeps its public methods
and signals, so no run logic changed.

- **Layout**: the bottom bar is replaced by a dock around the game. The game is
  pinned TOP-LEFT (new `RobloxWindow.layout(pin=(x,y))`) instead of centered,
  which frees the column to its right and the strip beneath it. It is ONE
  full-screen frameless `MainWindow` with a **click-through mask** cutting a hole
  where the game is (`setMask(screen − game rect)`), so the control column and
  the log strip read as a single surface wrapping the game rather than two
  separate windows. Two child hosts (`_column_host`, `_log_host`) hold the panels
  (Setup & Run over [Readiness | Statistics+Webhooks]; log strip below). The hole
  is unpainted + click-through, so Roblox shows through it, receives real and
  synthetic clicks, and `mss` reads the true game pixels. `MainWindow.place(game,
  screen)` positions the hosts and sets the mask; `main.py:_layout_docks` calls it
  at startup (expected rect), on attach (game's OUTER window rect via new
  `RobloxWindow.window_rect()`), and from the watchdog on move. `BAR_H` retired
  (kept = 0 for import compatibility); `MARGIN/GAP/COL_W/GAME_W/GAME_H` drive
  geometry.
- **Theme**: `DASHBOARD_QSS` retuned to the Nocturne tokens (ground #10111C,
  surface #232532, blurple accent #9184D9 / accent-300 #D2CEFD, low-chroma OK/
  WARN/BAD, 8px card/input radius, 4px log well). Buttons are OUTLINED (transparent
  ground, 1px border; primary=accent, danger=muted red, ghost=none). Section
  labels are the QGroupBox titles, upper-cased in code (Qt QSS has no
  text-transform). App font is Inter with a Segoe UI fallback (`setFamilies`).
- **Known deviations from the mock** (Qt QSS limits / judgement calls): the two
  dock windows keep their OS title bars (movable/closable - safer than frameless
  for a live tool; flip to `Qt.FramelessWindowHint` for the exact look); no
  Phosphor icon glyphs (icon font not bundled - status dots use the existing
  HTML-entity bullets); no letter-spacing or box-shadow (unsupported in Qt QSS).
  Inter falls back to Segoe UI unless Inter is installed.

Kept on a branch so the working bottom-bar build stays on `main` until this is
verified live (attach, confirm the docks frame the game with no overlap).

### 2.35 Stage editor rethemed to Nocturne (Stage Editor.html)

The editor already shared `DASHBOARD_QSS`, so this was colour/label polish to match
the `Stage Editor.html` mock, no structure or behaviour change:
- Marker colours are the mock's Nocturne set: placement `#9184D9` (accent),
  upgrade `#D9A45C`, selected-ring `#D2CEFD`; calibration overlay cyan `#5CC2D9`;
  canvas ground `#050507`. The legend picks these up automatically.
- "Stage" label is muted (not a section head); "THIS RUN" and the table headers
  (`# X Y UNIT WHAT TO DO`) are upper-cased in code (Qt QSS has no text-transform).
- `QHeaderView::section` is now transparent with just a bottom divider (was a
  filled block). The status line defaults to accent-300, level still overrides.
- Editor window keeps its OS title bar (the mock draws a custom one) - it's a
  user-moved floating window, so a draggable frame is more practical than
  frameless; a deliberate, minor deviation.

**Not done - the dashboard "Console + Current Process" split** from the updated
README: the Console is specced as a separate raw executor trace (window-find
results, coordinates, poll state), which is a NEW data stream, i.e. a behaviour
change the "visual + layout only" constraint rules out. The only dashboard VISUAL
mock is the single-log version, which the current build matches. Revisit if a real
console stream is wanted.

### 2.36 Two live-run bugs: upgrade-to-max stopping early, and round-2 select failing

Both reported with screenshots from a real farming run.

- **Upgrade-to-max stopped at 5 on a unit that goes to 8.** The panel read
  "Upgrade 5/8" but the log said "maxed at 5/5" - OCR misread the max (8 -> 5),
  and `upgrade_max`/`upgrade_times` had a top-of-loop `if N>=M: break` that took
  the misread at face value. Fixed by making the level-CHANGE the primary "a
  level was bought" signal (the pixel-diff already in `upgrade_once`) and reading
  N/M ONLY on a no-change, inside `upgrade_once`, to tell maxed from can't-afford.
  A buyable level changes the readout and is counted before OCR is ever consulted,
  so a misread max can no longer stop early. The fast-stop at true max (2.31) is
  kept: on no-change, N>=M returns immediately instead of waiting the timeout.
  Verified with a sim: real-max 8 with OCR stuck reading max=5 now reaches 8;
  a genuine 3/3 still stops at 3.
- **Second loop couldn't find a unit the first loop placed fine** ("#6: no unit
  at 0.471, 0.592"). Root cause chain: `deselect()`'s bare-ground fallback clicked
  `cursor_park` `[0.02, 0.5]`, which is INSIDE the bottom-left unit panel
  (~x 0.01-0.33, y 0.30-0.71), so it hit the open panel instead of the map and
  never closed it ("the unit panel won't close" in the log). The stale panel then
  poisoned the next step's selection on loop 2. Fixed with a separate
  `execution.deselect_point` (default `[0.62, 0.25]`, clear of that panel) for the
  fallback click. The user's `deselect_btn` is also mis-calibrated in that profile
  - recalibrating it (Calibrate tab > "Unit panel close (X)") is the more reliable
  fix and makes the fallback moot.

### 2.37 A stuck panel skips every later placement; deselect hardened; camera-on-entry default

Reported: *"the macro isn't even placing, sometimes it moves the cursor but does
not click."* The log showed steps #2/#3 finishing in ~1s each with no "placed
after N" line, right after a "unit panel won't close" warning.

- **Diagnosis.** Step #1 placed a unit (panel auto-opens), then `deselect()`
  failed to close it. Every later step's "is a unit already here?" check
  (`panel_shows_unit`, the authoritative placement check per 2.26/2.30) then read
  that ONE leftover panel as "yes", so `_place_until_verified` returned True
  without ever arming the card or clicking - placements #2, #3 were skipped
  silently. One stuck panel breaks the entire rest of the loop.
- **Deselect hardened.** The bare-ground fallback now retries `deselect_point`
  up to `execution.deselect_attempts` (3) times, checking after each - a
  swallowed click or a frame of lag no longer leaves the panel stuck. The
  warning now spells out the consequence (later placements get skipped) and the
  fix (calibrate `deselect_btn`, or move `deselect_point` onto empty ground).
  The two reliable fixes are still user-side: `deselect_btn` is mis-calibrated in
  the reporting profile, and `deselect_point` must be over empty map.
- **Camera-on-entry is now the default** (`normalize_camera_once: false`),
  reversing 2.33's default per a direct request ("auto change camera view on
  enter the stage, without pressing Test camera view"). The camera is
  normalized+verified on EVERY stage entry now, so a camera that drifts between
  rounds is corrected automatically; `abort_on_ref_mismatch` still skips a round
  rather than placing at the map edge if a re-normalize goes bad, which removes
  2.33's original reason for defaulting to once. Still only touched on entry,
  before Start Game - never during a match.

## 3. Current state of the code

**Phases 1 through 5 are all implemented and compile/import/smoke-tested.**
Nothing has been run against the actual game yet — that's the next step,
and it will surface issues no amount of offline testing can (see open items).

**`dist\run\run.exe` was previously a stale/corrupted 11-byte file** (stray
build-script text, not a real PE binary — that's why it wouldn't open).
Fixed and rebuilt via `pyinstaller run.spec --noconfirm`; confirmed the new
`run.exe` launches and its two Qt panels actually appear. While fixing this,
`vision/result_detector.py`'s template lookup was also corrected — it used
to resolve relative to the module's `__file__`, which lands inside
PyInstaller's `_internal` bundle in a frozen build (not somewhere a user
would think to drop `victory.png`/`defeat.png`). It's now threaded in from
`main.py` as a BASE-relative path (`dist\run\vision\templates`), same as
`profiles`/`logs`/`config.yaml`. If you rebuild, use `build.bat` (now also
copies `vision/templates/*.png` into dist) rather than raw `pyinstaller`.

```
core/window.py          find + center + resize Roblox; DPI awareness; watchdog support
core/input_driver.py    SendInput (mouse abs move, click, scroll, right-drag) with
                        jitter/humanization. The key methods + a-z/0-9 scan
                        codes still exist but NOTHING in the run path calls
                        them anymore (2.22).
core/camera.py          Phase 2.5: top-down normalization - zoom-in clamp, right-drag
                        pitch-down clamp, zoom-out clamp. No per-stage tuning. No
                        Shift Lock, no keystroke (2.22).
core/hotbar.py          2.22: slot number -> the hotbar card's screen position.
                        Centre-anchored geometry from game.hotbar, so changing
                        slot_count moves every card.
core/ocr.py             Phase 3: pytesseract HUD reads (needs Tesseract-OCR installed
                        separately - pip package alone isn't enough). FOUR readers -
                        using the wrong one silently breaks the caller (see 2.12/2.18):
                        read_int joins digit groups (cash, "1,050"); read_leading_int
                        takes only the leftmost (wave, "0 / 15"); read_fraction takes
                        the LAST TWO groups as (current, max) (upgrade level,
                        "Upgrade 0/8" - the label text precedes the numbers, so
                        stray digits from it sort first, not last); read_word is a
                        separate letters-only config for short text (priority
                        label, "None"/"First").
core/executor.py        SPLIT in 2.21 - see that section for the full map. Now just
                        the QThread orchestrator; the phases below live in
                        run_context / unit_panel / actions/ / step_runner /
                        stage_setup / match_flow / run_recorder.
                        Was: Phase 3+4: QThread that teleports to spawn, normalizes camera,
                        verifies vs reference image, runs steps (OCR-gated waits,
                        place/upgrade/sell/ability, place-verify-retry until it
                        lands or times out - 2.25). A verified
                        'place' bundles in _after_place: sets targeting priority
                        (_set_priority - presses/clicks priority_btn and reads the
                        label back via OCR until it matches, see 2.18) and/or
                        auto-upgrades (_click_upgrade_times / _click_upgrade_max -
                        the "max" mode spam-clicks upgrade_btn up to
                        execution.max_upgrade_clicks and stops, see 2.19). Then
                        polls for the match ending, clicks through the reward
                        screens, classifies + records the result, and clicks
                        Repeat Stage (2.16/2.17).
core/hotkeys.py         F9/F12 global hotkeys via RegisterHotKey + hidden message window
core/notify.py          Discord webhook (embed + screenshot + loss-streak @here ping,
                        send_test() for the panel's Test button)
vision/capture.py       mss grab, grab_roi, matchTemplate, similarity, region_changed
vision/result_detector.py  Phase 4: template match victory/defeat.png, falls back to a
                        green/red color-ratio check when templates aren't present yet
data/profile.py         Step / WaitCond / StageProfile dataclasses + JSON persistence.
                        Step carries priority + upgrade_mode (place-only, bundled - see
                        core/executor.py). MAX_STEPS = 100.
data/stats.py           Phase 5: SQLite run history, loss-streak query, win/loss summary
ui/panels.py             Dashboard widgets (dark/magenta DASHBOARD_QSS theme, see 2.8):
                        LogPanel, SetupRunPanel (attach/load/screenshot/start/
                        stop/exit), StatsPanel (session AND all-time DB W/L),
                        WebhookPanel (URL + Save/Test). No more ControlPanel/
                        StatusPanel/BasePanel - those floating Qt.Tool panels are gone.
ui/main_window.py       MainWindow: the narrow (300px) dashboard - stacks the
                        ui/panels.py widgets vertically. Does NOT contain the stage
                        editor (see 2.8) - that's shown as its own separate window.
ui/stage_editor.py      QGraphicsView canvas + ONE steps table (2.24). Canvas: click a
                        marker to select its row, drag to move it, click anywhere
                        else to set the SELECTED row's spot - a canvas click can
                        never create a step. Table (StepRow per row): # / X / Y /
                        Unit / What to do, where "What to do" is Place |
                        Upgrade to N | Upgrade to max. "+ Add step" is the only
                        way to add. Second tab: Calibrate. The card grid, the
                        read-only "all steps" table and the "Selected step" form
                        are all gone. Capped at data.profile.MAX_STEPS (100).
                        Shown via .show() as its own top-level window (main.py).
main.py                 wires everything; MainWindow (dashboard) + StageEditor as two
                        separate top-level windows (2.8), Executor thread, hotkeys,
                        frozen-path handling, 2s window watchdog with jitter-tolerant
                        move detection (>3px, else DPI-rounding/DWM-margin noise spams
                        "window moved"), clean shutdown on quit, save_config() writes
                        config.yaml back (webhook Save button), Screenshot button
                        (paths.manual_screenshots, separate from the executor's
                        auto-captured logs/screenshots). attach() verifies the resized
                        client area actually matches window.client_width/height and
                        logs a loud WARNING with likely causes if not (see open item 2).
                        App.profile is now a property - see 2.8.
config.yaml              window size, camera, input timing, vision, hotkeys,
                        game.hotbar (measured) + game.teleport_btn (unset),
                        execution timeouts (incl. max_upgrade_clicks), discord. No more panels.width/gap - the
                        UI is one resizable window now, not docked side panels.
run.bat                 one-click launcher (creates venv on first run)
build.bat + run.spec    PyInstaller build -> dist\run\run.exe
```

The **Start button now runs the real executor** (F9 also triggers it; F12 is
emergency stop). Every run loops forever until Stop / F12 (2.23).

**Priority + upgrade_mode are unverified against the real game**, same
status as `ui_anchors` — `priority_btn`/`priority_options` in
`data/profile.py`'s defaults are placeholder coordinates, and
`PRIORITY_TYPES` (`first/last/strongest/weakest/closest/farthest`) is a
guess at what the game's targeting menu actually offers.

---

## 4. Data model

```python
Step:
  id: int
  action: "place" | "upgrade" | "sell" | "ability" | "wait"
  x, y: float          # normalized 0-1
  slot: int            # hotbar slot for place/ability
  times: int           # repeat count for upgrade
  target_step: int|None
  wait: WaitCond(type="none"|"cash"|"wave"|"delay", value=int)
  note: str
  priority: str         # place-only: "none"|"first"|"last"|"strongest"|"weakest"|"closest"|"farthest"
  upgrade_mode: str     # place-only: "off"|"times"(uses `times`)|"max"(spam-clicks up to execution.max_upgrade_clicks)

StageProfile:
  stage: str
  reference_image: str
  # no camera field - core/camera.py drives zoom/pitch to hard clamps for every stage
  ui_anchors: {cash_roi, wave_roi, upgrade_btn, sell_btn, priority_btn,
               deselect_btn, upgrade_level_roi, priority_label_roi,
               reward_strip_roi, repeat_btn, result_screen_roi, result_roi,
               confirm_btn}
  steps: list[Step]     # capped at MAX_STEPS = 100
```

`ui_anchors` — **measured** (2.12/2.14/2.16/2.17/2.18): `cash_roi`,
`wave_roi`, `upgrade_btn`, `sell_btn`, `priority_btn`, `deselect_btn`,
`upgrade_level_roi`, `priority_label_roi`, `reward_strip_roi`, `repeat_btn`,
`result_screen_roi`, `result_roi`. Still a **placeholder**: `confirm_btn` (no
sell-confirm dialog captured yet). `priority_options` is retired — priority
turned out to be a cycle button, not a menu (2.14/2.18).

---

## 5. Roadmap — all phases implemented, none run against the live game

| Phase | Scope | Status |
|---|---|---|
| 2.5 | Teleport to spawn, camera normalize, verify screen vs reference image (`similarity` >= `vision.ref_match_threshold`, 0.65 since 2.28), retry the camera then skip the loop if it still fails | Built: `core/camera.py`, `StageSetup.normalize_and_verify` |
| 3 | Executor: iterate steps, OCR gating, place/upgrade/sell/ability, post-place verify, retry logic | Built: `core/executor.py`, `core/ocr.py` |
| 4 | Win/loss detector (template match on victory/defeat banner, 2 consecutive frames at >= 0.85), auto restart loop | Built: `vision/result_detector.py`; template images not supplied yet, so it runs on the color-ratio fallback until `vision/templates/victory.png` + `defeat.png` exist |
| 5 | SQLite stats (`data/stats.db`), Discord webhook with embeds + result screenshot, alert on 3-loss streak | Built: `data/stats.py`, `core/notify.py` |

### Phase 3 notes

- OCR via pytesseract: `--psm 7 -c tessedit_char_whitelist=0123456789`.
  Threshold the ROI to black/white first (both polarities are tried, since
  it isn't known yet whether HUD digits are light-on-dark or the reverse).
- Executor runs on a `QThread` subclass (`core/executor.py`); it only talks
  to the GUI through signals (`log`, `state`, `progress`, `result`).
- Global hotkeys: F9 start, F12 emergency stop. Implemented in
  `core/hotkeys.py` via `RegisterHotKey` on a dedicated thread with its own
  Win32 message loop (Qt's loop doesn't pump `WM_HOTKEY`). If another app
  already owns F9/F12 system-wide, registration fails per-key and is logged
  to the status panel instead of crashing — confirmed this exact failure
  mode while testing (F9/F12 were already claimed in the dev sandbox); it
  degrades gracefully but means the physical keys may not fire on some
  machines. The Start/Stop buttons always work regardless.
- Executor aborts the whole run if the Roblox window loses foreground or
  closes (`Executor._ensure_foreground`), per design intent.
- Teleport-to-spawn is a **click on `game.teleport_btn`** and is unset (so
  skipped) by default — see 2.22 for why losing it costs nothing while
  nothing moves the character. The old `game.teleport_key` is gone.

### Phase 4 notes

- Templates go in `vision/templates/`: `victory.png`, `defeat.png`, `lobby.png`
  (a README.txt there explains the expected crops). These need to be
  cropped from real game screenshots — not yet available.
- Fallback (active by default right now): color-ratio check on
  `ui_anchors["result_roi"]` (green = win, red = loss).

### Phase 5 notes

- `data/stats.py` stores wins/losses/aborts in SQLite; `loss_streak()` only
  counts win/loss, so aborted runs don't break or inflate a streak.
- `core/notify.py` posts a Discord embed with the result screenshot attached
  and pings `@here` once the loss streak hits `discord.ping_on_fail_streak`
  (default 3). Runs on a background thread — a dead/misconfigured webhook
  logs an error but never blocks the executor.

---

## 6. Open items blocking a real run

1. ~~**Roblox window class** is assumed to be `WINDOWSCLIENT` with title `Roblox`.~~
   **Confirmed working** on a real machine (Anime Expeditions) - `attach()`
   successfully finds the window via this class/title.
2. ~~**Attach finds the window but the resize can silently fail to take**~~
   **Confirmed fixed** on a real machine (Anime Expeditions) - log shows
   `Attached. Client 1280x720 at (320, 191)`, correctly centered. Was:
   `attach()` used to log "Attached" unconditionally from whatever size came
   back, even if `SetWindowPos` never actually resized anything (looked like
   success while coordinates were quietly wrong). Fix: `RobloxWindow.layout()`
   (core/window.py) retries once with freshly-measured frame padding (the
   first padding read right after `SW_RESTORE` can be stale), and `attach()`
   (main.py) compares the resulting client size against
   `window.client_width/height`, logging a loud `WARNING` instead of a plain
   success message if they still don't match. Same real test also surfaced
   a second bug in the 2s watchdog (`_check_window`): it compared position
   with exact pixel equality, so 1px DPI-rounding/DWM-margin jitter with the
   window sitting still spammed "Roblox window moved" every ~2s - fixed with
   a >3px tolerance before it's treated as a real move worth logging.
3. **DPI scaling** other than 100% is untested. Confirmed while screenshotting
   `MainWindow` for the 2.8 redesign: this dev sandbox's Qt couldn't fully set
   its DPI-awareness context (`SetProcessDpiAwarenessContext() failed: Access
   is denied`, stderr) and rendered noticeably smaller than the requested
   1440x960 - the stage editor's split (Index grid / step-settings form) had
   to get scroll areas + minimum heights so it degrades to scrollable rather
   than one side collapsing to nothing. Re-check actual rendered size on the
   user's real machine; the window is freely resizable/maximizable now so a
   cramped default is a minor annoyance, not a blocker, but worth a look.
4. **Mostly closed (2.12/2.14/2.16/2.17/2.18).** Real captures now exist for:
   the stage (with the Start Game dialog up), a selected unit (two different
   units, giving cross-checked measurements), 5 post-match reward screens, and
   the result screen. Measured from these: `cash_roi`, `wave_roi`,
   `game.start_game_btn`, `upgrade_btn`, `sell_btn`, `priority_btn`,
   `deselect_btn`, `upgrade_level_roi`, `priority_label_roi`,
   `reward_strip_roi`, `repeat_btn`, `result_screen_roi`, `result_roi`, plus
   `victory.png`/`reward_close.png`/`result_repeat.png` as real templates.
   camera normalization is confirmed working. **Still missing**: a mid-run
   screenshot with 4-5 digit cash (`cash_roi`'s left edge is unverified past
   3 digits), a sell-confirm dialog (`confirm_btn` still a guess), a loss (for
   `defeat.png` and to confirm the reward/result flow is the same on a loss),
   and the hotbar geometry (`game.hotbar`, 2.22) is measured from one
   6-unit loadout — `slot_count` must be set to match yours, and the
   Readiness panel's "Hotbar slots" row is the check for that.
   ~~`game.teleport_key` is unverified and collides with Upgrade~~ — closed
   in 2.22: no keystroke is sent to the game at all now.
   None of this has been run against the live game yet from
   this environment - only stubbed-Tesseract logic tests were possible.
   Screenshot button: `main.py:take_screenshot`, saves to
   `paths.manual_screenshots` (default `screenshots/`).
5. **Anti-detection**: jitter and humanization exist in `input_driver.py` but
   session-level pacing (breaks every 45–90 min, daily cap) is still not
   implemented — out of scope for the Phase 2.5–5 build, tracked here only.
6. **Global hotkeys are unverified in practice.** They register cleanly when
   the combo is free, but F9/F12 were already claimed by something else in
   the sandbox this was built in — test on the real machine and rebind via
   `config.yaml`'s `hotkeys` section if needed. The Start/Stop buttons are
   the reliable fallback either way.
7. **Tesseract-OCR the binary** (not just the `pytesseract` pip package)
   must be installed separately on the user's machine for cash/wave gating
   to work; point `vision.tesseract_cmd` in `config.yaml` at it if it's not
   on PATH.
8. **Mostly closed (2.18).** Priority is now confirmed to be a cycle button
   (`priority_btn` measured, `priority_options` retired), and it's set by
   pressing R and reading the label back via OCR (`Executor._set_priority`),
   not by clicking a per-option coordinate. Still open: only `none`/`first`
   are confirmed values in `PRIORITY_TYPES` - `last`/`strongest`/`weakest`/
   `closest`/`farthest` remain a guess at the game's real option set and
   cycle order, unverified against a live run. `upgrade_mode="max"` now has
   an OCR-based primary signal (`upgrade_level_roi`, "Upgrade N/M") that CAN
   tell "maxed" from "can't afford" - it falls back to the old cash-only
   heuristic (which still can't) only when the level can't be read. Needs
   Tesseract installed and a real run to confirm the OCR path actually fires.

---

## 7. In-game settings the user must lock

Changing any of these invalidates saved profiles:
Camera Mode = Classic, Movement Mode = Keyboard, Graphics Quality locked,
windowed mode (not fullscreen).

**Shift Lock must be OFF, and stay off.** Since 2.22 the macro never
touches it — camera normalization is a right-button drag — so it no longer
toggles it on and back off. Leave it off by hand; with it ON, the cursor is
captured to screen centre and the macro's absolute mouse moves can't click
anything where it means to.

**Phantom/pre-placement must be OFF** (2.20 follow-up). With it on, clicking
to place a unit without enough cash queues a translucent "ghost" placeholder
(glowing summon circle underneath) instead of doing nothing — multiple
queued units then auto-place in cash order as funds arrive. `_click_and_verify`
only understands two outcomes (pixels changed / didn't), so a ghost reads as
a successful placement — `_after_place` then tries to open an info panel and
set priority/upgrade on a unit that isn't really there yet. With phantom
placement off, an underfunded click should just no-op (pixels don't change),
which the existing retry logic (2.20/2.25 — re-arms the card, retries until
`execution.place_timeout_s`) already handles correctly with no extra
detection code needed. Confirmed off on the user's account as of this
session. If it can't stay off for some reason, ghost-detection would need
building — a template-match on the summon circle graphic (distinctive
shape, but a properly client-scaled capture is needed to size the template
correctly; a manual Windows Snip crop isn't reliable for this, see the
attempt in this same session).

Belt-and-suspenders even with phantom placement off: give placement steps a
`wait: cash >= <unit cost>` precondition where the cost is known. Not
required anymore, but still the cheapest way to avoid an underfunded click
in the first place.

---

## 8. Conventions

- Python 3.11/3.12, Windows only. Qt via PySide6.
- Code, comments and user-facing chat all in English (the user switched chat
  from Thai to English to cut token use — keep replies short too).
- Comments explain *why*, not *what*. Existing code follows this — match it.
- No new dependencies without a reason; `requirements.txt` is deliberately small.
