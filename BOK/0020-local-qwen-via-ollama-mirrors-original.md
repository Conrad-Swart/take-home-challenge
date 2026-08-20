# 0020. LLM path mirrors the original: local Qwen2.5 1.5B via Ollama

## Context
Testing the reformat / auto-title flow, the internal Ollama server at
192.168.0.98:11434 was unreachable from the dev machine (connection
timeout). Reformat silently fell back to returning the input unchanged.
User asked how the original macOS app handled this and requested the
"same way".

## Decision
Point `OLLAMA_URL` at `http://localhost:11434` and use `qwen2.5:1.5b`
pulled locally via `ollama pull qwen2.5:1.5b`. This directly mirrors the
original app, which used `mlx-community/Qwen2.5-1.5B-Instruct-4bit`
loaded from Hugging Face (`dictate.py:29, 126-128`).

Both approaches share the important properties:
- Same model family and size (Qwen2.5 1.5B).
- 100% local. No signin, no cloud, no external API.
- One-time download on first use (~900 MB via Ollama, ~1 GB via MLX).
- Runs offline forever after that.

Also added a `changed` flag to the reformat endpoint response so the UI
can tell the user when the LLM was unreachable and the text came back
unchanged. Previously the fallback was silent.

## Why
- Same on-device / on-machine privacy stance the original app committed
  to.
- No dependency on the internal Ollama server being reachable, so the
  reviewer can run the app from any network.
- Ollama exposes the same HTTP `/api/chat` interface regardless of which
  local model is loaded, so the app code did not need to change.

## Cost accepted
- Qwen2.5 1.5B on CPU is slower than the Apple Neural Engine path from
  the original (roughly 2-4 seconds per short reformat on a modern
  laptop). Acceptable for a demo; the "next two weeks" list has GPU as
  the natural upgrade.
- Different LLM output than qwen3.5:cloud would give. Not a real issue —
  the 1.5B model is deliberately the same class as the original, so
  outputs are directly comparable.
