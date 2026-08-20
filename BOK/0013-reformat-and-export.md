# 0013. Reformat + export as .txt / .md / .docx / .pdf

## Context
User asked for an expansion that pushes the app past "voice into text" toward
"voice into a usable document". Their example: "auto styled document ... word
doc or a pdf".

## Decision
Add two composable operations on any saved transcription:

1. **Reformat** into one of these styles via the LLM:
   - `raw` (pass-through, no LLM call)
   - `casual` (fix grammar, keep voice)
   - `meeting` (summary + key points + action items)
   - `email` (subject line, greeting, body, sign-off)
   - `bullets` (grouped bullet list)
   - `formal` (formal document paragraphs)

2. **Export** the current preview to `.txt`, `.md`, `.docx`, or `.pdf`.

Both live in a single modal: pick style -> preview updates -> pick format ->
download.

Backend endpoints:
- `POST /api/reformat` `{text, style}` -> `{text}`
- `POST /api/export` `{text, title, format}` -> file download

Library choices:
- `python-docx` for `.docx` (pure Python, no native deps).
- `fpdf2` for `.pdf` (pure Python, no native deps). Latin-1 fallback for
  characters outside the core font so it never crashes on curly quotes.

## Why
- Turns the app from a voice-to-text utility into a small productivity tool.
  One recording, six outputs, four file formats.
- Both libraries are pure Python. The Docker image and the local venv both
  work without installing GTK, Cairo, LibreOffice, or a headless browser.
- Editable preview in the modal means the user can tweak the reformatted
  text before downloading. LLM output is not final.

## Cost accepted
- Reformat depends on Ollama. If it is not reachable, we return the input
  unchanged (visible in the modal because the preview does not update).
  Not silent — the preview is still correct, just not reformatted.
- PDF font is Helvetica core (latin-1). Non-latin characters get replaced.
  Called out in the export module. Adding a Unicode TTF is a next-week
  change if the org needs non-English support.
