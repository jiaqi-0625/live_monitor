import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from .schemas import SessionCreate


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class Database:
    def __init__(self, path: Path):
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    operator_name TEXT NOT NULL,
                    room_name TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    ended_at TEXT,
                    audio_path TEXT
                );

                CREATE TABLE IF NOT EXISTS transcripts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    text TEXT NOT NULL,
                    start_ms INTEGER NOT NULL,
                    end_ms INTEGER NOT NULL,
                    is_final INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(id)
                );

                CREATE INDEX IF NOT EXISTS idx_transcripts_session
                ON transcripts(session_id, start_ms);
                """
            )

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def create_session(self, payload: SessionCreate) -> dict:
        session_id = str(uuid4())
        now = utc_now()
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO sessions (
                    id, title, platform, operator_name, room_name, status, created_at
                ) VALUES (?, ?, ?, ?, ?, 'created', ?)
                """,
                (
                    session_id,
                    payload.title,
                    payload.platform,
                    payload.operator_name,
                    payload.room_name,
                    now,
                ),
            )
        return self.get_session(session_id)

    def list_sessions(self) -> list[dict]:
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT s.*,
                    (SELECT COUNT(*) FROM transcripts t WHERE t.session_id = s.id)
                    AS transcript_count
                FROM sessions s
                ORDER BY s.created_at DESC
                """
            ).fetchall()
        return [self._session_row(row) for row in rows]

    def get_session(self, session_id: str) -> dict | None:
        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT s.*,
                    (SELECT COUNT(*) FROM transcripts t WHERE t.session_id = s.id)
                    AS transcript_count
                FROM sessions s
                WHERE s.id = ?
                """,
                (session_id,),
            ).fetchone()
        return self._session_row(row) if row else None

    def set_session_live(self, session_id: str) -> dict | None:
        with self.connection() as conn:
            conn.execute(
                """
                UPDATE sessions
                SET status = 'live', started_at = COALESCE(started_at, ?), ended_at = NULL
                WHERE id = ?
                """,
                (utc_now(), session_id),
            )
        return self.get_session(session_id)

    def end_session(self, session_id: str, failed: bool = False) -> dict | None:
        status = "failed" if failed else "ended"
        with self.connection() as conn:
            conn.execute(
                "UPDATE sessions SET status = ?, ended_at = ? WHERE id = ?",
                (status, utc_now(), session_id),
            )
        return self.get_session(session_id)

    def set_audio_path(self, session_id: str, audio_path: str) -> None:
        with self.connection() as conn:
            conn.execute(
                "UPDATE sessions SET audio_path = ? WHERE id = ?",
                (audio_path, session_id),
            )

    def add_transcript(
        self,
        session_id: str,
        text: str,
        start_ms: int,
        end_ms: int,
        is_final: bool = True,
    ) -> dict:
        now = utc_now()
        with self.connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO transcripts (
                    session_id, text, start_ms, end_ms, is_final, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (session_id, text, start_ms, end_ms, int(is_final), now),
            )
            transcript_id = cursor.lastrowid
        return {
            "id": transcript_id,
            "session_id": session_id,
            "text": text,
            "start_ms": start_ms,
            "end_ms": end_ms,
            "is_final": is_final,
            "created_at": now,
        }

    def list_transcripts(self, session_id: str) -> list[dict]:
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM transcripts
                WHERE session_id = ?
                ORDER BY start_ms, id
                """,
                (session_id,),
            ).fetchall()
        return [
            {
                **dict(row),
                "is_final": bool(row["is_final"]),
            }
            for row in rows
        ]

    @staticmethod
    def _session_row(row: sqlite3.Row) -> dict:
        data = dict(row)
        started_at = datetime.fromisoformat(data["started_at"]) if data["started_at"] else None
        ended_at = datetime.fromisoformat(data["ended_at"]) if data["ended_at"] else None
        if started_at:
            end = ended_at or datetime.now(UTC)
            duration = max(0, int((end - started_at).total_seconds()))
        else:
            duration = 0
        data["duration_seconds"] = duration
        data["transcript_count"] = int(data.get("transcript_count", 0))
        return data

