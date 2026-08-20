# 0017. Inline edit for title and transcription text

## Context
User wanted the app to feel usable day to day. Whisper sometimes gets a
word wrong; making the user re-record to fix a typo is bad UX.

## Decision
- Both `.row-title` and `.row-text` toggle `contenteditable="true"` on
  click. Blur triggers a `PATCH /api/history/{id}` with just the field
  that changed.
- `Enter` on a title commits and blurs (matches how spreadsheet-like
  inputs feel). `Escape` reverts to the pre-edit value.
- Visual cue: dashed underline on the title, and an outlined box on the
  text, when editing. Removed on blur.

## Why
- Zero-friction fix path. One click, edit, click away.
- No separate "edit mode" screen. The history row is the editor.
- Server accepts partial updates via a pydantic model with optional
  fields, so the same endpoint handles title-only, text-only, or both.

## Cost accepted
- No optimistic locking. If two tabs edit the same entry, last write
  wins. Acceptable for a single-user-at-a-time app; would want
  `updated_at` and an "If-Unmodified-Since" flow for a team-wide MVP.
- Plain text only; markdown/rich text intentionally not supported. Keeps
  the model and UI simple.
