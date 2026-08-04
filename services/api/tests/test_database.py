from pathlib import Path

from app.database import Database
from app.schemas import SessionCreate


def test_session_lifecycle(tmp_path: Path):
    database = Database(tmp_path / "test.db")
    database.initialize()

    created = database.create_session(
        SessionCreate(
            title="测试直播",
            platform="douyin",
            operator_name="测试优化师",
            room_name="直播间A",
        )
    )
    assert created["status"] == "created"

    live = database.set_session_live(created["id"])
    assert live["status"] == "live"
    assert live["started_at"] is not None

    transcript = database.add_transcript(
        created["id"],
        "测试转写",
        0,
        1200,
    )
    assert transcript["text"] == "测试转写"
    assert len(database.list_transcripts(created["id"])) == 1

    ended = database.end_session(created["id"])
    assert ended["status"] == "ended"
    assert ended["ended_at"] is not None

