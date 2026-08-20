# 0005. faster-whisper (CPU int8) as the transcription engine

## Context
Original uses mlx_whisper which is Apple Silicon only. Alternatives on
Windows/Linux:
- openai-whisper (PyTorch, works but slower)
- faster-whisper (CTranslate2 backend, 4x faster on CPU, half the memory)
- OpenAI cloud Whisper API (fastest, but sends audio off-machine)

## Decision
faster-whisper on CPU with compute_type="int8", model "small.en".

## Why
- Runs on any developer machine without a GPU. A reviewer with no NVIDIA
  hardware still gets working transcription.
- Fully local — audio never leaves the machine, mirroring the original app's
  privacy stance.
- small.en is the same size class as the original's whisper-small.en-mlx, so
  transcription quality is comparable.
- Container works without extra runtime deps; ffmpeg is installed in the
  Dockerfile because faster-whisper decodes through it for non-WAV inputs
  (the browser uploads webm/opus).

## Cost accepted
CPU int8 is noticeably slower than the original's Apple Neural Engine path
for long clips. Fine for demo, worth revisiting with a GPU base image
(nvidia/cuda) if latency becomes user-visible.
