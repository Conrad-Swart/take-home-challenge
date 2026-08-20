# 0021. run.py clears its own stale server before starting

## Context
Windows Ctrl+C behaviour + occasional orphan Python processes meant that
restarting the app sometimes failed with:

    [WinError 10048] only one usage of each socket address ...

The first time this happened I killed the leftover PID by hand. The user
correctly pointed out that fixing the current run is not enough — the
next Ctrl+C could leave things in the same state.

## Decision
`run.py` now runs a `clear_stale_server(PORT)` step at startup, after the
venv/deps checks and after the exec-into-venv re-launch. It:

1. Checks whether the port is in use.
2. If yes, on Windows, uses `Get-NetTCPConnection` to find the PID holding
   the port, and `Get-CimInstance Win32_Process` to inspect that PID's
   command line. Only kills the PID if the command line matches
   `uvicorn.*app:app` or `run\.py`. This is the safety guard — never kill
   an unrelated user program that happens to be on port 8000.
3. On POSIX, uses `lsof` + `/proc/{pid}/cmdline` to do the same check.
4. If the port is still in use after cleanup, exits with a clear message
   telling the user which program to close.

## Why
- The failure mode should be a self-healing one-liner, not a
  troubleshooting call.
- The match check on command line prevents run.py from being a
  liability: if a reviewer has their own thing on port 8000, we do not
  murder it silently.

## Cost accepted
- The startup path now shells out to PowerShell / lsof. Adds ~200 ms on
  Windows when the port is contested; zero-cost when it is not (we skip
  the whole block if `port_in_use` returns false).
- Windows-only fallback path if PowerShell is missing (rare in modern
  Win10/11 installs); would show the "port still in use" message and
  exit, which is at least clear.
