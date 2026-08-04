from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Platform = Literal["douyin", "dongchedi"]
SessionStatus = Literal["created", "live", "ended", "failed"]


class SessionCreate(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    platform: Platform
    operator_name: str = Field(min_length=1, max_length=40)
    room_name: str = Field(default="", max_length=80)


class SessionSummary(BaseModel):
    id: str
    title: str
    platform: Platform
    operator_name: str
    room_name: str
    status: SessionStatus
    created_at: datetime
    started_at: datetime | None = None
    ended_at: datetime | None = None
    duration_seconds: int
    audio_path: str | None = None
    transcript_count: int = 0


class TranscriptItem(BaseModel):
    id: int
    session_id: str
    text: str
    start_ms: int
    end_ms: int
    is_final: bool
    created_at: datetime


class SessionDetail(SessionSummary):
    transcripts: list[TranscriptItem]


class MonitorEvent(BaseModel):
    type: Literal[
        "session",
        "audio_status",
        "transcript",
        "warning",
        "heartbeat",
    ]
    payload: dict

