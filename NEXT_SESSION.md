# Handoff note — for Claude on the Windows PC

Written 2026-07-22 on the user's Mac. This is the machine handoff: the Mac
session did code review + capture analysis; the Windows machine is where the
game runs, so live verification happens THERE. Read `RELEASE_REVIEW.md` first —
it is the full findings list; this file is only "what's next".

## Where things stand

Committed on `main` (this repo):
- `2d360ef` — toggle-safe sell/priority panel actions (a bare `select()` on an
  already-open panel toggles it closed; everything now routes through
  `select_verified`). Placing a unit AUTO-SELECTS it — that model is stated in
  `core/unit_panel.py` and `core/actions/place.py` docstrings; the old HANDOFF
  2.20 "placing does not select" note is superseded.
- This commit — live-capture fixes:
  - `PRIORITY_TYPES` = real 9-option cycle (First → Last → Closest → Strongest
    → Boss → Weakest → Shielded → Fastest → None), confirmed from captures.
  - `cash_roi` = `[0.474, 0.807, 0.552, 0.840]` — old left edge clipped the
    leading digit at 5+ digits.
  - `vision/templates/defeat.png` — new, cut at 1280x720 scale from the loss
    capture.
  - `RELEASE_REVIEW.md` + this note.

## Known bugs still OPEN (all in RELEASE_REVIEW.md with fixes sketched)

Fix these in code before/while doing live testing, roughly in this order:

1. **1.7 HIGH — repeat_btn win/loss shift.** Loss result screen has no
   "Next Stage", so Repeat Stage sits at ~x0.277, not 0.375 → every loss
   stalls the loop. Fix: click the template-match LOCATION of
   `result_repeat.png` (vision/reward_screen.py already computes it via
   `vcap.match`, currently discards the position) instead of the fixed
   `repeat_btn` anchor. Needs a WIN result screenshot to confirm the win
   layout too — ask the user for one.
2. **1.1 HIGH — reward-screen stall.** `clear_reward_screens` treats "caption
   not showing YET" as "already cleared" when the match end was detected via
   the in-match banner. Poll for the caption to APPEAR (bounded, ~10-15s)
   before concluding there's nothing to clear. Note the loss capture shows
   losses skip the reward screens entirely — so on a loss the caption may
   legitimately never appear; result-screen detection should short-circuit the
   wait.
3. **1.2 MED — `select_verified` waits 150ms** before reading the panel; the
   place path waits `place_select_wait_ms` (400). Use the config value.
4. **1.3 MED — fresh clone can't start**: `load_config` should seed
   `config.yaml` from `config.example.yaml` in the non-frozen case. The
   Windows PC clone will hit exactly this on first run — fix it first thing.
5. **1.4/1.5 LOW** — shared `Capture` instance in main.py; clean error in
   `Capture.__init__` when opencv/mss missing.

## What the USER needs to do on the Windows PC (tell them, in order)

1. `git clone` / `git pull` this repo, run `run.bat` (expect the config.yaml
   issue above unless fixed first — workaround: copy `config.example.yaml` to
   `config.yaml`).
2. Install Tesseract-OCR binary (UB-Mannheim build), point
   `vision.tesseract_cmd` in config.yaml at it if not on PATH.
3. Lock in-game settings: Camera Classic, windowed, 100% display scaling,
   Shift Lock OFF, phantom/pre-placement OFF.
4. Attach → Test camera view → capture reference → Calibrate tab: use
   "Test read" on cash_roi (new box needs verifying live, esp. that the coin
   icon stays out) and priority_label_roi.
5. Provide the two missing captures: WIN result screen (for bug 1.7), and
   what Sell actually does (dialog or single click? `confirm_btn` is a guess).
6. Then: one supervised full loop (checklist in RELEASE_REVIEW.md §2 item 10),
   including at least one deliberate loss to exercise defeat.png + the 1.7 fix.

## Context that saves you re-deriving things

- The game: anime TD, ¥ currency, 1280x720 client assumed everywhere.
  User captures live at 1604x902 (16:9, same normalized layout) — RESIZE to
  1280x720 before cutting templates; matchTemplate is scale-sensitive.
- Panel model: placing auto-selects the unit (panel already open in
  `_after_place`). Never bare-click an open panel — toggle trap.
- Per-loop empty-panel baseline (`upgrade_level_roi` + `ctx.panel_empty`) is
  the authoritative "is a unit here" check; map-diff is the fallback.
- No keystrokes are ever sent to the game; everything is clicked.
  Priority is a CYCLE button read back via OCR.
- Losses: 0 rewards, no reward screens, straight to result screen.
- HANDOFF.md is the long history (97KB); RELEASE_REVIEW.md is current truth.
- User's chat style: keep replies short; caveman plugin may or may not be on
  over there — substance identical either way.

## Definition of done for the next session

`RELEASE_REVIEW.md` §3 blockers all checked: 4 bugs fixed, sell verified,
one clean supervised live loop with a win AND a loss handled end-to-end.
After that: minimal test suite, then `build.bat` smoke test → release.
