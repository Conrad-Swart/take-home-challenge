# 0007. Vanilla HTML + JS + CSS, no framework

## Context
The frontend is one page: sign in, big record button, transcription output,
history list. Options considered:
- React + Vite
- SvelteKit
- Plain HTML/JS/CSS

## Decision
Plain HTML/JS/CSS. One index.html, one app.js, one style.css.

## Why
- A framework adds a build step, a bundler config, and dozens of files a
  reviewer has to skim to answer "is this candidate any good at frontend".
- The whole UI is under 200 lines of JS. React would triple that just to
  set up state management for something this small.
- The reviewer can open static/app.js and read it top to bottom in two
  minutes.

## Cost accepted
No component reuse, no client-side routing. Not a scaling concern until the
UI grows to more than one screen — at which point React or Svelte is the
right call.
