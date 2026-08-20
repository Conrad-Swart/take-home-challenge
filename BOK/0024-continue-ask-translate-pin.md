# 0024. Four expansions: continue, ask, translate, pin

## Context
Once the reformat + export flow was stable, the user asked to push the
app further with:

- **Continue** — extend an existing note with more audio.
- **Ask your notes** — small RAG-lite Q&A over the user's own notes.
- **Translation** — translate the preview into another language.
- **Some form of organisation** — my call, I picked pinning.

Plus the "missing from original" items:

- **Auto-bullet list post-processing** (`dictate.py:184-207`), which
  detects "Number one, Number two, Number three" style dictation and
  converts each line to a `- ` bullet even without the LLM.
- **Silence gate** — the original used an RMS threshold to skip
  transcription of near-silence. We already have this effectively via
  `faster-whisper`'s `vad_filter=True` (Voice Activity Detection): if
  the whole clip is silence the transcript comes back empty and the
  transcribe endpoint returns 400 "no speech detected".

## Decision

### Continue recording
- `POST /api/history/{id}/continue` accepts the same
  `audio + duration_s` payload as `/api/transcribe`.
- Transcribes, optionally cleans up (respects the user's cleanup level),
  applies bullet-list post-processing, then appends to the existing
  `entry.text` with a blank line separator. Also bumps `duration_s`.
- Title stays the same. The note keeps its identity.
- Frontend: "Continue" button on every history row sets a
  `continueTargetId`. A pill under the header shows
  "Continuing: <title>". Next hold+release hits the continue endpoint
  instead of transcribe. Cancel via the pill's `x`.

### Ask your notes
- `POST /api/ask` takes `{query}`, pulls the user's last 30 notes,
  concatenates them into a bounded ~4000-char context, sends to the
  LLM with a strict "answer only from these notes" system prompt.
- Frontend: a rounded input above the history section ("Ask your
  notes:") with an inline "Ask" button and an answer card that expands
  underneath the input with a subtle slide-in.

### Translation
- `POST /api/translate` `{text, language}` where language is an ISO
  639-1 short code from the SUPPORTED_LANGUAGES map in audio.py
  (English, Afrikaans, Zulu, Xhosa, Southern Sotho, Spanish, French,
  German, Portuguese, Italian, Dutch, Chinese Simplified, Japanese,
  Arabic).
- `GET /api/languages` returns the picker options so the frontend does
  not need to hardcode them.
- Frontend: a language dropdown lives inside the export modal under
  the style chips. Picking a language translates the current preview
  (whatever style was applied) in place. `.txt / .md / .docx / .pdf`
  export then downloads the translated version.

### Pinning (the organisation)
- `Transcription.pinned` boolean, migrated in.
- Star button per row toggles pinned. Pinned rows sort first (via
  `order_by(pinned.desc(), created_at.desc())`) and render under a
  small "Pinned" header, with a subtle gold left-border and a very soft
  gradient background so they read as elevated without shouting.
- Rejected: tags and folders. Both add real UI surface (input for
  adding tags, filter chips at the top, tag-management flows) that
  would crowd the current sleek layout. Pinning is one click, one
  visual, and covers 80% of "which of my notes matter most today".

### Bullet-list post-processing
- Ported `_fix_unbulleted_list` from the original as `fix_unbulleted_list`.
- Applied in both `transcribe` and `continue` after the cleanup pass.

## Why
- All four features share the LLM plumbing that was already in place;
  none require new services or dependencies.
- Continue is real everyday utility: half-formed thoughts get finished
  without starting a fresh note.
- Ask closes the loop from "recorded lots of notes" to "actually
  finding what you said" without adding embeddings or a vector store
  (deferred until note volume justifies it).
- Translation demonstrates the app is not English-only in a
  multilingual org, at zero extra runtime cost.
- Pinning is the simplest organisation primitive that still adds
  visible structure. If the org actually needs tags or folders, they
  fit on top of this without a rewrite.

## Cost accepted
- Ask is bounded-context, not vector search. Older notes drop out of
  the answer if the user has more than roughly 30. Fine for now; a
  next-two-weeks item if volume matters.
- Translation quality depends on the small local model. English -> the
  five closer European languages tends to be good; less common
  languages (Xhosa, Zulu) benefit from the larger cloud model —
  swappable via `OLLAMA_MODEL`.
- Continue rewrites the note in place. No undo. Acceptable given the
  inline edit already exists as the corrective flow.
