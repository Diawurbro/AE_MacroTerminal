Drop cropped screenshots here to enable template-match win/loss detection:

  victory.png   - the victory/result banner, cropped tight
  defeat.png    - the defeat/result banner, cropped tight
  lobby.png     - a lobby/menu frame (reserved, not read yet)

Until victory.png and defeat.png both exist, result_detector.py falls back
to a green-vs-red color ratio check on StageProfile.ui_anchors["result_roi"].

Already supplied:

  reward_close.png - the "(Click anywhere to close)" caption on the
                     post-match item screens, WITHOUT the trailing [N/M]
                     counter (that part changes between screens, so
                     including it would break the match).
                     Cut from a real 1280x720 capture. Used by
                     vision/reward_screen.py to click through those
                     screens; delete it and looping will stall on them.
