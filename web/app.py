"""FastAPI application for Clever Dictate (web).

Routes are grouped in the file in the order a user hits them:
  1. Auth: register / login / logout / me
  2. Preferences: cleanup slider, hotkey, talk mode, theme
  3. Transcribe: upload one clip -> saved history entry
  4. History: list / update / continue / delete
  5. Reformat, translate, ask
  6. Export (txt / md / docx / pdf)
  7. Static frontend
"""
import os
import secrets
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load .env before any other module reads os.environ.
load_dotenv(Path(__file__).parent / ".env")

import bcrypt
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from itsdangerous import BadSignature, URLSafeSerializer
from pydantic import BaseModel
from sqlmodel import Session, SQLModel, create_engine, select

from audio import (
    CLEANUP_THRESHOLD_S,
    SUPPORTED_LANGUAGES,
    answer_from_notes,
    clean_text,
    fix_unbulleted_list,
    generate_title,
    reformat_text,
    transcribe_audio,
    translate_text,
)
from export import EXPORTERS
from models import Transcription, User


# ── Config ──────────────────────────────────────────────────

DATA_DIR = Path(os.environ.get("DATA_DIR", "data"))
DATA_DIR.mkdir(exist_ok=True)

DB_URL = os.environ.get("DB_URL", f"sqlite:///{DATA_DIR / 'dictate.db'}")
SESSION_COOKIE = "dictate_session"
SESSION_TTL_S = 60 * 60 * 24 * 14  # two weeks

ALLOWED_TALK_MODES = {"hold", "toggle"}
ALLOWED_THEMES = {"system", "light", "dark"}


def _load_secret_key() -> str:
    """Env var wins. Otherwise generate a key on first run and persist it
    to `DATA_DIR/.secret_key` so sessions survive server restarts."""
    env_key = os.environ.get("SECRET_KEY")
    if env_key:
        return env_key
    key_file = DATA_DIR / ".secret_key"
    if key_file.exists():
        return key_file.read_text().strip()
    generated = secrets.token_urlsafe(48)
    key_file.write_text(generated)
    try:
        os.chmod(key_file, 0o600)
    except OSError:
        pass
    return generated


SECRET_KEY = _load_secret_key()

engine = create_engine(DB_URL, connect_args={"check_same_thread": False})
signer = URLSafeSerializer(SECRET_KEY, salt="session")

app = FastAPI(title="Clever Dictate (web)")


# ── Schema migration + startup ──────────────────────────────

def _migrate_add_columns():
    """Add nullable columns to existing SQLite tables. On a fresh install
    this is a no-op because `SQLModel.metadata.create_all` already created
    the columns from the model."""
    with engine.connect() as conn:
        for table, col_defs in {
            "transcription": [
                ("title", "TEXT"),
                ("pinned", "INTEGER DEFAULT 0"),
            ],
            "user": [
                ("cleanup_level", "INTEGER DEFAULT 25"),
                ("hotkey", "TEXT DEFAULT 'Space'"),
                ("talk_mode", "TEXT DEFAULT 'hold'"),
                ("theme", "TEXT DEFAULT 'system'"),
            ],
        }.items():
            existing = {
                row[1]
                for row in conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
            }
            for name, ddl in col_defs:
                if name not in existing:
                    conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
        conn.commit()


@app.on_event("startup")
def on_startup():
    SQLModel.metadata.create_all(engine)
    _migrate_add_columns()


# ── Helpers ─────────────────────────────────────────────────

def get_db():
    with Session(engine) as s:
        yield s


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(401, "not signed in")
    try:
        user_id = signer.loads(token)
    except BadSignature:
        raise HTTPException(401, "invalid session")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(401, "unknown user")
    return user


def _login_response(user: User):
    resp = JSONResponse({"id": user.id, "email": user.email})
    resp.set_cookie(
        SESSION_COOKIE,
        signer.dumps(user.id),
        httponly=True,
        samesite="lax",
        max_age=SESSION_TTL_S,
    )
    return resp


def _hash_password(pw: str) -> str:
    # bcrypt only reads the first 72 bytes; truncate defensively.
    return bcrypt.hashpw(pw.encode("utf-8")[:72], bcrypt.gensalt()).decode("utf-8")


def _verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode("utf-8")[:72], hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def _user_dict(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "cleanup_level": user.cleanup_level,
        "hotkey": user.hotkey or "Space",
        "talk_mode": user.talk_mode or "hold",
        "theme": user.theme or "system",
    }


def _iso_utc(dt: datetime) -> str:
    """Return an ISO 8601 string with an explicit UTC marker. SQLite drops
    the timezone on save, so we re-attach UTC here to keep JavaScript
    Date parsing correct (naive ISO strings are treated as local time)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _serialise(t: Transcription) -> dict:
    return {
        "id": t.id,
        "title": t.title or "Untitled",
        "text": t.text,
        "mode": t.mode,
        "duration_s": t.duration_s,
        "pinned": bool(t.pinned),
        "created_at": _iso_utc(t.created_at),
    }


async def _save_upload_to_tempfile(upload: UploadFile) -> str:
    suffix = Path(upload.filename or "clip.webm").suffix or ".webm"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await upload.read())
        return tmp.name


def _transcribe_and_finalise(tmp_path: str, duration_s: float, cleanup_level: int) -> tuple[str, str]:
    """Run whisper -> cleanup -> bullet fix. Deletes the temp file, always.
    Returns (text, mode)."""
    try:
        raw = transcribe_audio(tmp_path)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    if not raw:
        raise HTTPException(400, "no speech detected")

    if duration_s >= CLEANUP_THRESHOLD_S and cleanup_level > 0:
        text = clean_text(raw, cleanup_level)
        mode = "cleaned" if text != raw else "raw"
    else:
        text = raw
        mode = "raw"
    return fix_unbulleted_list(text), mode


# ── Pydantic request bodies ─────────────────────────────────

class PrefsUpdate(BaseModel):
    cleanup_level: Optional[int] = None
    hotkey: Optional[str] = None
    talk_mode: Optional[str] = None
    theme: Optional[str] = None


class EntryUpdate(BaseModel):
    text: Optional[str] = None
    title: Optional[str] = None
    pinned: Optional[bool] = None


class ReformatBody(BaseModel):
    text: str
    style: str


class TranslateBody(BaseModel):
    text: str
    language: str  # ISO 639-1 short code from SUPPORTED_LANGUAGES


class AskBody(BaseModel):
    query: str


class ExportBody(BaseModel):
    text: str
    title: str = "Transcription"
    format: str  # "txt" | "md" | "docx" | "pdf"


# ── Auth ────────────────────────────────────────────────────

@app.post("/api/register")
def register(
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    email = email.strip().lower()
    if len(password) < 8:
        raise HTTPException(400, "password must be at least 8 characters")
    if db.exec(select(User).where(User.email == email)).first():
        raise HTTPException(400, "email already registered")
    user = User(email=email, password_hash=_hash_password(password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return _login_response(user)


@app.post("/api/login")
def login(
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    email = email.strip().lower()
    user = db.exec(select(User).where(User.email == email)).first()
    if not user or not _verify_password(password, user.password_hash):
        raise HTTPException(401, "invalid credentials")
    return _login_response(user)


@app.post("/api/logout")
def logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(SESSION_COOKIE)
    return resp


@app.get("/api/me")
def me(user: User = Depends(current_user)):
    return _user_dict(user)


# ── Preferences ─────────────────────────────────────────────

@app.patch("/api/prefs")
def update_prefs(
    body: PrefsUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    if body.cleanup_level is not None:
        if not 0 <= body.cleanup_level <= 100:
            raise HTTPException(400, "cleanup_level must be 0-100")
        user.cleanup_level = body.cleanup_level
    if body.hotkey is not None:
        hk = body.hotkey.strip()
        if not hk or len(hk) > 32:
            raise HTTPException(400, "invalid hotkey")
        user.hotkey = hk
    if body.talk_mode is not None:
        if body.talk_mode not in ALLOWED_TALK_MODES:
            raise HTTPException(400, "invalid talk_mode")
        user.talk_mode = body.talk_mode
    if body.theme is not None:
        if body.theme not in ALLOWED_THEMES:
            raise HTTPException(400, "invalid theme")
        user.theme = body.theme

    db.add(user)
    db.commit()
    db.refresh(user)
    return _user_dict(user)


# ── Transcribe ──────────────────────────────────────────────

@app.post("/api/transcribe")
async def transcribe(
    audio: UploadFile = File(...),
    duration_s: float = Form(...),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    tmp_path = await _save_upload_to_tempfile(audio)
    text, mode = _transcribe_and_finalise(tmp_path, duration_s, user.cleanup_level)

    entry = Transcription(
        user_id=user.id,
        text=text,
        title=generate_title(text),
        mode=mode,
        duration_s=duration_s,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return _serialise(entry)


# ── History ─────────────────────────────────────────────────

@app.get("/api/history")
def history(
    limit: int = 100,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    rows = db.exec(
        select(Transcription)
        .where(Transcription.user_id == user.id)
        .order_by(Transcription.pinned.desc(), Transcription.created_at.desc())
        .limit(limit)
    ).all()
    return [_serialise(r) for r in rows]


@app.patch("/api/history/{entry_id}")
def update_entry(
    entry_id: int,
    body: EntryUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    entry = db.get(Transcription, entry_id)
    if not entry or entry.user_id != user.id:
        raise HTTPException(404, "not found")
    if body.text is not None:
        entry.text = body.text
    if body.title is not None:
        entry.title = body.title[:80]
    if body.pinned is not None:
        entry.pinned = bool(body.pinned)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return _serialise(entry)


@app.post("/api/history/{entry_id}/continue")
async def continue_entry(
    entry_id: int,
    audio: UploadFile = File(...),
    duration_s: float = Form(...),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    entry = db.get(Transcription, entry_id)
    if not entry or entry.user_id != user.id:
        raise HTTPException(404, "not found")

    tmp_path = await _save_upload_to_tempfile(audio)
    addition, _mode = _transcribe_and_finalise(tmp_path, duration_s, user.cleanup_level)

    entry.text = (entry.text.rstrip() + "\n\n" + addition.lstrip()).strip()
    entry.duration_s = (entry.duration_s or 0) + duration_s
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return _serialise(entry)


@app.delete("/api/history/{entry_id}")
def delete_entry(
    entry_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    entry = db.get(Transcription, entry_id)
    if not entry or entry.user_id != user.id:
        raise HTTPException(404, "not found")
    db.delete(entry)
    db.commit()
    return {"ok": True}


# ── Reformat / translate / ask ──────────────────────────────

@app.post("/api/reformat")
def reformat(body: ReformatBody, user: User = Depends(current_user)):
    out = reformat_text(body.text, body.style)
    changed = out.strip() != body.text.strip() and body.style != "raw"
    return {"text": out, "changed": changed}


@app.get("/api/languages")
def languages(user: User = Depends(current_user)):
    return [{"code": k, "label": v} for k, v in SUPPORTED_LANGUAGES.items()]


@app.post("/api/translate")
def translate(body: TranslateBody, user: User = Depends(current_user)):
    if body.language not in SUPPORTED_LANGUAGES:
        raise HTTPException(400, "unsupported language")
    out = translate_text(body.text, body.language)
    changed = out.strip() != body.text.strip()
    return {"text": out, "changed": changed}


@app.post("/api/ask")
def ask(
    body: AskBody,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    rows = db.exec(
        select(Transcription)
        .where(Transcription.user_id == user.id)
        .order_by(Transcription.created_at.desc())
        .limit(30)
    ).all()
    notes = [{"title": r.title or "Untitled", "text": r.text} for r in rows]
    return {"answer": answer_from_notes(body.query, notes)}


# ── Export ──────────────────────────────────────────────────

@app.post("/api/export")
def export(body: ExportBody, user: User = Depends(current_user)):
    exporter = EXPORTERS.get(body.format)
    if not exporter:
        raise HTTPException(400, f"unsupported format: {body.format}")
    data, filename, mime = exporter(body.text, body.title or "Transcription")
    return Response(
        content=data,
        media_type=mime,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Static frontend ─────────────────────────────────────────

_static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


@app.get("/")
def index():
    return FileResponse(_static_dir / "index.html")
