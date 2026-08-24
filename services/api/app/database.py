import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
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
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    display_name TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'operator',
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_login_at TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_users_status
                ON users(status, role, created_at DESC);

                CREATE TABLE IF NOT EXISTS auth_sessions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    token_hash TEXT NOT NULL UNIQUE,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_auth_sessions_token
                ON auth_sessions(token_hash, expires_at);

                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    operator_name TEXT NOT NULL,
                    room_name TEXT NOT NULL DEFAULT '',
                    live_url TEXT NOT NULL DEFAULT '',
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

                CREATE TABLE IF NOT EXISTS metric_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    endpoint TEXT NOT NULL,
                    page_url TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL,
                    normalized_json TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(id)
                );

                CREATE INDEX IF NOT EXISTS idx_metrics_session
                ON metric_snapshots(session_id, id DESC);

                CREATE TABLE IF NOT EXISTS ai_insights (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    risk_level TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    signals_json TEXT NOT NULL,
                    actions_json TEXT NOT NULL,
                    talk_track TEXT NOT NULL,
                    model TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(id)
                );

                CREATE INDEX IF NOT EXISTS idx_ai_insights_session
                ON ai_insights(session_id, id DESC);

                CREATE TABLE IF NOT EXISTS session_reviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL,
                    summary TEXT NOT NULL DEFAULT '',
                    metric_summary TEXT NOT NULL DEFAULT '',
                    highlights_json TEXT NOT NULL DEFAULT '[]',
                    issues_json TEXT NOT NULL DEFAULT '[]',
                    actions_json TEXT NOT NULL DEFAULT '[]',
                    key_metrics_json TEXT NOT NULL DEFAULT '{}',
                    model TEXT NOT NULL DEFAULT '',
                    error TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(id)
                );

                CREATE INDEX IF NOT EXISTS idx_session_reviews_session
                ON session_reviews(session_id);

                CREATE TABLE IF NOT EXISTS corpus_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    operator_name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    source_name TEXT,
                    source_type TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_corpus_operator
                ON corpus_entries(operator_name, enabled, id DESC);

                CREATE TABLE IF NOT EXISTS ai_configs (
                    purpose TEXT PRIMARY KEY,
                    api_base TEXT NOT NULL,
                    api_key_encrypted TEXT NOT NULL DEFAULT '',
                    model TEXT NOT NULL,
                    updated_by TEXT,
                    updated_at TEXT NOT NULL
                );
                """
            )
            session_columns = {
                row["name"] for row in conn.execute("PRAGMA table_info(sessions)").fetchall()
            }
            if "live_url" not in session_columns:
                conn.execute("ALTER TABLE sessions ADD COLUMN live_url TEXT NOT NULL DEFAULT ''")
            if "owner_user_id" not in session_columns:
                conn.execute("ALTER TABLE sessions ADD COLUMN owner_user_id TEXT")
            corpus_columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(corpus_entries)").fetchall()
            }
            if "owner_user_id" not in corpus_columns:
                conn.execute("ALTER TABLE corpus_entries ADD COLUMN owner_user_id TEXT")
            if "source_name" not in corpus_columns:
                conn.execute("ALTER TABLE corpus_entries ADD COLUMN source_name TEXT")
            if "source_type" not in corpus_columns:
                conn.execute("ALTER TABLE corpus_entries ADD COLUMN source_type TEXT")

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def create_session(
        self,
        payload: SessionCreate,
        *,
        owner_user_id: str | None = None,
        operator_name: str | None = None,
    ) -> dict:
        session_id = str(uuid4())
        now = utc_now()
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO sessions (
                    id, title, platform, operator_name, room_name, live_url,
                    status, created_at, owner_user_id
                ) VALUES (?, ?, ?, ?, ?, ?, 'created', ?, ?)
                """,
                (
                    session_id,
                    payload.title,
                    payload.platform,
                    operator_name or payload.operator_name,
                    payload.room_name,
                    payload.live_url,
                    now,
                    owner_user_id,
                ),
            )
        return self.get_session(session_id)

    def list_sessions(self, owner_user_id: str | None = None) -> list[dict]:
        where_clause = "WHERE s.owner_user_id = ?" if owner_user_id else ""
        parameters: tuple[object, ...] = (owner_user_id,) if owner_user_id else ()
        with self.connection() as conn:
            rows = conn.execute(
                f"""
                SELECT s.*,
                    (SELECT COUNT(*) FROM transcripts t WHERE t.session_id = s.id)
                    AS transcript_count
                FROM sessions s
                {where_clause}
                ORDER BY s.created_at DESC
                """,  # noqa: S608
                parameters,
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

    def reset_session_for_retry(self, session_id: str) -> dict | None:
        with self.connection() as conn:
            conn.execute(
                """
                UPDATE sessions
                SET status = 'created',
                    started_at = NULL,
                    ended_at = NULL,
                    audio_path = NULL
                WHERE id = ?
                """,
                (session_id,),
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

    def add_metric_snapshot(
        self,
        session_id: str,
        endpoint: str,
        page_url: str,
        payload: dict,
        normalized: dict[str, float],
        captured_at: str | None = None,
    ) -> dict:
        created_at = utc_now()
        captured_at = captured_at or created_at
        with self.connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO metric_snapshots (
                    session_id, endpoint, page_url, payload_json,
                    normalized_json, captured_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    endpoint,
                    page_url,
                    json.dumps(payload, ensure_ascii=False),
                    json.dumps(normalized, ensure_ascii=False),
                    captured_at,
                    created_at,
                ),
            )
            snapshot_id = cursor.lastrowid
        return {
            "id": snapshot_id,
            "session_id": session_id,
            "endpoint": endpoint,
            "normalized": normalized,
            "captured_at": captured_at,
            "created_at": created_at,
        }

    def latest_metrics(self, session_id: str, limit: int = 30) -> list[dict]:
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM metric_snapshots
                WHERE session_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "session_id": row["session_id"],
                "endpoint": row["endpoint"],
                "payload": json.loads(row["payload_json"]),
                "normalized": json.loads(row["normalized_json"]),
                "captured_at": row["captured_at"],
                "created_at": row["created_at"],
            }
            for row in reversed(rows)
        ]

    def add_ai_insight(
        self,
        session_id: str,
        *,
        risk_level: str,
        summary: str,
        signals: list[str],
        actions: list[str],
        talk_track: str,
        model: str,
    ) -> dict:
        created_at = utc_now()
        with self.connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO ai_insights (
                    session_id, risk_level, summary, signals_json,
                    actions_json, talk_track, model, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    risk_level,
                    summary,
                    json.dumps(signals, ensure_ascii=False),
                    json.dumps(actions, ensure_ascii=False),
                    talk_track,
                    model,
                    created_at,
                ),
            )
            insight_id = cursor.lastrowid
        return {
            "id": insight_id,
            "session_id": session_id,
            "risk_level": risk_level,
            "summary": summary,
            "signals": signals,
            "actions": actions,
            "talk_track": talk_track,
            "model": model,
            "created_at": created_at,
        }

    def latest_ai_insight(self, session_id: str) -> dict | None:
        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM ai_insights
                WHERE session_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "session_id": row["session_id"],
            "risk_level": row["risk_level"],
            "summary": row["summary"],
            "signals": json.loads(row["signals_json"]),
            "actions": json.loads(row["actions_json"]),
            "talk_track": row["talk_track"],
            "model": row["model"],
            "created_at": row["created_at"],
        }

    def upsert_session_review(
        self,
        session_id: str,
        *,
        status: str,
        summary: str = "",
        metric_summary: str = "",
        highlights: list[str] | None = None,
        issues: list[str] | None = None,
        actions: list[str] | None = None,
        key_metrics: dict[str, float] | None = None,
        model: str = "",
        error: str = "",
    ) -> dict:
        now = utc_now()
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO session_reviews (
                    session_id, status, summary, metric_summary,
                    highlights_json, issues_json, actions_json,
                    key_metrics_json, model, error, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    status = excluded.status,
                    summary = excluded.summary,
                    metric_summary = excluded.metric_summary,
                    highlights_json = excluded.highlights_json,
                    issues_json = excluded.issues_json,
                    actions_json = excluded.actions_json,
                    key_metrics_json = excluded.key_metrics_json,
                    model = excluded.model,
                    error = excluded.error,
                    updated_at = excluded.updated_at
                """,
                (
                    session_id,
                    status,
                    summary,
                    metric_summary,
                    json.dumps(highlights or [], ensure_ascii=False),
                    json.dumps(issues or [], ensure_ascii=False),
                    json.dumps(actions or [], ensure_ascii=False),
                    json.dumps(key_metrics or {}, ensure_ascii=False),
                    model,
                    error,
                    now,
                    now,
                ),
            )
        review = self.get_session_review(session_id)
        if review is None:
            raise RuntimeError("复盘记录保存失败")
        return review

    def get_session_review(self, session_id: str) -> dict | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM session_reviews WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "session_id": row["session_id"],
            "status": row["status"],
            "summary": row["summary"],
            "metric_summary": row["metric_summary"],
            "highlights": json.loads(row["highlights_json"]),
            "issues": json.loads(row["issues_json"]),
            "actions": json.loads(row["actions_json"]),
            "key_metrics": json.loads(row["key_metrics_json"]),
            "model": row["model"],
            "error": row["error"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def list_corpus_entries(
        self,
        operator_name: str,
        *,
        enabled_only: bool = False,
        owner_user_id: str | None = None,
    ) -> list[dict]:
        if owner_user_id:
            query = "SELECT * FROM corpus_entries WHERE owner_user_id = ?"
            parameters: list[object] = [owner_user_id]
        else:
            query = "SELECT * FROM corpus_entries WHERE operator_name = ?"
            parameters = [operator_name]
        if enabled_only:
            query += " AND enabled = 1"
        query += " ORDER BY id DESC"
        with self.connection() as conn:
            rows = conn.execute(query, parameters).fetchall()
        return [self._corpus_row(row) for row in rows]

    def add_corpus_entry(
        self,
        *,
        operator_name: str,
        category: str,
        title: str,
        content: str,
        enabled: bool = True,
        owner_user_id: str | None = None,
        source_name: str | None = None,
        source_type: str | None = None,
    ) -> dict:
        now = utc_now()
        with self.connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO corpus_entries (
                    operator_name, category, title, content,
                    enabled, created_at, updated_at, owner_user_id,
                    source_name, source_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    operator_name,
                    category,
                    title,
                    content,
                    int(enabled),
                    now,
                    now,
                    owner_user_id,
                    source_name,
                    source_type,
                ),
            )
            entry_id = cursor.lastrowid
        entry = self.get_corpus_entry(int(entry_id))
        if entry is None:
            raise RuntimeError("语料保存失败")
        return entry

    def get_corpus_entry(self, entry_id: int) -> dict | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM corpus_entries WHERE id = ?",
                (entry_id,),
            ).fetchone()
        return self._corpus_row(row) if row else None

    def update_corpus_entry(
        self,
        entry_id: int,
        operator_name: str,
        updates: dict,
        *,
        owner_user_id: str | None = None,
    ) -> dict | None:
        current = self.get_corpus_entry(entry_id)
        if not current or (
            owner_user_id is not None
            and current.get("owner_user_id") != owner_user_id
        ) or (
            owner_user_id is None
            and current["operator_name"] != operator_name
        ):
            return None
        allowed = {"category", "title", "content", "enabled"}
        values = {key: value for key, value in updates.items() if key in allowed}
        if not values:
            return current
        values["updated_at"] = utc_now()
        assignments = ", ".join(f"{key} = ?" for key in values)
        parameters = [int(value) if key == "enabled" else value for key, value in values.items()]
        parameters.append(entry_id)
        with self.connection() as conn:
            conn.execute(
                f"UPDATE corpus_entries SET {assignments} WHERE id = ?",  # noqa: S608
                parameters,
            )
        return self.get_corpus_entry(entry_id)

    def delete_corpus_entry(
        self,
        entry_id: int,
        operator_name: str,
        *,
        owner_user_id: str | None = None,
    ) -> bool:
        field = "owner_user_id" if owner_user_id is not None else "operator_name"
        owner = owner_user_id if owner_user_id is not None else operator_name
        with self.connection() as conn:
            cursor = conn.execute(
                f"DELETE FROM corpus_entries WHERE id = ? AND {field} = ?",  # noqa: S608
                (entry_id, owner),
            )
        return cursor.rowcount > 0

    @staticmethod
    def _corpus_row(row: sqlite3.Row) -> dict:
        data = dict(row)
        data["enabled"] = bool(data["enabled"])
        return data

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

    def get_ai_config(self, purpose: str) -> dict | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM ai_configs WHERE purpose = ?",
                (purpose,),
            ).fetchone()
        return dict(row) if row else None

    def upsert_ai_config(
        self,
        *,
        purpose: str,
        api_base: str,
        api_key_encrypted: str,
        model: str,
        updated_by: str,
    ) -> dict:
        now = utc_now()
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO ai_configs (
                    purpose, api_base, api_key_encrypted, model,
                    updated_by, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(purpose) DO UPDATE SET
                    api_base = excluded.api_base,
                    api_key_encrypted = excluded.api_key_encrypted,
                    model = excluded.model,
                    updated_by = excluded.updated_by,
                    updated_at = excluded.updated_at
                """,
                (
                    purpose,
                    api_base,
                    api_key_encrypted,
                    model,
                    updated_by,
                    now,
                ),
            )
        result = self.get_ai_config(purpose)
        if result is None:
            raise RuntimeError("AI 配置保存失败")
        return result

    def delete_ai_config(self, purpose: str) -> bool:
        with self.connection() as conn:
            cursor = conn.execute("DELETE FROM ai_configs WHERE purpose = ?", (purpose,))
        return cursor.rowcount > 0

    def create_user(
        self,
        *,
        username: str,
        display_name: str,
        password_hash: str,
        role: str = "operator",
        status: str = "pending",
    ) -> dict:
        user_id = str(uuid4())
        now = utc_now()
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO users (
                    id, username, display_name, password_hash,
                    role, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    username.strip().lower(),
                    display_name.strip(),
                    password_hash,
                    role,
                    status,
                    now,
                    now,
                ),
            )
        user = self.get_user(user_id)
        if user is None:
            raise RuntimeError("用户创建失败")
        return user

    def ensure_admin_user(
        self,
        *,
        username: str,
        display_name: str,
        password_hash: str,
    ) -> dict:
        existing = self.get_user_by_username(username)
        if existing:
            if existing["role"] != "admin" or existing["status"] != "active":
                self.update_user(existing["id"], {"role": "admin", "status": "active"})
            return self.get_user(existing["id"]) or existing
        return self.create_user(
            username=username,
            display_name=display_name,
            password_hash=password_hash,
            role="admin",
            status="active",
        )

    def get_user(self, user_id: str) -> dict | None:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return self._user_row(row) if row else None

    def get_user_by_username(self, username: str) -> dict | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE username = ? COLLATE NOCASE",
                (username.strip(),),
            ).fetchone()
        return self._user_row(row) if row else None

    def list_users(self) -> list[dict]:
        with self.connection() as conn:
            rows = conn.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
        return [self._user_row(row) for row in rows]

    def update_user(self, user_id: str, updates: dict) -> dict | None:
        allowed = {"display_name", "role", "status", "last_login_at", "password_hash"}
        values = {key: value for key, value in updates.items() if key in allowed}
        if not values:
            return self.get_user(user_id)
        values["updated_at"] = utc_now()
        assignments = ", ".join(f"{key} = ?" for key in values)
        with self.connection() as conn:
            cursor = conn.execute(
                f"UPDATE users SET {assignments} WHERE id = ?",  # noqa: S608
                [*values.values(), user_id],
            )
        return self.get_user(user_id) if cursor.rowcount else None

    def count_active_admins(self) -> int:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS count FROM users WHERE role = 'admin' AND status = 'active'"
            ).fetchone()
        return int(row["count"])

    def create_auth_session(
        self,
        *,
        user_id: str,
        token_hash: str,
        duration_days: int,
    ) -> None:
        now = datetime.now(UTC)
        with self.connection() as conn:
            conn.execute("DELETE FROM auth_sessions WHERE expires_at <= ?", (now.isoformat(),))
            conn.execute(
                """
                INSERT INTO auth_sessions (
                    id, user_id, token_hash, expires_at, created_at, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    user_id,
                    token_hash,
                    (now + timedelta(days=duration_days)).isoformat(),
                    now.isoformat(),
                    now.isoformat(),
                ),
            )

    def get_user_by_session(self, token_hash: str) -> dict | None:
        now = utc_now()
        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT u.* FROM auth_sessions a
                JOIN users u ON u.id = a.user_id
                WHERE a.token_hash = ? AND a.expires_at > ?
                """,
                (token_hash, now),
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE auth_sessions SET last_seen_at = ? WHERE token_hash = ?",
                    (now, token_hash),
                )
        return self._user_row(row) if row else None

    def delete_auth_session(self, token_hash: str) -> None:
        with self.connection() as conn:
            conn.execute("DELETE FROM auth_sessions WHERE token_hash = ?", (token_hash,))

    @staticmethod
    def _user_row(row: sqlite3.Row) -> dict:
        return dict(row)
