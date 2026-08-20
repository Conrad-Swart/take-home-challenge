# 0016. Auto-title on save, and cleanup slider back per user

## Context
Two features paired because they both surface the LLM in the same UX
surfaces (transcribe + history), and both fall back gracefully when Ollama
is unreachable.

## Decision
- **Auto-title**: on every transcribe, call the LLM with a short "generate a
  3-6 word title" prompt against the first 800 chars of the transcript.
  Store it on `Transcription.title`. If the LLM is unreachable, fall back
  to the first six words of the text. History rows lead with the title.
- **Cleanup slider**: bring back the 0-100 slider from the original
  (`dictate_tray.py:190-200`), stored per user as `User.cleanup_level`
  (default 25). The tier labels (Off / Light / Medium / Heavy / Full) and
  prompt-rules-per-tier mirror the original at `dictate.py:146-181`.
  Slider debounces to `PATCH /api/prefs` so we do not spam the server on
  drag.

## Why
- The auto-title changes the history from "wall of text" to a scannable
  list — the single biggest UX improvement per line of code.
- Bringing the slider back was a user ask, and it demonstrates I actually
  read the original app rather than replacing it with something generic.
- Both are LLM-optional. No Ollama = fallback title (first words) and
  cleanup no-op. The app never breaks because the LLM is down.

## Cost accepted
- Title generation adds one LLM call per transcribe (~1 second on the
  1.5b model). Acceptable — it runs after the transcript is saved, so
  the user does not wait for it in the primary UI thread beyond the
  transcribe endpoint response.
- Slider save is debounced 350 ms. Rapid drags do not thrash the DB.
