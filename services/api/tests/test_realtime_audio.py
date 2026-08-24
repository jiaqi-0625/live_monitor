import wave
from pathlib import Path

from fastapi.testclient import TestClient

from app import main as main_module
from app.database import Database


def test_realtime_audio_pipeline(tmp_path: Path, monkeypatch):
    test_database = Database(tmp_path / "test.db")
    monkeypatch.setattr(main_module, "database", test_database)
    monkeypatch.setattr(main_module.settings, "storage_root", tmp_path)
    main_module.active_audio_sessions.clear()
    main_module.audio_session_states.clear()

    with TestClient(main_module.app) as client:
        response = client.post(
            "/api/sessions",
            json={
                "title": "实时音频集成测试",
                "platform": "douyin",
                "operator_name": "测试优化师",
                "room_name": "测试直播间",
                "live_url": "https://live.douyin.com/123456",
            },
        )
        assert response.status_code == 201
        assert response.json()["live_url"] == "https://live.douyin.com/123456"
        session_id = response.json()["id"]

        with client.websocket_connect(f"/ws/monitor/{session_id}") as monitor_socket:
            assert monitor_socket.receive_json()["type"] == "session"
            initial_audio_status = monitor_socket.receive_json()
            assert initial_audio_status == {
                "type": "audio_status",
                "payload": {
                    "active": False,
                    "connected": False,
                    "source": None,
                    "message": "等待链接监听、浏览器扩展或Windows采集助手",
                },
            }

            with client.websocket_connect(f"/ws/audio/{session_id}") as audio_socket:
                session_event = monitor_socket.receive_json()
                assert session_event["type"] == "session"
                assert session_event["payload"]["status"] == "live"

                connected_event = monitor_socket.receive_json()
                assert connected_event["type"] == "audio_status"
                assert connected_event["payload"]["connected"] is True

                audio_socket.send_bytes(b"\x20\x00" * 16000 * 10)
                transcript_event = monitor_socket.receive_json()
                assert transcript_event["type"] == "transcript", transcript_event
                assert "10 秒实时音频" in transcript_event["payload"]["text"]

            disconnected_event = monitor_socket.receive_json()
            assert disconnected_event["type"] == "audio_status"
            assert disconnected_event["payload"]["connected"] is False

        detail = client.get(f"/api/sessions/{session_id}").json()
        assert detail["status"] == "live"
        assert len(detail["transcripts"]) == 1

        audio_path = Path(detail["audio_path"])
        assert audio_path.exists()
        with wave.open(str(audio_path), "rb") as recording:
            assert recording.getnchannels() == 1
            assert recording.getsampwidth() == 2
            assert recording.getframerate() == 16000
            assert recording.getnframes() == 16000 * 10

        audio_response = client.get(f"/api/sessions/{session_id}/audio")
        assert audio_response.status_code == 200
        assert audio_response.headers["content-type"] == "audio/wav"


def test_browser_extension_audio_source(tmp_path: Path, monkeypatch):
    test_database = Database(tmp_path / "extension.db")
    monkeypatch.setattr(main_module, "database", test_database)
    monkeypatch.setattr(main_module.settings, "storage_root", tmp_path)
    main_module.active_audio_sessions.clear()
    main_module.audio_session_states.clear()

    with TestClient(main_module.app) as client:
        created = client.post(
            "/api/sessions",
            json={
                "title": "浏览器扩展测试",
                "platform": "dongchedi",
                "operator_name": "测试优化师",
                "room_name": "测试直播间",
                "live_url": "",
            },
        ).json()

        with client.websocket_connect(
            f"/ws/audio/{created['id']}?source=browser_extension"
        ) as audio_socket:
            status = main_module.get_audio_status(created["id"])
            assert status["source"] == "browser_extension"
            assert "浏览器扩展" in status["message"]
            audio_socket.send_bytes(b"\x00\x00" * 1600)


def test_browser_extension_reports_continuous_silence(tmp_path: Path, monkeypatch):
    test_database = Database(tmp_path / "extension-silence.db")
    monkeypatch.setattr(main_module, "database", test_database)
    monkeypatch.setattr(main_module.settings, "storage_root", tmp_path)
    main_module.active_audio_sessions.clear()
    main_module.audio_session_states.clear()

    with TestClient(main_module.app) as client:
        created = client.post(
            "/api/sessions",
            json={
                "title": "浏览器扩展静音检测",
                "platform": "dongchedi",
                "operator_name": "测试优化师",
                "room_name": "测试直播间",
                "live_url": "",
            },
        ).json()

        with client.websocket_connect(f"/ws/monitor/{created['id']}") as monitor:
            monitor.receive_json()
            monitor.receive_json()
            with client.websocket_connect(
                f"/ws/audio/{created['id']}?source=browser_extension"
            ) as audio_socket:
                monitor.receive_json()
                monitor.receive_json()
                audio_socket.send_bytes(b"\x00\x00" * 16000 * 8)
                warning = monitor.receive_json()
                assert warning["type"] == "audio_status", warning
                assert warning["payload"]["connected"] is True
                assert "连续8秒未检测到声音" in warning["payload"]["message"]

                audio_socket.send_bytes(b"\x20\x00" * 1600)
                resumed = monitor.receive_json()
                assert resumed["type"] == "audio_status"
                assert "声音已恢复" in resumed["payload"]["message"]
