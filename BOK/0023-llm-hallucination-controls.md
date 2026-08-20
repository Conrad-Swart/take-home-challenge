# 0023. Reformat prompts, seed, and length caps to control the 1.5B model

## Context
The Qwen2.5 1.5B model returned wildly different outputs across identical
reformat clicks. One "email" reformat of a short introduction turned into
a fake job application at a fake company. "Formal" oscillated between a
tight paragraph and a two-page essay.

## Decision
Three levers combined, not one:

1. **Determinism.** The Ollama call now uses `temperature=0.1`, `seed=42`,
   `top_p=0.9`, and `repeat_penalty=1.15`. Same input, same output. This
   alone stops the "different every click" behaviour.

2. **Sharper prompts.** Each style prompt now:
   - Starts with an explicit `Task:` line.
   - Gives a concrete `Format:` template (e.g. `Subject: <short subject>`).
   - Ends with a shared `STRICT RULES:` block that explicitly forbids
     inventing facts, names, companies, job titles, dates, or numbers.
   - The user content is wrapped in `INPUT:` so the system prompt can
     refer to it unambiguously.

3. **Per-style length caps.** A dict maps style to a length-cap function
   of the input length. If the LLM output blows past that cap, we drop
   the reformat and return the original text. Caps roughly:
   - casual: `2*n + 60`
   - formal: `n + 120`
   - bullets: `2*n + 80`
   - email: `n + 250` (accommodates subject/greeting/signoff overhead)
   - meeting: `3*n + 200` (accommodates summary + bullets)

Also: strip common preamble leads ("Sure,", "Here is", "Output:")
because the small model occasionally emits them despite the rule.

## Why
- The failure mode was clearly hallucination + variance, and the fix
  needs both a leash (prompts/rules) and a fence (length caps). One
  without the other still lets bad output through.
- A seed makes the reformat feel like a settled formatting tool rather
  than a slot machine. Same click, same result.
- Length caps are the last line of defence. Even if the model ignores
  every rule, the user does not see the two-page essay — they see the
  original text and can try a different style.

## Cost accepted
- Determinism means the model gives one answer per input. If that answer
  is bad, clicking again cannot improve it. Mitigated by the "raw" chip:
  the user can always fall back and edit by hand.
- Length caps occasionally reject legitimate longer outputs on very
  short inputs. Trade the false-reject against the wall-of-hallucination
  we were seeing.
