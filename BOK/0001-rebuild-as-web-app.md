# 0001. Rebuild as a small web app, not a Windows port

## Context
Original app is macOS Apple Silicon only (MLX + PyObjC). I am on Windows.
Two viable paths:
1. Reimplement natively for Windows (pystray + faster-whisper + hotkey daemon).
2. Rebuild as a small multi-user web app.

## Decision
Web app.

## Why
The brief explicitly rewards shared multi-user data, accounts, and team handoff.
A Windows port keeps the single-user, single-machine shape the original is
stuck in — it demonstrates porting ability but not product judgment. A web
rewrite hits the rubric lines a local rewrite misses (Team readiness,
Structure, Product thinking) and is what the brief is pointing at when it says
"a single local database file is one person's data on one laptop, not a shared
team system".

## Cost accepted
The web app cannot paste text at the OS cursor. That is the biggest UX
regression from the original and the price of shareable. Called out in
WRITEUP section 1 as a deliberate trade.
