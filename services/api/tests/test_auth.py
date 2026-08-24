from pathlib import Path

from fastapi.testclient import TestClient

from app import main as main_module
from app.ai_config import ApiKeyCipher, resolve_ai_config
from app.auth import hash_password
from app.database import Database
from app.schemas import SessionCreate


def test_registration_approval_login_and_user_isolation(
    tmp_path: Path,
    monkeypatch,
):
    test_database = Database(tmp_path / "auth.db")
    monkeypatch.setattr(main_module, "database", test_database)
    monkeypatch.setattr(main_module.settings, "auth_required", True)
    test_database.initialize()
    admin = test_database.create_user(
        username="admin",
        display_name="系统管理员",
        password_hash=hash_password("Admin123456"),
        role="admin",
        status="active",
    )

    with (
        TestClient(main_module.app) as admin_client,
        TestClient(main_module.app) as first_client,
        TestClient(main_module.app) as second_client,
    ):
        first_registration = first_client.post(
            "/api/auth/register",
            json={
                "username": "operator_one",
                "display_name": "优化师甲",
                "password": "Password123",
            },
        )
        second_registration = second_client.post(
            "/api/auth/register",
            json={
                "username": "operator_two",
                "display_name": "优化师乙",
                "password": "Password456",
            },
        )
        assert first_registration.status_code == 201
        assert first_registration.json()["status"] == "pending"
        assert second_registration.status_code == 201
        assert first_client.post(
            "/api/auth/login",
            json={"username": "operator_one", "password": "Password123"},
        ).status_code == 403

        admin_login = admin_client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "Admin123456"},
        )
        assert admin_login.status_code == 200
        assert admin_login.cookies.get("live_monitor_session")

        for registration in (first_registration, second_registration):
            activated = admin_client.patch(
                f"/api/admin/users/{registration.json()['id']}",
                json={"status": "active"},
            )
            assert activated.status_code == 200

        assert first_client.post(
            "/api/auth/login",
            json={"username": "operator_one", "password": "Password123"},
        ).status_code == 200
        assert second_client.post(
            "/api/auth/login",
            json={"username": "operator_two", "password": "Password456"},
        ).status_code == 200

        first_session = first_client.post(
            "/api/sessions",
            json={
                "title": "甲的直播",
                "platform": "douyin",
                "operator_name": "伪造的名称",
                "room_name": "直播间甲",
                "live_url": "",
            },
        )
        second_session = second_client.post(
            "/api/sessions",
            json={
                "title": "乙的直播",
                "platform": "dongchedi",
                "operator_name": "伪造的名称",
                "room_name": "直播间乙",
                "live_url": "",
            },
        )
        assert first_session.json()["operator_name"] == "优化师甲"
        assert second_session.status_code == 201
        assert [item["id"] for item in first_client.get("/api/sessions").json()] == [
            first_session.json()["id"]
        ]
        assert first_client.get(
            f"/api/sessions/{second_session.json()['id']}"
        ).status_code == 404
        assert len(admin_client.get("/api/sessions").json()) == 2

        disabled = admin_client.patch(
            f"/api/admin/users/{first_registration.json()['id']}",
            json={"status": "disabled"},
        )
        assert disabled.status_code == 200
        assert first_client.get("/api/auth/me").status_code == 403

        last_admin_change = admin_client.patch(
            f"/api/admin/users/{admin['id']}",
            json={"role": "operator"},
        )
        assert last_admin_change.status_code == 409


def test_duplicate_registration_and_unauthenticated_access(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(main_module, "database", Database(tmp_path / "auth-errors.db"))
    monkeypatch.setattr(main_module.settings, "auth_required", True)

    with TestClient(main_module.app) as client:
        payload = {
            "username": "new_user",
            "display_name": "新用户",
            "password": "Password123",
        }
        assert client.post("/api/auth/register", json=payload).status_code == 201
        assert client.post("/api/auth/register", json=payload).status_code == 409
        assert client.get("/api/sessions").status_code == 401
        assert client.get("/api/health").status_code == 200


def test_registration_accepts_chinese_username(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(main_module, "database", Database(tmp_path / "chinese-user.db"))
    monkeypatch.setattr(main_module.settings, "auth_required", True)

    with TestClient(main_module.app) as client:
        response = client.post(
            "/api/auth/register",
            json={
                "username": "优化师小李",
                "display_name": "优化师小李",
                "password": "Password123",
            },
        )

    assert response.status_code == 201
    assert response.json()["username"] == "优化师小李"
    assert response.json()["status"] == "pending"


def test_registration_accepts_numeric_password_and_returns_readable_errors(
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.setattr(main_module, "database", Database(tmp_path / "validation.db"))
    monkeypatch.setattr(main_module.settings, "auth_required", True)

    with TestClient(main_module.app) as client:
        accepted = client.post(
            "/api/auth/register",
            json={
                "username": "优化师王五",
                "display_name": "优化师王五",
                "password": "12345678",
            },
        )
        rejected = client.post(
            "/api/auth/register",
            json={
                "username": "优化师赵六",
                "display_name": "优化师赵六",
                "password": "123456",
            },
        )

    assert accepted.status_code == 201
    assert rejected.status_code == 422
    assert rejected.json() == {"detail": "密码至少需要 8 个字符"}


def test_admin_ai_config_is_global_encrypted_and_admin_only(tmp_path: Path, monkeypatch):
    test_database = Database(tmp_path / "ai-config.db")
    monkeypatch.setattr(main_module, "database", test_database)
    monkeypatch.setattr(main_module.settings, "auth_required", True)
    monkeypatch.setattr(main_module.settings, "storage_root", tmp_path)
    test_database.initialize()
    test_database.create_user(
        username="admin",
        display_name="系统管理员",
        password_hash=hash_password("Admin123456"),
        role="admin",
        status="active",
    )
    test_database.create_user(
        username="operator",
        display_name="优化师",
        password_hash=hash_password("Operator123"),
        status="active",
    )

    with TestClient(main_module.app) as admin_client, TestClient(main_module.app) as user_client:
        assert admin_client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "Admin123456"},
        ).status_code == 200
        assert user_client.post(
            "/api/auth/login",
            json={"username": "operator", "password": "Operator123"},
        ).status_code == 200
        saved = admin_client.put(
            "/api/admin/ai-configs/realtime",
            json={
                "api_base": "https://api.deepseek.com",
                "api_key": "sk-global-secret",
                "model": "deepseek-chat",
            },
        )
        listed = admin_client.get("/api/admin/ai-configs")
        forbidden = user_client.get("/api/admin/ai-configs")

    assert saved.status_code == 200
    assert saved.json()["has_api_key"] is True
    assert "sk-global-secret" not in saved.text
    assert "sk-global-secret" not in listed.text
    assert forbidden.status_code == 403
    stored = test_database.get_ai_config("realtime")
    assert stored is not None
    assert stored["api_key_encrypted"] != "sk-global-secret"
    assert ApiKeyCipher(main_module.settings).decrypt(stored["api_key_encrypted"]) == (
        "sk-global-secret"
    )
    assert resolve_ai_config(test_database, main_module.settings, "realtime").model == (
        "deepseek-chat"
    )


def test_extension_capture_channels_remain_compatible_with_auth(
    tmp_path: Path,
    monkeypatch,
):
    test_database = Database(tmp_path / "extension-auth.db")
    monkeypatch.setattr(main_module, "database", test_database)
    monkeypatch.setattr(main_module.settings, "storage_root", tmp_path)
    monkeypatch.setattr(main_module.settings, "auth_required", True)
    main_module.active_audio_sessions.clear()
    main_module.audio_session_states.clear()
    test_database.initialize()
    session = test_database.create_session(
        SessionCreate(
            title="扩展兼容测试",
            platform="dongchedi",
            operator_name="测试优化师",
            room_name="测试直播间",
            live_url="",
        ),
        owner_user_id="owner-id",
    )

    with TestClient(main_module.app) as client:
        metrics = client.post(
            f"/api/sessions/{session['id']}/metrics",
            json={"endpoint": "/screen/overview/data", "payload": {"online_user_count": 8}},
        )
        assert metrics.status_code == 200

        with client.websocket_connect(
            f"/ws/audio/{session['id']}?source=browser_extension"
        ) as audio_socket:
            assert main_module.get_audio_status(session["id"])["source"] == "browser_extension"
            audio_socket.send_bytes(b"\x00\x00" * 1600)
