# 0010. Docker Compose is the primary "how to run this" story

## Context
Reviewer will clone the repo cold and needs to get the app running with
minimal ceremony. Options:
- pip install locally + uvicorn (needs Python 3.12, may hit binary wheels
  for CTranslate2/faster-whisper on some platforms)
- Docker Compose
- Both

## Decision
Docker Compose is the documented path. Local pip install is noted as an
alternative for developers who prefer it, not documented step-by-step.

## Why
- One command (docker compose up --build), one port (8000), one URL. That
  is exactly the "onboarding for non-technical users" line in the rubric.
- The Dockerfile bakes in ffmpeg and the correct Python version, so the
  reviewer does not spend the first ten minutes on their own environment.
- Data lives in ./data (mounted), so the SQLite file survives container
  rebuilds.

## Cost accepted
The first build is slow because it downloads the faster-whisper wheel and
its ctranslate2 dependency (100+ MB), and Whisper downloads the small.en
model on the first transcription request (~500 MB into the container's
Hugging Face cache — not persisted across rebuilds unless we add a
volume). Both are called out as first-run behaviour in the README.
