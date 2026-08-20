# 0012. One-command run: `python run.py`

## Context
User feedback: "for another user to run this can we have it so they can just
run without hassle and have it working?" The reviewer should not have to
create a venv, install requirements, edit .env, or read setup notes to get
the app running.

Options considered:
1. Two shell scripts (run.ps1 + run.sh) for Windows and Unix.
2. A single Python bootstrapper (run.py) that works everywhere Python does.
3. Keep Docker as the sole "just runs" path.

## Decision
Ship `web/run.py`. It:
- Detects the current platform for the venv Python path.
- Creates `.venv/` on first invocation with the stdlib `venv` module.
- Installs `requirements.txt` on first invocation (idempotent via a marker
  file so subsequent runs skip the install).
- Ensures `data/` exists.
- Opens the browser at http://localhost:8000 after a 3 second delay so
  the server has time to bind.
- Runs uvicorn in the foreground, propagates Ctrl+C cleanly.

Also modified `app.py` to auto-generate and persist a secret key into
`data/.secret_key` on first launch when SECRET_KEY env var is not set.
Sessions survive restarts without the reviewer editing .env.

## Why
- One command, one language (Python), one path across all platforms.
- No `.env` step. No manual pip install. No manual venv activation.
- Cross-platform without maintaining two shell dialects.
- Docker still works as an alternative for reviewers who prefer it.

## Cost accepted
- Reviewer needs Python 3.10+ and ffmpeg on PATH. Both named in README
  Prerequisites with install commands per OS.
- The auto-generated `.secret_key` in `data/` is fine for a dev/demo and
  not suitable for a shared deployment (each replica would generate its
  own key). Real deployments should set SECRET_KEY via env var; the .env
  path still works and takes precedence.
