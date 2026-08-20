# 0006. Cleanup pass hits Ollama, and is optional

## Context
Original runs Qwen2.5-1.5B via mlx_lm to clean up long recordings. On
Windows/Linux the natural analogue is calling Ollama. Global rules point at
qwen3.5:cloud on the ai@fullstack.co.za Ollama account.

## Decision
- Call Ollama /api/chat when OLLAMA_URL env var is set.
- If OLLAMA_URL is empty or the call fails, return the raw Whisper text.
- Mirror the original's duration threshold: only clean recordings longer
  than CLEANUP_THRESHOLD_S (default 15s).
- Mirror the original's crude sanity check: if the cleaned text is more than
  2x the length of the raw text, discard it and return raw.

## Why
- A fresh clone with no Ollama running still boots and transcribes. That
  matters for the reviewer: docker compose up, sign in, hold the button, get
  text back.
- Ollama is what the org already runs, so pointing at it is one env var away
  from working in a real deployment.
- Keeping the duration threshold and the 2x guard means the behaviour is
  recognisable to someone who read the original.

## Cost accepted
Cleanup quality depends on the Ollama model. qwen3.5:cloud is likely fine
for prose; jargon-heavy or list-heavy dictation would want the same few-shot
example the original had. Deliberately dropped that here for simplicity.
