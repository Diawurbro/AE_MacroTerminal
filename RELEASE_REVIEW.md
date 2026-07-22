# Release Review — Roblox TD Macro

Date: 2026-07-22. Full read of `core/`, `vision/`, `data/`, `main.py`, UI skimmed
(`ui/stage_editor.py` structure only), HANDOFF.md cross-checked. Goal: what must
happen before this is release-ready.

**Update (same day):** live captures received (`Downloads/eeee` — cash 4/5/6
digit, loss screen, full priority cycle). Findings folded in below; section 1.7
is a new bug those captures exposed, and several "need from you" items are now
resolved. Applied fixes: `PRIORITY_TYPES` corrected, `cash_roi` corrected,
`defeat.png` template installed (see section 5).

---

## 1. Bugs found in this review

Ordered by severity. None of these are fixed yet — they are findings.

### 1.1 HIGH — Banner-classified match can stall the whole loop
`core/match_flow.py:71` (`clear_reward_screens`)

`wait_for_match_end` can return `'win'`/`'loss'` from the **in-match banner**
before the reward screens have appeared. `clear_reward_screens` then checks the
caption **once**, sees it not showing (because the screens aren't up *yet*),
and returns `True` ("cleared") after 0 clicks. `read_result_screen` then waits
up to 60 s for the result screen — but the reward screens appear behind that
wait and nothing ever clicks through them. Result screen never comes, Repeat is
never clicked, and the next loop aborts on the camera check.

The code conflates "caption not showing yet" with "caption already gone".

**Fix:** after a banner-based match end, poll for the caption to *appear* for a
bounded window (e.g. 10–15 s) before concluding there is nothing to clear. Only
skip straight through when the result screen itself is already detected.

(Currently masked in practice because `wait_for_match_end` usually returns via
the `"rewards"` path — but any run where the banner is read first hits this.)

### 1.2 MEDIUM — `select_verified` settle is 150 ms; the placement path uses 400 ms
`core/unit_panel.py:63` vs `core/actions/place.py` (`place_select_wait_ms`, default 400)

`_unit_is_there` waits `place_select_wait_ms` (400 ms) after a select click
before reading the panel. `select_verified` uses `select()`'s default 150 ms.
If the panel takes >150 ms to draw, `select_verified` returns `False` on a
perfectly good unit — and priority / upgrade / sell then **skip** with
"no unit at … the placement probably failed", even though it didn't.

**Fix:** `select_verified` should wait `ctx.execution("place_select_wait_ms", 400)`
before reading the panel, same as the placement check.

### 1.3 MEDIUM — Fresh clone cannot start: no `config.yaml` fallback in dev mode
`main.py:64` (`load_config`)

`config.yaml` is gitignored (correct — it holds the webhook URL). The frozen
build seeds it from the bundle, but the **source** path raises
`FileNotFoundError` when only `config.example.yaml` exists — so `run.bat` on a
fresh clone dies with the startup-error box. `build.bat` also does
`copy /y config.yaml` and fails the same way on a clean checkout.

**Fix:** in `load_config`, when `config.yaml` is missing, seed from
`config.example.yaml` (next to `main.py`) before raising.

### 1.4 LOW — `mss` handles leak on the GUI thread
`main.py:317, 342, 440` — every screenshot / OCR test / reference score creates
a new `vcap.Capture()`, each of which opens an `mss.mss()` instance that is
never closed. Harmless for one run, but a long session accumulates handles.

**Fix:** create one `Capture` lazily in `App` and reuse it (all three call
sites are on the GUI thread, so one shared instance is safe).

### 1.5 LOW — `Capture()` with opencv/mss missing fails late and cryptically
`vision/capture.py:15` — when `HAS_CV` is false, `_sct` is `None` and the
first `grab()` dies with `AttributeError: 'NoneType' object has no attribute
'grab'`. Callers mostly guard with `HAS_VISION`, but a clean
`raise RuntimeError("opencv/mss not installed")` in `__init__` would make any
missed guard diagnosable from the log.

### 1.6 NOTE — Full-frame template matching per poll in `wait_for_match_end`
`core/match_flow.py:50` grabs the whole client area and matches **two**
templates (victory + defeat) against the full frame every 400 ms poll for up to
15 minutes per match. Works, but it is the hottest loop in the program.
Matching inside `result_roi` (plus margin) instead of the full frame would cut
that cost ~10x and also reduce false-positive surface. Not a correctness bug —
a cheap performance win.

### 1.7 HIGH — `repeat_btn` position differs between win and loss; auto-repeat misses after a loss
`core/match_flow.py:121` (`click_repeat`), anchor `repeat_btn` in `data/profile.py`

`repeat_btn=[0.375, 0.790]` was measured on the WIN result screen, where
`Repeat Stage` is the MIDDLE of three buttons (Next Stage / Repeat / View Party).
The loss capture shows the DEFEAT result screen has no `Next Stage`, so
`Repeat Stage` shifts LEFT to ~x0.277 and `View Party` sits at ~0.474. A fixed
click at 0.375 lands in the gap between them — so **every loss stalls the loop**:
Repeat is never clicked, and the next iteration aborts on the camera check.

**Fix:** `click_repeat` already confirms the result screen via a template match
(`result_repeat.png`). Click the button at its **matched location** instead of
the fixed `repeat_btn` anchor, so it works whichever column Repeat is in.
(Needs a WIN result-screen capture to confirm the win layout and the template.)

### Reviewed and found sound
- Placement retry loop (check-before-place, re-arm every attempt) — correct.
- Per-loop empty-panel baseline (HANDOFF 2.30 fix) — correct.
- Toggle-safe select for priority/upgrade/sell (fixed this session, commit `2d360ef`).
- OCR reader split (`read_int` / `read_leading_int` / `read_fraction`) — correct.
- Hotkey thread, stats DB, webhook fire-and-forget — no issues found.
- `save_config_value` in-place patcher — handles colons in values, keeps comments.

---

## 2. What I need from YOU

Everything below needs the real game / your Windows machine — none of it can be
done from code. Use the dashboard **Screenshot** button (saves to
`screenshots/`) unless noted; a Windows Snip is *not* reliable for template
crops because the scale won't match the client capture.

### Screenshots / captures (in priority order)
1. ~~A loss.~~ **DONE** — `defeat.png` cut and installed. Note: the loss goes
   straight to the result screen (empty "Gained Rewards", no item screens), so
   the reward-clear step is a fast no-op on a loss. The result/Repeat flow IS
   the same shape as a win, except for the button-column shift (bug 1.7).
2. **WIN result screen** — still needed. Screenshot the victory result dialog
   (the one with Repeat Stage), so I can (a) confirm the 3-button win layout for
   bug 1.7 and (b) re-cut `victory.png`/`result_repeat.png` at the same scale as
   `defeat.png` if the existing ones were cut differently.
3. **Sell-confirm dialog.** Select a unit, press Sell, screenshot the dialog
   (don't confirm). `confirm_btn` at `[0.50, 0.72]` is still a pure guess —
   the sell action has never been verified end-to-end. NOTE: the unit panel's
   Sell button shows "Sell ¥200" with no visible confirm step in the captures —
   selling may be a SINGLE click with no dialog at all. Confirm which.
4. ~~Mid-run cash 4–5 digit.~~ **DONE** — `cash_roi` corrected (bug 1.3-cash).
5. ~~Priority cycle.~~ **DONE** — full 9-option set/order confirmed and
   `PRIORITY_TYPES` corrected.
6. **Game-state crops** (optional but recommended): in-stage HUD, lobby, and
   loading screen shots → crop to `vision/templates/states/{in_stage,lobby,loading}.png`.
   Enables the `wait_for_in_stage` gate so a loop never runs on a loading screen.
   (The captures already show a clean in-stage HUD — I can cut `in_stage.png`
   from any of them on request.)

### Machine checks
6. **Install Tesseract-OCR** (the binary, not just pip):
   https://github.com/UB-Mannheim/tesseract/wiki — then point
   `vision.tesseract_cmd` at it if not on PATH. Without it: no cash/wave waits,
   no priority verification.
7. **Hotkeys F9/F12** — verify they fire on your machine (they were claimed by
   another app in the dev sandbox). Rebind in `config.yaml → hotkeys` if taken.
8. **Windows display scaling = 100%** and Roblox **windowed** — then Attach and
   confirm the Readiness row reports exactly 1280x720.
9. **In-game settings locked:** Camera Mode = Classic, Shift Lock OFF,
   phantom/pre-placement OFF, graphics quality locked (changing any of these
   invalidates saved profiles).

### Live-run tests (after the above)
10. **One supervised full loop**, watching for: camera normalize + reference
    score (report the number), each placement landing, priority actually
    changing, upgrade level readout advancing, reward screens clearing, Repeat
    firing, loop 2 starting clean. Nothing has ever run against the live game
    from the environment this was built in.
11. **A 1–2 hour unattended session** afterwards — watch for drift, missed
    reads in `logs/`, and whether the loss-streak webhook fires correctly.

---

## 3. Not done yet — release checklist

### Blockers (fix before anyone else uses it)
- [x] Bug 1.1 (reward-screen stall after banner detection) — bounded wait for the
      caption/result screen to appear before concluding nothing to clear
      (`reward_appear_timeout_s`, default 12s)
- [x] Bug 1.2 (`select_verified` settle time) — now waits `place_select_wait_ms`
- [x] Bug 1.3 (config seeding on fresh clone) — `load_config`/`run.spec`/`build.bat`
      seed from `config.example.yaml`
- [x] Bug 1.7 (repeat_btn win/loss shift) — clicks the `result_repeat.png`
      template-match location, not the fixed anchor (needs WIN capture to confirm)
- [x] `defeat.png` captured + installed (scale-matched to 1280x720)
- [ ] Sell flow verified end-to-end (may be a single click, no dialog — confirm)
- [ ] At least one clean supervised live loop (item 10 above)

### Should-have
- [x] `PRIORITY_TYPES` confirmed against the real cycle and corrected
- [x] `cash_roi` corrected (was clipping the leading digit at 5+ digits)
- [ ] Frozen build (`build.bat`) actually built and smoke-tested on a clean
      machine — PyInstaller path handling (`app_dir`/`bundle_dir`,
      BASE-relative templates) is written but has never been exercised
- [ ] Bug 1.4 (shared Capture instance)
- [ ] Perf note 1.6 (ROI-scoped result matching)
- [ ] **No automated tests in the repo.** HANDOFF references stubbed-driver
      tests repeatedly, but there is no `tests/` directory — those tests died
      with the dev sandbox. The logic they covered (placement retry, priority
      cycle, OCR parsing) is exactly the logic that regresses silently.
      Recreating even a minimal suite is cheap insurance before release.

### Deliberately out of scope (tracked, not blocking)
- Session-level pacing (breaks every 45–90 min, daily cap) — anti-detection
  beyond per-click jitter is not implemented.
- Ghost/phantom-placement detection — unnecessary while the in-game setting
  stays OFF; would need a properly scaled summon-circle template if ever ON.
- DPI scaling other than 100% — untested, warned about at attach.
- Multi-resolution support — everything is measured at 1280x720 client.

---

## 5. Applied from the live captures (2026-07-22)

- **`data/profile.py` — `PRIORITY_TYPES`**: replaced the 7-entry guess (with a
  nonexistent `farthest`) with the real 9-option set confirmed from the cycle
  captures: `none, first, last, closest, strongest, boss, weakest, shielded,
  fastest`. The old list was also too short for the cycle bound to reach the
  last options.
- **`data/profile.py` — `cash_roi`**: `[0.492,0.805,0.547,0.842]` →
  `[0.474,0.807,0.552,0.840]`. The number is left-anchored right of the coin
  icon and grows rightward; the old left edge clipped the leading digit of any
  5+-digit value. Measured spans: "2,003" 0.483–0.528, "113,498" 0.480–0.536.
- **`vision/templates/defeat.png`**: cut from the loss capture, resized to the
  1280x720 runtime scale first (matchTemplate is scale-sensitive; existing
  templates are 1280x720-scale) and tightened to the "Defeat" ribbon. This
  upgrades loss detection from "inferred (no victory ribbon)" to a positive
  match, and enables template classification in `classify_frame` instead of the
  colour ratio (which never worked for this blue-victory game).

Not yet verified against a live run — `cash_roi` and the priority reads should
be checked with the Calibrate tab's "Test read" button once Tesseract is in.

## 4. Suggested order of work

1. I fix bugs 1.1–1.5 (small, local diffs).
2. You install Tesseract + lock the in-game settings + send captures 1–4.
3. I cut the templates from your captures, set `confirm_btn`, verify
   `PRIORITY_TYPES` / `cash_roi` against them.
4. Supervised live loop (item 10); fix whatever it exposes.
5. Minimal test suite over placement/priority/OCR parsing.
6. `build.bat` on your machine, smoke-test the frozen exe, then release.
