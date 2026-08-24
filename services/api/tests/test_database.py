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
            live_url="https://live.douyin.com/123456",
        )
    )
    assert created["status"] == "created"
    assert created["live_url"] == "https://live.douyin.com/123456"

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

    pending_review = database.upsert_session_review(
        created["id"],
        status="pending",
        model="test-model",
    )
    assert pending_review["status"] == "pending"

    completed_review = database.upsert_session_review(
        created["id"],
        status="completed",
        summary="整场表现稳定",
        metric_summary="累计观看100人",
        highlights=["开场节奏清晰"],
        issues=["互动引导偏少"],
        actions=["每5分钟增加一次互动"],
        key_metrics={"cumulative_viewers": 100.0},
        model="test-model",
    )
    assert completed_review["summary"] == "整场表现稳定"
    assert completed_review["highlights"] == ["开场节奏清晰"]
    assert completed_review["key_metrics"] == {"cumulative_viewers": 100.0}

    corpus = database.add_corpus_entry(
        operator_name="测试优化师",
        category="vehicle",
        title="测试车型卖点",
        content="全系标配主动安全系统。",
    )
    assert corpus["enabled"] is True
    assert database.list_corpus_entries("其他优化师") == []
    assert database.list_corpus_entries("测试优化师") == [corpus]

    disabled = database.update_corpus_entry(
        corpus["id"],
        "测试优化师",
        {"enabled": False},
    )
    assert disabled is not None
    assert disabled["enabled"] is False
    assert database.list_corpus_entries("测试优化师", enabled_only=True) == []
    assert database.delete_corpus_entry(corpus["id"], "其他优化师") is False
    assert database.delete_corpus_entry(corpus["id"], "测试优化师") is True
