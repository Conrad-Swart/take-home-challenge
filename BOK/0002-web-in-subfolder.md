# 0002. Put the web rewrite in web/, leave the original files alone

## Context
The original repo has dictate.py, dictate_tray.py, install.sh, README.md,
TASK.md, WRITEUP.md, assets/, and the Clever Dictate.app bundle at the root.

## Decision
Create web/ at the repo root and put all rewrite code there. Original files
stay untouched.

## Why
- The findings in WRITEUP section 2 reference specific line numbers in the
  original code. Deleting those files would make the review harder for the
  assessor.
- Keeps the two implementations legible side by side. Reviewer can see what
  changed by structure, not by diff.
- Root README gets a short "web rewrite" section pointing to web/, with the
  macOS instructions kept below as reference.
