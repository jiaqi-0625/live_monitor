from pathlib import Path

from fastapi.testclient import TestClient

from app import main as main_module
from app.database import Database
from app.live_source import LiveSourceProbe


def test_probe_live_source(tmp_path: Path, monkeypatch):
    test_database = Database(tmp_path / "test.db")
    monkeypatch.setattr(main_module, "database", test_database)
    monkeypatch.setattr(
        main_module,
        "probe_live_source",
        lambda _url, _cookie: LiveSourceProbe(
            status="live",
            message="已从直播页面解析到可用直播流",
            qualities=["full_hd1", "hd1"],
            room_id="123456",
            title="测试直播",
            author="测试主播",
        ),
    )

    with TestClient(main_module.app) as client:
        created = client.post(
            "/api/sessions",
            json={
                "title": "链接抓取测试",
                "platform": "douyin",
                "operator_name": "测试优化师",
                "room_name": "测试直播间",
                "live_url": "https://live.douyin.com/123456",
            },
        )
        session_id = created.json()["id"]

        response = client.post(f"/api/sessions/{session_id}/live-source/probe")

    assert response.status_code == 200
    assert response.json() == {
        "status": "live",
        "message": "已从直播页面解析到可用直播流",
        "qualities": ["full_hd1", "hd1"],
        "room_id": "123456",
        "title": "测试直播",
        "author": "测试主播",
    }


def test_probe_autoengine_replay_is_not_live(monkeypatch):
    from app import live_source

    monkeypatch.setattr(
        live_source,
        "_request_autoengine_json",
        lambda endpoint, room_id, cookie, **kwargs: (
            {"data": {"room_id": room_id, "title": "历史场次"}}
            if endpoint.endswith("/room/info")
            else {"data": {"replay_url": "https://example.com/replay.m3u8"}}
        ),
    )

    result = live_source.probe_live_source(
        "https://www.autoengine.com/jdc/industry/live/screen?room_id=7670485893970529070"
    )

    assert result.status == "offline"
    assert result.room_id == "7670485893970529070"
    assert "已经结束" in result.message


def test_probe_autoengine_live_stream(monkeypatch):
    from app import live_source

    monkeypatch.setattr(
        live_source,
        "_request_autoengine_json",
        lambda endpoint, room_id, cookie, **kwargs: {
            "data": {
                "room_id": room_id,
                "title": "实时直播",
                "stream_url": "https://example.com/live.m3u8",
            }
        },
    )

    result = live_source.probe_live_source(
        "https://www.autoengine.com/jdc/industry/live/screen?room_id=7670485893970529070"
    )

    assert result.status == "live"
    assert result.qualities == ["auto"]
