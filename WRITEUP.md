# Writeup

## 1. What I did

Hay, hope all is well! I rebuilt this into a small web-app, a + of this is that this can 
now be re-used by a team instead of being machine-only, once deployed with docker. I left the 
original `dictate.py` and `dictate_tray.py` as reference, also the macOS install
with launch sripts are untouched. 

Why did I choose to rebuild?
Mostly because I am on a Windows machine, but an added benefit is that it is now
on web so multi-device friendly. 

What is different from the prototype? 

- Email + password login. Each user has their own history in SQLite (if multi-user would 
  end up being the end goal)
- Whisper via `faster-whisper` instead of Apple MLX.
- Fallback to just capturing raw text if Ollama is not set or broken.
- History is a table that is now attached to a user.
- Like voice to text new features (title, cleanup, reformat, translate, ask) has a
  safe fallback if Ollama is unreachable.

Features I built on top of what the original had:

- Auto-generated titles: on every note, just an organisational quirk.
- Format and export: Giving the user the ability to reformat the note as these:
  Raw / Casual / Meeting notes / Email / Bullets / Formal document, then
  download the formatted doc as `.txt`, `.md`, `.docx`, or `.pdf`.
  This is all done via AI like the recording --> text.
- Translation into 14 languages: Just a small nice to have, don't know if it 
  will be used really. 
- "Ask your notes": Tiny RAG-lite over the user's recent notes.
  Type a question, get an answer from the extent of your notes.
- Continue recording: Giving the user ability to continue on a previous note, 
  this one seems nice to have to me.
- Pinning Notes: Easy access to important recordings!
- Live audio waveform: Just something to make UI feel interactive.
- Settings (gear in the header): configurable push-to-talk key,
  hold-to-talk vs press-to-toggle, light/dark theme.
- Inline edit: Just ability to edit on page withotu opening up note,
  might be nice sometimes.

What is regressed on purpose:

- No paste-at-cursor. A browser cannot type into another OS window. You
  copy from the page and paste yourself. Loss from swapping.


## 2. Findings: confusions and breaks I hit

Some things I picked up while reading through the original. 

- The docs, the code, and the tray label all differ on which key to hold.
  The docstring at `dictate.py:4` says "Left Option", the listener 
  is bound to `alt_r` (Right Option) at `dictate.py:370`, and the empty
  state label in the tray says "Right Control" (`dictate_tray.py:572`). 
  Just different keys for the same thing, probably from development lifecycle.
- The `pgrep`-and-kill-siblings block at `dictate.py:12-21` and 
  `dictate_tray.py:9-17`, if you run it twice, it will kill the other one.
- History is a flat JSON file (`dictate.py:268-271`), atomic writes but 
  no locking. Two writers can still stomp on each other between load 
  and write. The kill-siblings thing above mentioned is basically the workaround.
- `_check_audio_level` at `dictate.py:312-323` uses a hardcoded 
  `rms > 200` could be fine for 1 pc mic, but might be an issue if deployed,
  because different mics have different sensitivities.
- `clear_all` (`dictate_tray.py:534-547`) is actually cosmetic. It just
  writes a `cleared_before` timestamp and leaves the data in the file. 
- The Restart button hardcodes 
  `/Library/Frameworks/Python.framework/Versions/3.13/bin/python3` and
  `~/.local/bin/dictate*.py` (`dictate_tray.py:524-530`). So any new user would
  not be able to use this button.
- First-run downloads the Whisper and Qwen models silently from Hugging 
  Face. Could add a loader or some ui to not have app seem frozen.

I just fixed the ones relevant to a webapp, rest is named here though.

FIXED:
- Hotkey is user-configurable in Settings now, so no more three-way
  disagreement on which key to hold.
- History lives in a proper SQLite table keyed to a user, no more flat
  JSON file to race on. That also means the kill-siblings hack is not
  needed.
- Silence detection uses `faster-whisper`'s built-in VAD filter instead
  of a hardcoded RMS threshold, so it should be more robust across mics.
- Delete actually deletes (per-row Delete button removes it from the DB),
  no more cosmetic "clear that isn't a clear".
- No Restart button needed, beacuse it is now a web server that just runs.

## 3. Prioritization: the next two weeks

Ordered by what I would tackle first:

1. SSO via Azure Entra ID: Email + password is fine for a quick demo, but 
   for actual company use it would need to swap to Entra so the team just 
   signs in with their work accounts.
2. Streaming transcription: Right now you speak, wait, then see text. Real 
   time feedback feels a lot better.`faster-whisper` supports it, would just need a 
   WebSocket added to implement this, will make ui feel more alive too!
3. Postgres instead of SQLite: SQLite is fine for one user, but a shared 
   web app really wants proper write concurrency. One env var change plus 
   a compose service, not much work.
4. Per-user daily token cap (maybe): If we ever swap off Ollama to a paid LLM,
   one enthusiastic user could rack up a real bill. Just track 
   `tokens_used_today` per user and reject once they hit the cap.
5. Real delete-my-history: The original's cosmetic clear to be replaced.
   Add a real DELETE endpoint and a "delete all my data" button that actually
   wipes the DB.
6. Audit log of who transcribed when: Metadata only, no text. Just so a 
   later security questions would have an answer.
7. An admin tab, should the app get used by a bunch of people.

## 4. Real-world readiness

- Error handling: Right now the status line just shows the last error and 
  that's about it. Missing: retries on transient upload errors, an 
  "uploading" state so a slow connection doesn't feel frozen, and a proper 
  way to see server-side errors (I like Sentry).
- Auth and access: Current MVP has email + password with bcrypt hashes 
  and signed httponly cookies. Real deployment would need Entra SSO,
  a way to revoke sessions, and per-user rate limiting. No 
  password reset flow yet, deliberately, since Entra does this.
- Privacy and data: Audio is written to a temp file and unlinked right 
  after transcription. Only text gets stored, keyed to the user. Gaps: 
  no encryption at rest, no data residency options, no export-my-data 
  endpoint. All three would be needed for safety.
- Reliability: Single process, single SQLite file, no backups. Not
  really production-ready, if the process crashes or the file gets
  corrupted there's no recovery. Would want automated DB backups and
  a restart-on-crash setup before letting a team depend on this daily.
- Onboarding for non-technical users: `python run.py`, wait for the
  browser to open, click Sign in. For a hosted deployment: create an
  Entra group, add the team, share the URL. That way nothing needs
  installing on the user's machine at all.

## 5. Trade-offs

- SQLite, not Postgres: SQLite is just a file on disk, so the app
  boots with `python run.py` and needs no external services at all.
  Traded proper multi-user write concurrency for setup simplicity,
  would swap to Postgres before deploying this to a real team.
- No streaming: Would have liked to add text as you talk.
- No paste-at-cursor: Already named in section 1.
- Vanilla HTML/JS/CSS, no framework: Would have loved React/Blazor.
  but in interrest of time.
- Local Qwen 2.5 1.5B via Ollama: Same model family as the original.
  Kept it local so nothing leaves the machine, even though a bigger
  cloud model would probably give better output. Also just faster to
  set up locally than wire up a cloud API.

## 6. How I worked

- Approach: Spent about a hour orientating myself and reading through
  the two Python files end to end. Then decided to go web because reading
  through the instructions made it kind of clear that the end goal would be
  multi user. Being on a Windows machine also kind of sealed it, since
  the MLX stack wouldn't run for me locally anyway.
- Where I used AI, and where I didn't: I use AI as much as I can, no need to do ui 
  etc yourself anymore. I keep my hands on the wheel by actually reading and understanding 
  what is being done (before and after). I also ALWAYS set up a Body of Knowledge directory 
  up in my projects, this not only gives you a good understanding of every decision
  made, but will also show where I directed AI, and makes it extremely easy for 
  another person/you're AI to gather all needed context instantly. the big scoping calls were 
  mine as well: web over a Windows port, which features to add and which to skip.
- Checking the AI: Tried to add in real-time collaboration via WebSockets,
  which is way out of scope for what I had planned/in-mind. Bad because it adds a lot
  of complexity (state sync, presence, conflict handling) I needed the time to add features.
  When I tested reformatting a short "hi, my name is Konrad" intro as an email, it invented an 
  entire fake job application at a fake company with credentials I don't have. Manually adjusted 
  prompts that are sent when reformatting and added a length cap.
  Also has a knack of slipping in features not asked for. I try to always keep to scope and keep 
  things simple.
- Unfamiliar ground: MLX and PyObjC, never touched either. Didn't need 
  to run them to review the code (Python is Python). Working at an outsourcing
  company I can never choose my tech stack, but I am most familliar with C# with Blazor
  and for mobile got xp on Virgin Active Kotlin/Swift setup. But I have worked on Python projects before.
- Confidence: Least sure about the Docker path actually working end to end. I built the Dockerfile 
- and compose file but they are just there for if it were deployed.
  Docker should work in theory but I can't promise it, intended to be tested with just run.py.


## 7. Open questions for stakeholders

- Who is this actually for? Everyone in the company, one team, or 
  specific roles? Answer will change planning.
- How sensitive would the recordings be? Could change approach on privacy.
- Is Ollama the standard for the org? Could implement a paid model.
- Do we care about paste-at-cursor? Just because it was dropped.
- Language support - Could support Afrikaans note taking etc in future.

## Assumptions

- Think everything I can think of is in this writeup!
