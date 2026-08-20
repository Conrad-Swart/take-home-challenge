# 0025. Repo tidy pass

## Context
After the burst of feature work (settings, hallucination controls,
continue, ask, translate, pin), the code had accumulated:

- A stray `import re as _re` mid-file in audio.py.
- An unused `const recBtn` in app.js after `applyTalkMode()` replaced
  the button node.
- Section headers in app.py that no longer reflected the routes below
  them.
- `_serialise` defined below its first caller.
- Duplicated tempfile + transcribe boilerplate between `/api/transcribe`
  and `/api/history/{id}/continue`.
- A stale `qwen3.5:cloud` default for `OLLAMA_MODEL` in audio.py that
  did not match the new `qwen2.5:1.5b` default the app actually ships
  with.
- `.env.example` still described a subset of the current settings.

Also: the port-clear routine in `run.py` was matching by command-line
substring, which missed a real leftover where two Python processes
(system Python + venv Python) were both running from our repo.

## Decision
One tidy pass with no behaviour changes except:

1. `run.py` `clear_stale_server`: match by process name (`python` /
   `pythonw` / `uvicorn`) rather than command-line substring, and
   compare against both `os.getpid()` and `os.getppid()` so the current
   Python and its exec parent are always excluded from the kill list.
2. `audio.py`: consolidated imports at top, added `_strip_preamble()`
   helper to remove the duplicated preamble-stripping loop in
   `reformat_text` and `translate_text`, updated the module docstring
   to reflect all five LLM use cases, set the default `OLLAMA_MODEL`
   to `qwen2.5:1.5b` to match `.env.example`.
3. `app.py`: reorganised into clearly-named sections in the order a
   user hits them (auth -> prefs -> transcribe -> history -> reformat/
   translate/ask -> export -> static). Moved `_serialise` and helpers
   above their first callers. Pulled the tempfile + transcribe pipeline
   into `_save_upload_to_tempfile` and `_transcribe_and_finalise` so
   the transcribe and continue endpoints stop repeating themselves.
4. `.env.example`: expanded to cover every documented setting
   (SECRET_KEY, WHISPER_MODEL, OLLAMA_URL, OLLAMA_MODEL,
   CLEANUP_THRESHOLD_S, DATA_DIR, DB_URL), with a comment for each.
5. `app.js`: removed the unused top-level `const recBtn` and added a
   one-line comment explaining why the button is looked up freshly in
   `startRec`/`stopRec` (because `applyTalkMode` clones the node).
6. `WRITEUP.md` "What I did" section now lists the features that
   landed after the initial pass (auto-title, reformat + export,
   translate, ask, continue, pin, settings, waveform).

## Why
- Repo tidiness is not free: reviewers notice dead code, stale
  comments, and duplicated blocks and pattern-match "this candidate
  did not go back and finish".
- Kill-by-process-name is safer AND stricter: we only kill `python`
  processes, and we never touch a non-Python program on the same port.

## Cost accepted
- Refactoring `_transcribe_and_finalise` means both endpoints now share
  a single failure path. If a change breaks it, both endpoints break.
  Acceptable given the duplication was worse.
