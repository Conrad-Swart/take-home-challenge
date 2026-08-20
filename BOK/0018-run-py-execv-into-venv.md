# 0018. run.py re-execs into the venv Python and runs uvicorn in-process

## Context
First attempt at `run.py` used `subprocess.run(...)` to spawn uvicorn. On
Windows this had a nasty side effect: Ctrl+C in the terminal did not
reliably stop the server, because Python caught KeyboardInterrupt in
subprocess.run before the child process shut down.

User hit this and had to close the terminal window to kill it. Not okay.

## Decision
Rewrite `run.py` so, after ensuring the venv and deps exist, it re-execs
itself using the venv's Python via `os.execv`. Once running under the
venv, it imports uvicorn directly and calls `uvicorn.run("app:app", ...)`
in the same process. No subprocess in between.

## Why
- With uvicorn in-process, Ctrl+C hits uvicorn's own SIGINT handler
  directly, which unbinds the socket and exits cleanly.
- No handshake needed between wrapper Python and child Python.
- `os.execv` replaces the process image, so on POSIX there is only one
  Python left running. On Windows the behaviour is similar enough that
  Ctrl+C reaches the right process.

## Cost accepted
- The re-exec adds a small startup delay (a few hundred ms). Not visible.
- If `os.execv` fails on some odd platform, the app will not start; the
  outer `try/except KeyboardInterrupt` at least keeps the traceback clean.
