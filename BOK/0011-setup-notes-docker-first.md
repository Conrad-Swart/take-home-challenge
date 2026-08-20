# 0011. Setup notes lead with Docker, name Docker Desktop as a prerequisite explicitly

## Context
The submission form asks for "Setup notes: Anything we need to know to run
it." The reviewer is not on my machine, does not have my toolchain, and
should be able to boot the app cold.

Original README setup notes assume macOS + Homebrew + Python 3.13 framework
build. Not portable.

## Decision
Rewrite the setup notes at the top of README.md to be Docker-first. Include:
- A Prerequisites section that names Docker Desktop with the download URL,
  the ~1 GB disk requirement, the browser requirement, and the mic
  requirement.
- A "Run it" section with copy-paste commands that go from cold clone to
  transcribing in five steps.
- A separate "no Docker" developer path for reviewers who prefer that.
- A "Turning on the LLM cleanup" toggle so the default cold-boot path
  works with no Ollama, and the reviewer can turn cleanup on if they want.
- A Troubleshooting section for the three failure modes I already
  know about (port in use, mic denied, first-run model download).

## Why
- The reviewer explicitly cares about "onboarding for non-technical users"
  in the rubric. The setup notes are the onboarding.
- Naming Docker Desktop as a prerequisite by URL is not fancy but it is
  the difference between the reviewer succeeding and giving up.
- The Ollama toggle default (blank = skip) means a first-time reviewer
  does not have to install and run Ollama to see the app work.

## Cost accepted
More prose in the README. Worth it — one skipped setup step is enough to
lose the reviewer.
