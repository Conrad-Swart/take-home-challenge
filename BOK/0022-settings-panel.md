# 0022. Settings panel: hotkey, talk mode, theme (per-user)

## Context
User asked for a config surface so they can:
- Choose which key holds/toggles the mic.
- Switch between hold-to-talk and press-to-toggle.
Plus any other small preferences that fit naturally.

## Decision
Added a gear icon in the header (visible only when signed in) that opens
a Settings modal. Settings live on the User row so they persist across
devices when the same account signs in:

- `User.hotkey` — a `KeyboardEvent.code` (e.g. "Space", "KeyA"). Captured
  by clicking a button and pressing any key. Displayed via a small
  `prettyKey()` mapping so "KeyA" shows as "A".
- `User.talk_mode` — "hold" (default) or "toggle". A segmented control
  swaps between them. Changing this dynamically rewires the record
  button and the keyboard listener.
- `User.theme` — "system" (default), "light", or "dark". Applied by
  toggling a `data-theme` attribute on `<html>`. The CSS uses
  `@media (prefers-color-scheme: dark)` guarded by
  `:not([data-theme="light"])` so the media query is the fallback, not
  the override.

Rejected during scoping:
- **Auto-copy on transcribe** — user said no, the copy button on each
  history row is enough. Removed from the model, endpoint, and UI in
  the same pass.

Backend:
- `PrefsUpdate` accepts all four settings as optional fields; partial
  updates are the norm (one field per user interaction).
- `_migrate_add_columns` handles new columns for existing databases.

## Why
- Persist to the DB, not localStorage, so the settings follow the user
  across machines and browsers.
- One PATCH endpoint for all prefs keeps the surface tight — no
  per-setting route.
- Capture via `KeyboardEvent.code` (not `key`) so the binding survives
  layout changes (a French AZERTY user pressing "A" gets `KeyQ`
  correctly; the physical key wins, not the label).
- `stopImmediatePropagation()` on the capture-phase keydown prevents the
  recording listener from also firing on the captured keypress.

## Cost accepted
- Rebinding the record button uses `cloneNode(true)` + `replaceChild`.
  Cheap, unambiguous, but slightly heavy-handed compared to keeping
  handlers and gating on mode. The clone approach avoids any risk of
  stale listeners.
- The Meta (Cmd/Windows) key is deliberately unavailable as a hotkey
  because Cmd+X shortcuts belong to the browser and OS.
