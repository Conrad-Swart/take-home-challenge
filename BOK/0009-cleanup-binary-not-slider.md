# 0009. Cleanup is a binary (raw vs cleaned) on the duration threshold, not a 0-100 slider

## Context
Original app has a 0-100 slider for cleanup aggressiveness with five tiers:
Raw, Light, Medium, Heavy, Full (dictate_tray.py:190-200). The correction
prompt in the original is assembled from rules that turn on above 25, 50, 75
(dictate.py:151-181).

## Decision
Web app has no slider. Cleanup runs at a single, medium setting (equivalent
to the original's "Light-plus-punctuation" tier) when the recording exceeds
CLEANUP_THRESHOLD_S. Otherwise the text is returned raw.

## Why
- User asked for "as basic as possible". The slider is a real product
  surface but not the core loop.
- The duration threshold is the primary control the original app relies
  on for the raw-vs-cleaned decision (dictate.py:340). Keeping that
  preserves the observable behaviour a real user would notice.
- Bringing the slider back is a one-form-field change plus a per-user
  setting row in the DB. Deferred rather than dropped.

## Cost accepted
Power users lose per-recording control over cleanup aggressiveness.
WRITEUP section 5 names this as a trade-off; section 3 puts it on the
next-two-weeks list.
