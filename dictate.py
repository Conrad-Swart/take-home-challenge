#!/usr/local/bin/python3
"""
Clever Dictate — Local voice-to-text for macOS.
Hold Left Option → speak → release → text auto-pasted at cursor.
Fully local — no APIs, no cloud, no data leaves your machine.

Short recordings (<8s) → raw Whisper output, instant paste.
Long recordings (≥8s) → Whisper + Qwen cleanup (lazy-loaded on first use).
"""
import subprocess, threading, time, ctypes, queue, tempfile, os, signal, shutil, sys, json, re

# ── Kill any existing dictate instances before starting ──────────────────────
_my_pid = os.getpid()
try:
    result = subprocess.run(['pgrep', '-f', 'dictate.py'], capture_output=True, text=True)
    for pid_str in result.stdout.strip().split('\n'):
        if pid_str and int(pid_str) != _my_pid:
            os.kill(int(pid_str), signal.SIGTERM)
            print(f"Killed stale dictate instance (PID {pid_str})", flush=True)
except Exception:
    pass
from datetime import datetime, timezone
import numpy as np
import mlx_whisper
from pynput.keyboard import Controller as KbCtrl, Key  # for Cmd+V paste

# ── Config ──────────────────────────────────────────────────────────────────
WHISPER_MODEL    = "mlx-community/whisper-small.en-mlx"
LLAMA_MODEL      = "mlx-community/Qwen2.5-1.5B-Instruct-4bit"
SAMPLE_RATE      = 16000
QWEN_THRESHOLD_S = 15  # seconds — recordings longer than this get Qwen cleanup
# ────────────────────────────────────────────────────────────────────────────

# ── Auto-detect ffmpeg ──────────────────────────────────────────────────────

FFMPEG = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
if not os.path.exists(FFMPEG):
    print("ERROR: ffmpeg not found. Install with: brew install ffmpeg", flush=True)
    sys.exit(1)

# ── Auto-detect microphone ──────────────────────────────────────────────────

def detect_mic() -> str:
    """Find the default audio input device index for ffmpeg avfoundation."""
    import re
    result = subprocess.run(
        [FFMPEG, '-f', 'avfoundation', '-list_devices', 'true', '-i', ''],
        capture_output=True, text=True
    )
    lines = result.stderr.splitlines()
    audio_section = False
    for line in lines:
        if 'audio devices' in line.lower():
            audio_section = True
            continue
        if audio_section and '[' in line:
            match = re.search(r'\[(\d+)\]', line)
            if not match:
                continue
            idx = match.group(1)
            if 'MacBook' in line or 'Built-in' in line:
                return f":{idx}"
    audio_section = False
    for line in lines:
        if 'audio devices' in line.lower():
            audio_section = True
            continue
        if audio_section and '[' in line:
            match = re.search(r'\[(\d+)\]', line)
            if match:
                return f":{match.group(1)}"
    return ":0"

AUDIO_DEVICE = detect_mic()

# ── Low-latency system sounds ───────────────────────────────────────────────

_at = ctypes.cdll.LoadLibrary('/System/Library/Frameworks/AudioToolbox.framework/AudioToolbox')
_cf = ctypes.cdll.LoadLibrary('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
_cf.CFURLCreateFromFileSystemRepresentation.restype  = ctypes.c_void_p
_cf.CFURLCreateFromFileSystemRepresentation.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_bool]
_cf.CFRelease.argtypes = [ctypes.c_void_p]
_at.AudioServicesCreateSystemSoundID.restype  = ctypes.c_int
_at.AudioServicesCreateSystemSoundID.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
_at.AudioServicesPlaySystemSound.argtypes     = [ctypes.c_uint32]

def _make_sound_id(path: str) -> int:
    b   = path.encode()
    url = _cf.CFURLCreateFromFileSystemRepresentation(None, b, len(b), False)
    sid = ctypes.c_uint32(0)
    _at.AudioServicesCreateSystemSoundID(url, ctypes.byref(sid))
    _cf.CFRelease(url)
    return sid.value

_SND = {
    "Tink":  _make_sound_id("/System/Library/Sounds/Tink.aiff"),
    "Glass": _make_sound_id("/System/Library/Sounds/Glass.aiff"),
    "Basso": _make_sound_id("/System/Library/Sounds/Basso.aiff"),
}

def chime(name="Tink"):
    _at.AudioServicesPlaySystemSound(_SND[name])

# ── Startup — Whisper (always loaded) ────────────────────────────────────────

_whisper_lock = threading.Lock()

print(f"Loading Whisper ({WHISPER_MODEL.split('/')[-1]})…", flush=True)
mlx_whisper.transcribe(np.zeros(SAMPLE_RATE, dtype=np.float32), path_or_hf_repo=WHISPER_MODEL, language="en")
print("Whisper ready.", flush=True)

# ── Qwen correction model — lazy loaded on first long dictation ──────────────

_llm_model = None
_llm_tokenizer = None
_llm_generate_fn = None
_qwen_loaded = False

def _ensure_qwen_loaded():
    """Load Qwen on first use."""
    global _llm_model, _llm_tokenizer, _llm_generate_fn, _qwen_loaded
    if _qwen_loaded:
        return
    print("Loading Qwen correction model…", flush=True)
    t0 = time.perf_counter()
    from mlx_lm import load as _llm_load, generate as _gen
    _llm_model, _llm_tokenizer = _llm_load(LLAMA_MODEL)
    _llm_generate_fn = _gen
    _llm_generate_fn(_llm_model, _llm_tokenizer, prompt="test", max_tokens=5, verbose=False)
    elapsed = time.perf_counter() - t0
    _qwen_loaded = True
    print(f"Qwen ready ({elapsed:.1f}s)", flush=True)
    chime("Glass")

# ── Settings ─────────────────────────────────────────────────────────────────

SETTINGS_FILE = os.path.join(os.path.expanduser("~/.local/share/dictate"), "settings.json")

def load_settings() -> dict:
    try:
        with open(SETTINGS_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {"cleanup_level": 25}

def build_correction_prompt(level: int) -> str:
    """Build system prompt based on cleanup level (0-100)."""
    if level == 0:
        return ""

    rules = [
        "You are a text filter. You do NOT converse, respond, or answer. Output ONLY the corrected text.",
        "Remove filler sounds: um, uh, hmm, er, ah.",
        "Add proper punctuation: commas, periods, question marks, apostrophes.",
        "Fix capitalization.",
    ]

    if level <= 25:
        rules.append("Do NOT remove, add, rephrase, or rearrange any other words. Exception: you MUST still add '- ' bullet prefixes for list items.")
    if level > 25:
        rules.append("Remove filler phrases: like, basically, you know, I mean, so, go ahead and, the thing is, kind of, sort of.")
        rules.append("Keep all other words exactly as spoken. Do not rephrase. Exception: you MUST still add '- ' bullet prefixes for list items.")
    if level > 50:
        rules.append("Remove false starts and repeated phrases.")
        rules.append("Fix grammar while keeping the speaker's word choices and tone.")
    if level > 75:
        rules.append("Restructure for clarity and conciseness while preserving meaning.")
        rules.append("Convert rambling speech into clean, professional written text.")

    rules.append(
        "LIST FORMATTING (highest priority — overrides other rules):\n"
        "When the speaker lists multiple items — whether using numbered words (number one/two/three, first/second/third), "
        "or listing things in sequence separated by pauses or conjunctions (item, item, and item), "
        "or saying 'here is what I need' followed by individual items — "
        "format each item as '- ' bullet, one per line.\n"
        "Keep all text before the first item as a paragraph above. "
        "Keep all text after the last item as a paragraph below. Never drop surrounding text.\n"
        "If no list is detected, output plain text only."
    )

    return "\n".join(rules)


_ORDINAL_RE = re.compile(r'^(Number\s+\w+|#?\d+[\.\):]|\w+[\.\)])\s', re.IGNORECASE)

def _fix_unbulleted_list(text: str) -> str:
    """Post-process: if 2+ consecutive lines look like ordinal list items without '- ', add bullets."""
    lines = text.split('\n')
    if len(lines) < 2:
        return text
    ordinal_lines = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('- '):
            continue
        if _ORDINAL_RE.match(stripped):
            ordinal_lines.append(i)
    if len(ordinal_lines) >= 2:
        consecutive = all(
            ordinal_lines[j] == ordinal_lines[j-1] + 1
            for j in range(1, len(ordinal_lines))
        )
        if consecutive:
            for idx in ordinal_lines:
                lines[idx] = '- ' + lines[idx].strip()
            return '\n'.join(lines)
    return text


def correct_text(raw: str) -> str:
    """Run LLM correction on raw transcription. Returns cleaned text."""
    settings = load_settings()
    level = settings.get("cleanup_level", 25)

    if level == 0:
        return raw

    _ensure_qwen_loaded()

    system_prompt = build_correction_prompt(level)
    print(f"  qwen level={level} prompt_len={len(system_prompt)}", flush=True)

    messages = [{"role": "system", "content": system_prompt}]
    messages.append({"role": "user", "content": "So here is what I got from the shop um number one was apples number two was bananas and number three was grapes and that is pretty much everything for today"})
    messages.append({"role": "assistant", "content": "Here is what I got from the shop.\n- Apples\n- Bananas\n- Grapes\nThat is pretty much everything for today."})
    messages.append({"role": "user", "content": raw})
    prompt = _llm_tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)

    result = _llm_generate_fn(_llm_model, _llm_tokenizer, prompt=prompt, max_tokens=5000, verbose=False)
    cleaned = result.strip().strip('"')

    if not cleaned:
        return raw
    cleaned = _fix_unbulleted_list(cleaned)
    if len(cleaned) > len(raw) * 2:
        return raw
    return cleaned

_kb_ctrl = KbCtrl()
_wav_queue = queue.Queue()

print(f"Mic: {AUDIO_DEVICE} | Whisper: {WHISPER_MODEL.split('/')[-1]} | Qwen threshold: {QWEN_THRESHOLD_S}s", flush=True)
print("Ready — hold Right Option to dictate.", flush=True)
chime("Glass")

# ── History persistence ───────────────────────────────────────────────────

HISTORY_DIR  = os.path.expanduser("~/.local/share/dictate")
HISTORY_FILE = os.path.join(HISTORY_DIR, "history.json")
MAX_HISTORY  = 100

def save_to_history(text: str, used_qwen: bool):
    """Append a transcription to the shared history file (atomic, capped)."""
    os.makedirs(HISTORY_DIR, exist_ok=True)
    history = {"transcriptions": []}
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                history = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    history["transcriptions"].append({
        "text": text,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": "qwen" if used_qwen else "raw",
    })
    history["transcriptions"] = history["transcriptions"][-MAX_HISTORY:]
    tmp_path = HISTORY_FILE + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(history, f, indent=2)
    os.replace(tmp_path, HISTORY_FILE)

# ── Pipeline ─────────────────────────────────────────────────────────────────

_ffmpeg_proc = None
_tmp_wav     = None

def start_recording():
    global _ffmpeg_proc, _tmp_wav
    _tmp_wav = tempfile.NamedTemporaryFile(suffix='.wav', delete=False).name
    _ffmpeg_proc = subprocess.Popen([
        FFMPEG, '-y',
        '-f', 'avfoundation',
        '-i', AUDIO_DEVICE,
        '-ar', '16000',
        '-ac', '1',
        '-acodec', 'pcm_s16le',
        '-af', 'highpass=f=80,lowpass=f=8000',
        _tmp_wav,
    ], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=open("/tmp/ffmpeg_err.log", "w"))

def stop_recording() -> str:
    global _ffmpeg_proc
    if _ffmpeg_proc:
        _ffmpeg_proc.send_signal(signal.SIGINT)
        _ffmpeg_proc.wait(timeout=3)
        _ffmpeg_proc = None
    return _tmp_wav

def transcribe(wav_path: str) -> str:
    try:
        with _whisper_lock:
            result = mlx_whisper.transcribe(
                wav_path,
                path_or_hf_repo=WHISPER_MODEL,
                language="en",
            )
        return result["text"].strip()
    finally:
        os.unlink(wav_path)

def _check_audio_level(wav_path: str) -> bool:
    """Return True if audio has enough signal to be speech, False if silence."""
    import wave
    try:
        with wave.open(wav_path) as wf:
            frames = wf.readframes(wf.getnframes())
            audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32)
            rms = np.sqrt(np.mean(audio**2))
            print(f"  audio RMS: {rms:.0f}", flush=True)
            return rms > 200  # threshold — real speech is typically 500+
    except Exception:
        return True  # if we can't check, proceed anyway

def process_wav(wav_path: str, duration_s: float):
    if not wav_path or not os.path.exists(wav_path):
        return
    size = os.path.getsize(wav_path)
    if size < 16000:
        print("Too short — ignored.", flush=True)
        os.unlink(wav_path)
        return

    # Silence gate — skip transcription if audio is too quiet
    if not _check_audio_level(wav_path):
        print("Too quiet — no speech detected, skipping.", flush=True)
        os.unlink(wav_path)
        return

    use_qwen = duration_s >= QWEN_THRESHOLD_S
    print(f"Transcribing… ({duration_s:.1f}s, {'qwen' if use_qwen else 'raw'})", flush=True)

    raw = transcribe(wav_path)
    if not raw:
        chime("Basso")
        return
    print(f"  raw → {raw}", flush=True)

    if use_qwen:
        t0 = time.perf_counter()
        cleaned = correct_text(raw)
        correction_ms = (time.perf_counter() - t0) * 1000
        print(f"  out → {cleaned}  ({correction_ms:.0f}ms qwen)", flush=True)
    else:
        cleaned = raw
        print(f"  out → {cleaned}  (raw, skipped qwen)", flush=True)

    subprocess.run(["pbcopy"], input=cleaned.encode(), check=False)
    time.sleep(0.05)
    _kb_ctrl.press(Key.cmd)
    _kb_ctrl.press('v')
    _kb_ctrl.release('v')
    _kb_ctrl.release(Key.cmd)
    save_to_history(cleaned, use_qwen)


# ── Hotkey hold-to-talk ──────────────────────────────────────────────────────

from pynput import keyboard as kb_module
HOTKEY = kb_module.Key.alt_r   # Right Option

_held = False
_record_start = 0

def _maybe_focus_vscode():
    """Bring VS Code to front if the setting is enabled."""
    try:
        settings = load_settings()
        if settings.get("focus_vscode", False):
            subprocess.Popen(
                ['osascript', '-e', 'tell application "Visual Studio Code" to activate'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
    except Exception:
        pass

def on_press(key):
    global _held, _record_start
    if key == HOTKEY and not _held:
        _held = True
        _record_start = time.perf_counter()
        _maybe_focus_vscode()
        start_recording()
        time.sleep(0.5)         # let ffmpeg fully initialize the mic
        chime("Tink")           # chime = "mic is hot, start speaking now"

def on_release(key):
    global _held
    if key == HOTKEY and _held:
        _held = False
        duration_s = time.perf_counter() - _record_start
        chime("Tink")           # immediate feedback — "I heard you let go"
        time.sleep(0.4)         # tail buffer still captures trailing words
        wav_path = stop_recording()
        _wav_queue.put((wav_path, duration_s))

# ── Main loop ────────────────────────────────────────────────────────────────

listener = kb_module.Listener(on_press=on_press, on_release=on_release)
listener.start()

try:
    while True:
        try:
            wav_path, duration_s = _wav_queue.get(timeout=0.5)
            process_wav(wav_path, duration_s)
        except queue.Empty:
            pass
except KeyboardInterrupt:
    print("Dictate stopped.", flush=True)
finally:
    listener.stop()
