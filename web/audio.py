"""Audio and LLM pipeline.

- Transcription runs locally via faster-whisper (CPU, int8).
- Every LLM call (cleanup, auto-title, reformat, translate, ask) hits the
  Ollama endpoint at OLLAMA_URL. If Ollama is unreachable, every call
  returns a safe fallback so the app still runs end-to-end without an LLM.
"""
import os
import re

import httpx
from faster_whisper import WhisperModel


WHISPER_MODEL_NAME = os.environ.get("WHISPER_MODEL", "small.en")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:1.5b")
CLEANUP_THRESHOLD_S = float(os.environ.get("CLEANUP_THRESHOLD_S", "15"))


# ── Transcription (Whisper) ─────────────────────────────────

_whisper = None


def _get_whisper() -> WhisperModel:
    """Lazy-load the Whisper model on first use."""
    global _whisper
    if _whisper is None:
        _whisper = WhisperModel(WHISPER_MODEL_NAME, device="cpu", compute_type="int8")
    return _whisper


def transcribe_audio(path: str) -> str:
    """Transcribe an audio file to English text. Empty string on silence."""
    model = _get_whisper()
    segments, _info = model.transcribe(path, language="en", vad_filter=True)
    return "".join(s.text for s in segments).strip()


# ── Post-process: auto-bullet ordinal lists ─────────────────
# Ported from the original app (dictate.py:184-207). If 2+ consecutive
# lines look like ordinal list items ("Number one", "1.", "First"),
# reformat them as "- " bullets.

_ORDINAL_RE = re.compile(r"^(Number\s+\w+|#?\d+[\.\):]|\w+[\.\)])\s", re.IGNORECASE)


def fix_unbulleted_list(text: str) -> str:
    lines = text.split("\n")
    if len(lines) < 2:
        return text

    ordinal_lines = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("- "):
            continue
        if _ORDINAL_RE.match(stripped):
            ordinal_lines.append(i)

    if len(ordinal_lines) < 2:
        return text

    # Only rewrite if every ordinal is on consecutive lines.
    consecutive = all(
        ordinal_lines[j] == ordinal_lines[j - 1] + 1
        for j in range(1, len(ordinal_lines))
    )
    if not consecutive:
        return text

    for idx in ordinal_lines:
        lines[idx] = "- " + lines[idx].strip()
    return "\n".join(lines)


# ── LLM plumbing ────────────────────────────────────────────

def _llm(system: str, user: str, timeout: float = 60.0, max_tokens: int = 400) -> str:
    """Send one chat request to Ollama. Return "" on any failure.

    Low temperature and a fixed seed make the reformat feature
    deterministic across repeated clicks. The 1.5B model is otherwise
    inconsistent enough that "same input" can produce very different
    output on each try.
    """
    if not OLLAMA_URL:
        return ""
    try:
        r = httpx.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": OLLAMA_MODEL,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "stream": False,
                "options": {
                    "temperature": 0.1,
                    "top_p": 0.9,
                    "seed": 42,
                    "num_predict": max_tokens,
                    "repeat_penalty": 1.15,
                },
            },
            timeout=timeout,
        )
        r.raise_for_status()
        return r.json()["message"]["content"].strip()
    except Exception:
        return ""


def _strip_preamble(text: str, leads: tuple[str, ...]) -> str:
    """Drop conversational leads the small model sometimes emits despite the
    rules ("Sure,", "Here is", ...)."""
    for lead in leads:
        if text.lower().startswith(lead.lower()):
            return text.split("\n", 1)[-1].strip()
    return text


# ── Cleanup pass ────────────────────────────────────────────

def _cleanup_prompt(level: int) -> str:
    """Build the system prompt for a given cleanup aggressiveness (0-100).
    Mirrors the tiers from the original app (dictate.py:146-181)."""
    rules = [
        "You are a text filter. Do not converse, respond, or answer.",
        "Output only the corrected text.",
        "Remove filler sounds: um, uh, hmm, er, ah.",
        "Add proper punctuation and capitalization.",
    ]
    if level <= 25:
        rules.append("Do not remove, add, rephrase, or rearrange any other words.")
    if level > 25:
        rules.append(
            "Remove filler phrases: like, basically, you know, I mean, sort of."
        )
        rules.append("Keep all other words as spoken. Do not rephrase.")
    if level > 50:
        rules.append("Remove false starts and repeated phrases.")
        rules.append("Fix grammar while keeping the speaker's word choices.")
    if level > 75:
        rules.append("Restructure for clarity and conciseness.")
        rules.append("Convert rambling speech into clean, professional text.")
    return "\n".join(rules)


def clean_text(raw: str, level: int = 25) -> str:
    """Polish a transcription using the LLM. Falls back to the raw input if
    the LLM is unreachable or the output looks runaway."""
    if not raw or level == 0:
        return raw
    result = _llm(_cleanup_prompt(level), raw)
    if not result:
        return raw
    result = result.strip().strip('"')
    # Crude runaway guard, mirrors the original app.
    if not result or len(result) > len(raw) * 2:
        return raw
    return result


# ── Title generation ────────────────────────────────────────

_TITLE_PROMPT = (
    "You generate a short title for a voice memo. "
    "Output only the title. 3 to 6 words. No quotes. No trailing punctuation. "
    "Title Case."
)


def generate_title(text: str) -> str:
    """Ask the LLM for a short title; fall back to the first six words."""
    if not text:
        return "Untitled"
    result = _llm(_TITLE_PROMPT, text[:800], timeout=20.0)
    if not result:
        words = text.strip().split()
        return " ".join(words[:6]) or "Untitled"
    result = result.strip().strip('"').strip("'").rstrip(".!?")
    return result[:80] or "Untitled"


# ── Reformat ────────────────────────────────────────────────

_HARD_RULES = (
    "STRICT RULES:\n"
    "- Use ONLY information present in the INPUT. No new facts, names, "
    "companies, job titles, dates, numbers, or details.\n"
    "- Do NOT expand, elaborate, or infer.\n"
    "- Output ONLY the formatted text. No preamble like 'Here is'. "
    "No commentary. No explanation."
)


REFORMAT_STYLES = {
    "raw": None,  # pass-through, no LLM call
    "casual": (
        "Task: rewrite the INPUT in clean casual prose. "
        "Fix grammar. Remove filler (um, uh, like, you know). "
        "Keep the speaker's voice and roughly the same length.\n\n"
        + _HARD_RULES
    ),
    "meeting": (
        "Task: rewrite the INPUT as short meeting notes.\n"
        "Format:\n"
        "Summary: <one sentence, based on the input>\n"
        "\n"
        "Key points:\n"
        "- <point from input>\n"
        "- <point from input>\n"
        "\n"
        "Use 2 to 4 bullets, only from the input. Do not add an "
        "'Action items' section unless the input clearly mentions tasks.\n\n"
        + _HARD_RULES
    ),
    "email": (
        "Task: rewrite the INPUT as one short email. Never longer than "
        "the input plus about 40 words.\n"
        "Format:\n"
        "Subject: <short subject from the input>\n"
        "\n"
        "Hi,\n"
        "\n"
        "<one or two short sentences carrying the input's content>\n"
        "\n"
        "Thanks\n"
        "\n"
        "Do not invent a recipient's name, a sender's job title, "
        "a company, or any other detail not in the input.\n\n"
        + _HARD_RULES
    ),
    "bullets": (
        "Task: rewrite the INPUT as a bulleted list. "
        "One '- ' bullet per item that appears in the input. "
        "No prose paragraphs. No headings. Only items actually in the input.\n\n"
        + _HARD_RULES
    ),
    "formal": (
        "Task: rewrite the INPUT as ONE short formal paragraph. "
        "Remove filler and casual phrasing. Neutral, third-person tone "
        "unless the input is clearly first-person. Same information, "
        "similar length. Never longer than the input plus about 20 words.\n\n"
        + _HARD_RULES
    ),
}


# Acceptable output length as a function of input length, per style. If the
# LLM output blows past this cap we discard it and return the input. Safer
# than showing a hallucinated wall of text.
_STYLE_CAPS = {
    "casual":  lambda n: n * 2 + 60,
    "meeting": lambda n: n * 3 + 200,
    "email":   lambda n: n + 250,
    "bullets": lambda n: n * 2 + 80,
    "formal":  lambda n: n + 120,
}


_REFORMAT_LEADS = ("Output:", "Here is", "Sure,", "Certainly,", "OK,", "Okay,")


def reformat_text(text: str, style: str) -> str:
    """Reformat text into the requested style via the LLM."""
    if not text or style == "raw" or style not in REFORMAT_STYLES:
        return text
    system = REFORMAT_STYLES[style]
    result = _llm(system, f"INPUT:\n{text}", timeout=90.0, max_tokens=400)
    if not result:
        return text
    result = _strip_preamble(result.strip(), _REFORMAT_LEADS)
    cap = _STYLE_CAPS.get(style, lambda n: n * 3 + 200)
    if len(result) > cap(len(text)):
        return text
    return result


# ── Translation ─────────────────────────────────────────────

SUPPORTED_LANGUAGES = {
    "en": "English",
    "af": "Afrikaans",
    "zu": "Zulu",
    "xh": "Xhosa",
    "st": "Southern Sotho",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "pt": "Portuguese",
    "it": "Italian",
    "nl": "Dutch",
    "zh": "Chinese (Simplified)",
    "ja": "Japanese",
    "ar": "Arabic",
}

_TRANSLATE_LEADS = ("Translation:", "Here is", "Sure,", "Certainly,")


def translate_text(text: str, lang_code: str) -> str:
    """Translate text into the target language. Returns the input unchanged
    on any failure."""
    if not text or lang_code not in SUPPORTED_LANGUAGES:
        return text
    target = SUPPORTED_LANGUAGES[lang_code]
    system = (
        f"Task: translate the INPUT into {target}. "
        "Preserve meaning, tone, punctuation, and paragraph breaks. "
        "Do NOT add commentary or headings. Output only the translation."
    )
    result = _llm(system, f"INPUT:\n{text}", timeout=90.0, max_tokens=600)
    if not result:
        return text
    result = _strip_preamble(result.strip().strip('"').strip("'"), _TRANSLATE_LEADS)
    # Sanity cap: translation length is usually within 3x of the source.
    if len(result) > len(text) * 4 + 200:
        return text
    return result


# ── Ask (RAG-lite over the user's own notes) ────────────────

_ASK_SYSTEM = (
    "You answer the user's question using ONLY the notes provided. "
    "If the answer is not in the notes, say 'I could not find that in your notes.' "
    "Be brief (1-3 sentences). Do NOT invent facts. Do NOT add commentary."
)

_ASK_CONTEXT_CHAR_BUDGET = 4000


def answer_from_notes(query: str, notes: list[dict]) -> str:
    """Answer a user question grounded in their own notes.

    Takes an already-ordered list of notes (newest first is typical) and
    packs as many as fit in the char budget into the prompt.
    """
    if not query.strip():
        return "Please enter a question."
    if not notes:
        return "You have no notes yet."

    ctx_lines = []
    total = 0
    for n in notes:
        title = n.get("title") or "Untitled"
        text = n.get("text") or ""
        block = f"- ({title}) {text}"
        if total + len(block) > _ASK_CONTEXT_CHAR_BUDGET:
            break
        ctx_lines.append(block)
        total += len(block)

    user_msg = "NOTES:\n" + "\n".join(ctx_lines) + f"\n\nQUESTION: {query.strip()}"
    result = _llm(_ASK_SYSTEM, user_msg, timeout=60.0, max_tokens=250)
    if not result:
        return "Sorry, the answer service is not reachable right now."
    return result.strip()
