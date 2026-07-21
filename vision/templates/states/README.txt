Game-state detection templates (see vision/game_state.py).

Drop tightly-cropped PNGs here, each a UI element that appears ONLY in that
state, so the macro can tell lobby / loading / in-stage / result apart:

  in_stage.png - the top "health / wave / enemies / time" HUD bar. Most useful.
  lobby.png    - a lobby-only element (Play button, or the Store/Units menu).
  loading.png  - the loading screen logo/spinner (optional; a near-black frame
                 is already treated as loading without this).
  result.png   - the victory/defeat banner (win-vs-loss split lives in the
                 parent folder's victory.png / defeat.png).

How to make them:
  1. Get into the state in-game.
  2. Click the dashboard "Screenshot" button (saves a full 1280x720 frame to
     the screenshots/ folder).
  3. Crop tightly to the distinctive element in any image editor, save here
     with the exact name above.

Then set execution.wait_for_in_stage: true in config.yaml to make runs wait
for the in-stage HUD before acting. With no templates here, detection is a
safe no-op and runs proceed exactly as before.
