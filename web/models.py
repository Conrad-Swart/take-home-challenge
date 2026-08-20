from datetime import datetime, timezone
from typing import Optional

from sqlmodel import SQLModel, Field


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True)
    password_hash: str
    cleanup_level: int = Field(default=25)  # 0-100, mirrors the original slider
    hotkey: str = Field(default="Space")  # KeyboardEvent.code (e.g. "Space", "KeyA")
    talk_mode: str = Field(default="hold")  # "hold" or "toggle"
    theme: str = Field(default="system")  # "system" | "light" | "dark"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Transcription(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    text: str
    title: Optional[str] = None
    mode: str  # "raw" or "cleaned"
    duration_s: float
    pinned: bool = Field(default=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
