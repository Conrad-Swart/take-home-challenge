# 0008. Audio is deleted immediately after transcription

## Context
The upload endpoint receives an audio blob and needs to hand it to
faster-whisper, which takes a file path. Two options:
1. Save the blob to a persistent path, keep for debugging or replay.
2. Save to a temp file, transcribe, unlink in a finally.

## Decision
Option 2. Audio file is written to tempfile.NamedTemporaryFile, transcribed,
and unlinked in a finally block. Only the resulting text is persisted.

## Why
- The original app's stance is "nothing leaves the machine". The web
  version breaks the "on the machine" part by design (server-side), so
  keeping the audio-doesn't-persist part is the strongest privacy signal
  we can give.
- Storing audio would need retention policy, encryption at rest, and a
  delete-my-audio endpoint before it could be defensible. Not building
  any of that this cycle.
- WRITEUP section 4 ("Privacy and data") calls this out as the current
  posture and names encryption-at-rest as a gap.

## Cost accepted
No replay for debugging bad transcriptions. If we later need to tune
Whisper or the cleanup prompt against real data, we would opt-in per user
to keep audio, not opt-out.
