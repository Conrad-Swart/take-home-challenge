# 0015. Live waveform via Web Audio, drawn on canvas

## Context
User asked for "one exciting thing" that made the app feel alive without
being risky. Live audio feedback while recording matches that: it confirms
the mic is working, gives the recording a sense of scale, and is a common
UX pattern in voice-note apps (WhatsApp, Voice Memos, Slack huddles).

## Decision
- `getUserMedia()` yields a `MediaStream`.
- Pipe the stream through an `AudioContext.createMediaStreamSource()` into
  an `AnalyserNode`.
- `analyser.fftSize = 128`, then `getByteFrequencyData()` at every
  `requestAnimationFrame`.
- Draw N vertical bars (16 to 40 depending on canvas width) on a `<canvas>`
  in the record card, coloured with the current `--accent` token.
- Bar count is width-derived so the visual density stays right as the page
  resizes.
- Canvas bitmap size tracks `devicePixelRatio` so it stays sharp on Retina.

## Why
- Same MediaStream that MediaRecorder is already recording — no extra mic
  permission prompt.
- Frequency data gives a "bouncy bars" feel; time-domain data gives a
  waveform-line feel. Bars read better for short bursts.
- Web Audio is universally supported on modern browsers; no library.

## Cost accepted
- `roundRect` on Canvas 2D is Chrome 99+, Safari 16+, Firefox 113+. Older
  browsers would fall back to sharp corners — non-blocking.
- Drawing runs every RAF only while recording. Idle state draws a static
  flat line once.
