# 0014. UI overhaul with CSS tokens and auto dark mode

## Context
The initial CSS was functional but flat: single palette, no design system,
no accommodation for dark mode. User asked to invest heavily in "look good"
and keep it "sleek, simple, basic, looking good and functional".

## Decision
Rewrite `style.css` around a design token system:
- CSS custom properties at `:root` for every colour, radius, shadow, and font.
- `@media (prefers-color-scheme: dark)` block redefines the same tokens for
  dark mode. All components consume the tokens, not hardcoded values.
- One accent colour (Clever Profits navy `#040B4D`) used sparingly.
- Consistent radii (12 / 8 / 6px) and a small elevation scale (`--shadow`,
  `--shadow-lg`).
- Card component pattern: `.card` gives every surface the same
  border+radius+shadow. Applied to auth card, record card, prefs, history
  rows, and the modal.
- System font stack, no web fonts. Zero external assets on the page.

Also added:
- Media queries at 640px and 400px for responsive layout.
- Global `[hidden] { display: none !important; }` so `hidden` attribute
  survives `display: flex` on the same element.

## Why
- Tokens make dark mode a one-block change instead of a hunt through
  fifteen selectors.
- No web fonts means no network dependency and no FOUC.
- The card pattern gives every surface visual consistency without a design
  system framework.

## Cost accepted
- The token scale is small (one accent, one danger, one info, one good).
  Real design systems have more nuance. Fine for a demo.
