# Clever Dictate: practical assessment base repo

This repo is the starting point for the CleverProfits **AI Automations Analyst** practical project. It holds a real, half-built internal tool. Your job is to take it forward.

<p align="center">
  <a href="https://ai-specialist-builder-practical-project-production.up.railway.app/">
    <img src="assets/read-the-brief.svg" alt="Read the full brief" width="460">
  </a>
</p>

> The brief (deliverables, scoring, time budget) is also in [`TASK.md`](./TASK.md) so the repo stands on its own. **Read it first.**

---

## This fork: web rewrite

The original app is macOS Apple Silicon only. I rebuilt it as a small
multi-user web app in [`web/`](./web/). The original `dictate.py` and
`dictate_tray.py` are left in place as reference. The WRITEUP references
them by line number.

See [`WRITEUP.md`](./WRITEUP.md) for the direction, the findings, and the
next-two-weeks plan. See [`BOK/`](./BOK/) for the material decisions made
along the way.

### Simplest way to run it

```bash
cd web
python run.py
```

`run.py` creates a virtual environment on first use, installs the
dependencies, generates a secret key, opens the browser at
<http://localhost:8000>, and starts the server. First run takes about
2-3 minutes for the install; subsequent runs start in a couple of seconds.

Requirements: **Python 3.10 or newer**, **ffmpeg** on your PATH, a modern
browser, and a microphone.

- Python: <https://www.python.org/downloads/>
- ffmpeg on Windows: `winget install Gyan.FFmpeg`
- ffmpeg on macOS: `brew install ffmpeg`
- ffmpeg on Linux: `apt install ffmpeg` (or your distro equivalent)

Once the browser opens:

1. Click **Create an account**, enter any email and a password (8+ characters).
2. Grant microphone permission when the browser asks.
3. Hold the **Hold to talk** button, or hold **Space**, and speak.
4. Release. The first transcription takes about 30 seconds while Whisper
   downloads the `small.en` model (~500 MB) into a local cache. Every
   transcription after that runs in a few seconds.

To stop: `Ctrl+C` in the terminal.

Your SQLite database lives at `web/data/dictate.db`. Deleting it wipes
all users and history. `web/data/` is `.gitignored` and will not be
committed.

### Alternative: Docker

If you would rather not install Python locally, and you have Docker
Desktop running:

```bash
cd web
docker compose up --build
```

On the first run the build takes about 3-5 minutes. Every run after that
is a few seconds because Docker caches the layers. Open
<http://localhost:8000> once you see `Uvicorn running` in the terminal.

Docker Desktop installer if you do not have it:
<https://www.docker.com/products/docker-desktop/>.

### Turning on the LLM cleanup pass (optional)

By default the app returns Whisper's raw output. To enable the cleanup
pass on recordings longer than 15 seconds, edit `web/.env`:

```
OLLAMA_URL=http://host.docker.internal:11434
OLLAMA_MODEL=qwen3.5:cloud
```

`host.docker.internal` reaches an Ollama running on the host from inside
the container. Restart the container after changing `.env`:
`docker compose up -d --force-recreate`.

If Ollama is unreachable the app falls back to raw output silently — the
transcription still comes back, it just is not cleaned.

### Manual developer setup (if `run.py` is not what you want)

```bash
cd web
python -m venv .venv
.venv\Scripts\activate         # PowerShell / cmd on Windows
# source .venv/bin/activate    # macOS / Linux
pip install -r requirements.txt
uvicorn app:app --reload
```

The app auto-generates a secret key into `data/.secret_key` on first
launch, so no `.env` editing is required for a demo. Override
`SECRET_KEY` (and other settings) via env vars for real deployments —
see `.env.example` for the full list.

### Troubleshooting

- **"Port 8000 is already in use."** Something else is bound to 8000.
  Change the left side of `"8000:8000"` in `web/docker-compose.yml`
  (e.g. `"8080:8000"`) and open <http://localhost:8080> instead.
- **"Mic permission denied."** In the browser, click the padlock icon
  next to the URL and re-grant microphone access, then reload.
- **First transcription hangs.** Whisper is downloading the model. Watch
  the terminal running `docker compose up` — you will see the download
  progress from Hugging Face.
- **Cleanup pass is not running.** Check `OLLAMA_URL` in `.env`. Test
  the URL from the container with `docker compose exec web curl
  $OLLAMA_URL/api/tags` — you should see a JSON list of models.

The original macOS instructions are below and remain valid if you have
an Apple Silicon Mac.

---

## What the app is

Clever Dictate is a 100% local voice-to-text tool for macOS (Apple Silicon). Hold a push-to-talk key, speak, release, and the text gets pasted at your cursor. Everything runs on-device through Apple's MLX framework: no external APIs, nothing leaves the machine.

- Short recordings get raw Whisper transcription, pasted straight away.
- Long recordings get a second pass through a local LLM (Qwen) to clean them up. It loads on first use, so the first long dictation is slow.
- A menu-bar app shows your transcription history and settings.
- Models: `whisper-small.en` and `Qwen2.5-1.5B-Instruct`, both on-device via MLX.

## What you're walking into

One person built this for themselves. It works, but it carries every "runs on my machine" assumption you'd expect. Treat it honestly:

- Finding what's confusing, broken, or unsafe is part of the job. Write it down as you go.
- Don't trust the docs, comments, or button labels. Check them against the code and what actually happens.
- We're not grading feature count. Thoughtful and unfinished beats thoughtless and voluminous.

## Your task, in one line

Make this something everyone at the company could use safely, and show your reasoning. You can harden the native app or rebuild it as a web / multi-user app. Both are fair game. The full brief is in [`TASK.md`](./TASK.md); put your findings in [`WRITEUP.md`](./WRITEUP.md).

---

## Running the prototype

These notes cover the app as it stands today. They're rough on purpose, and tightening them is part of the exercise. If you take the app somewhere new, update this section to match what you built.

### Requirements

- **Apple Silicon Mac (M1 or later).** MLX is Apple-Silicon-only. There's no Intel or non-macOS path today.
- **Python 3.13**, the framework build from [python.org] (the menu-bar app needs a framework build to draw a GUI). It expects `/Library/Frameworks/Python.framework/Versions/3.13`.
- **Homebrew** and **ffmpeg** (`brew install ffmpeg`) for audio capture.
- A few GB of free disk and a network connection on first run. The Whisper and Qwen models download from Hugging Face the first time you use them.

### Install dependencies

```bash
python3 -m pip install -r requirements.txt
```

### Run it (development)

Two processes make up the app:

```bash
python3 dictate.py        # engine: hotkey listener, recording, transcription, paste
python3 dictate_tray.py   # menu-bar app: history window and settings
```

The first launch prints model-loading progress and chimes when it's ready.

### Grant macOS permissions

macOS asks for these the first time. The app does nothing useful without them:

- **Microphone**, to record.
- **Accessibility**, to catch the global hotkey and inject the paste keystroke.

### Use it

Hold the push-to-talk key, speak, release. The text gets transcribed and pasted at your cursor. History shows up in the menu-bar window.

> Which key is the push-to-talk key? Work it out from the code and the docs, and note whether they agree.

### The `.app` bundle and installer

- `install.sh` is the author's one-shot installer. Read it before you run it. It copies scripts into `~/.local/bin`, writes state under `~/.local/share/dictate`, drops the `.app` in `/Applications`, and sets up a LaunchAgent.
- `Clever Dictate.app` is a launcher wrapper. Check what it actually runs, and whether it's signed, before you count on it running anywhere but this machine.

### Where state lives

- Settings: `~/.local/share/dictate/settings.json`
- History: `~/.local/share/dictate/history.json`
- Logs: `/tmp/dictate.log`, `/tmp/dictate_tray.log`, `/tmp/ffmpeg_err.log`

---

## Repo contents

| Path | What it is |
|------|------------|
| `dictate.py` | The engine: hotkey listener, recording, Whisper transcription, LLM cleanup, auto-paste |
| `dictate_tray.py` | Menu-bar app: history window and settings |
| `install.sh` | The author's one-shot installer (LaunchAgent, deps, copies scripts) |
| `Clever Dictate.app/` | macOS `.app` launcher bundle (a wrapper that starts the two scripts) |
| `requirements.txt` | Python dependencies |
| `TASK.md` | The full brief. Read first |
| `WRITEUP.md` | Template for your writeup deliverable. Fill it in |

## Ground rules

- Fork or branch this repo and commit your work there.
- Use any AI tools and libraries you want. Restructure the code freely.
- Where the brief is silent, make a call and write down the assumption.
- The work should reflect your own reasoning and decisions.

[python.org]: https://www.python.org/downloads/macos/
