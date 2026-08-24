from datetime import datetime
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator

Platform = Literal["douyin", "dongchedi"]
SessionStatus = Literal["created", "live", "ended", "failed"]
ReviewStatus = Literal["pending", "completed", "failed"]
UserRole = Literal["admin", "operator"]
UserStatus = Literal["pending", "active", "disabled"]


class RegisterInput(BaseModel):
    username: str = Field(
        min_length=2,
        max_length=40,
        pattern=r"^[A-Za-z0-9_.\-\u4e00-\u9fff]+$",
    )
    display_name: str = Field(min_length=1, max_length=40)
    password: str = Field(min_length=8, max_length=128)


class LoginInput(BaseModel):
    username: str = Field(min_length=1, max_length=40)
    password: str = Field(min_length=1, max_length=128)


class UserProfile(BaseModel):
    id: str
    username: str
    display_name: str
    role: UserRole
    status: UserStatus
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None = None


class UserAdminUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=40)
    role: UserRole | None = None
    status: UserStatus | None = None


class AiConfigUpdate(BaseModel):
    api_base: str = Field(min_length=1, max_length=500)
    api_key: str | None = Field(default=None, max_length=500)
    model: str = Field(min_length=1, max_length=200)

    @field_validator("api_base")
    @classmethod
    def validate_api_base(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        parsed = urlparse(value)
        if parsed.scheme != "https" or parsed.hostname != "api.deepseek.com":
            raise ValueError("当前仅支持 DeepSeek 官方 API 地址")
        return value


class AiConfigProbe(BaseModel):
    api_base: str = Field(min_length=1, max_length=500)
    api_key: str | None = Field(default=None, max_length=500)
    model: str | None = Field(default=None, max_length=200)

    @field_validator("api_base")
    @classmethod
    def validate_api_base(cls, value: str) -> str:
        return AiConfigUpdate.validate_api_base(value)


class AiConfigView(BaseModel):
    purpose: Literal["realtime", "corpus"]
    api_base: str
    model: str
    configured: bool
    has_api_key: bool
    source: Literal["admin", "environment"]
    updated_at: datetime | None = None


class AiModelsResult(BaseModel):
    models: list[str] = Field(default_factory=list)


class AiConfigTestResult(BaseModel):
    success: bool
    message: str


class SessionCreate(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    platform: Platform
    operator_name: str = Field(min_length=1, max_length=40)
    room_name: str = Field(default="", max_length=80)
    live_url: str = Field(default="", max_length=500)

    @field_validator("live_url")
    @classmethod
    def validate_live_url(cls, value: str) -> str:
        value = value.strip()
        if not value:
            return ""
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("直播间链接必须是完整的HTTP或HTTPS地址")
        return value


class SessionSummary(BaseModel):
    id: str
    title: str
    platform: Platform
    operator_name: str
    room_name: str
    live_url: str
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


class LiveSourceProbeResult(BaseModel):
    status: Literal["live", "offline", "unsupported", "error"]
    message: str
    qualities: list[str] = Field(default_factory=list)
    room_id: str | None = None
    title: str | None = None
    author: str | None = None


class AudioSourceStatus(BaseModel):
    active: bool
    connected: bool
    source: Literal["windows", "browser_extension", "live_url"] | None = None
    message: str


class MetricCapture(BaseModel):
    endpoint: str = Field(min_length=1, max_length=300)
    page_url: str = Field(default="", max_length=1000)
    payload: dict
    captured_at: datetime | None = None


class MetricSnapshot(BaseModel):
    id: int
    session_id: str
    endpoint: str
    normalized: dict[str, float]
    captured_at: datetime
    created_at: datetime


class AiInsight(BaseModel):
    id: int
    session_id: str
    risk_level: Literal["normal", "attention", "critical"]
    summary: str
    signals: list[str]
    actions: list[str]
    talk_track: str
    model: str
    created_at: datetime


class LiveDashboard(BaseModel):
    latest_metrics: dict[str, float] = Field(default_factory=dict)
    latest_metric_at: datetime | None = None
    latest_insight: AiInsight | None = None


class LiveRoomOverview(BaseModel):
    session: SessionSummary
    dashboard: LiveDashboard


class MultiRoomOverview(BaseModel):
    rooms: list[LiveRoomOverview] = Field(default_factory=list)
    updated_at: datetime


class SessionReview(BaseModel):
    id: int
    session_id: str
    status: ReviewStatus
    summary: str
    metric_summary: str
    highlights: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    key_metrics: dict[str, float] = Field(default_factory=dict)
    model: str
    error: str
    created_at: datetime
    updated_at: datetime


class ReviewGenerationStatus(BaseModel):
    status: ReviewStatus


class CorpusEntryCreate(BaseModel):
    operator_name: str = Field(min_length=1, max_length=40)
    category: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1, max_length=12000)
    enabled: bool = True


class CorpusEntryUpdate(BaseModel):
    operator_name: str = Field(min_length=1, max_length=40)
    category: str | None = Field(default=None, min_length=1, max_length=40)
    title: str | None = Field(default=None, min_length=1, max_length=100)
    content: str | None = Field(default=None, min_length=1, max_length=12000)
    enabled: bool | None = None


class CorpusEntry(BaseModel):
    id: int
    operator_name: str
    category: str
    title: str
    content: str
    enabled: bool
    source_name: str | None = None
    source_type: str | None = None
    created_at: datetime
    updated_at: datetime


class CorpusImportFailure(BaseModel):
    filename: str
    error: str


class CorpusImportResult(BaseModel):
    imported_files: int
    imported_entries: int
    original_chars: int = 0
    saved_chars: int = 0
    fallback_files: list[str] = Field(default_factory=list)
    entries: list[CorpusEntry] = Field(default_factory=list)
    failures: list[CorpusImportFailure] = Field(default_factory=list)


class MonitorEvent(BaseModel):
    type: Literal[
        "session",
        "audio_status",
        "transcript",
        "metrics",
        "ai_insight",
        "warning",
        "heartbeat",
    ]
    payload: dict
