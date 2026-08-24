import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

from app import main as main_module
from app.ai_analysis import normalize_metrics
from app.database import Database


def test_normalize_metrics_from_nested_payload():
    payload = {
        "data": {
            "overview": {
                "online_user_count": 79,
                "total_watch_user_count": 1202,
                "interaction_rate": 0.0075,
                "business_opportunity_count": 4,
            }
        }
    }

    assert normalize_metrics(payload) == {
        "online_users": 79.0,
        "cumulative_viewers": 1202.0,
        "interaction_rate": 0.0075,
        "lead_count": 4.0,
    }


def test_normalize_autoengine_data_map():
    values = {
        str(metric_id): f"{metric_id:,}" if metric_id == 9 else f"{metric_id}%"
        for metric_id in range(1, 54)
    }
    payload = {"data": {"data_map": values}}

    assert normalize_metrics(
        payload,
        "https://www.autoengine.com/motor/dealer/jdc_saas/live/screen/overview/data",
    ) == {
        "average_watch_seconds": 1.0,
        "fans_average_watch_seconds": 2.0,
        "lead_count": 3.0,
        "lead_conversion_rate": 4.0,
        "private_message_users": 5.0,
        "private_message_longterm_conversions": 6.0,
        "online_users": 7.0,
        "preview_viewers": 8.0,
        "cumulative_viewers": 9.0,
        "fans_viewer_rate": 10.0,
        "view_count": 11.0,
        "exposure_entry_rate": 12.0,
        "exposure_users": 13.0,
        "fans_exposure_entry_rate": 14.0,
        "peak_online_users": 15.0,
        "average_online_users": 16.0,
        "spend": 17.0,
        "lead_cost": 18.0,
        "windmill_clicks": 19.0,
        "windmill_impressions": 20.0,
        "windmill_click_rate": 21.0,
        "new_followers": 22.0,
        "follower_rate": 23.0,
        "share_rate": 24.0,
        "share_users": 25.0,
        "share_count": 26.0,
        "like_rate": 27.0,
        "like_users": 28.0,
        "like_count": 29.0,
        "comment_rate": 30.0,
        "comment_users": 31.0,
        "comment_count": 32.0,
        "interaction_rate": 33.0,
        "interaction_users": 34.0,
        "interaction_count": 35.0,
        "card_clicks": 36.0,
        "card_impressions": 37.0,
        "card_click_rate": 38.0,
        "windmill_card_click_users": 39.0,
        "exposure_count": 40.0,
        "fans_exposure_share": 41.0,
        "watch_over_one_minute": 42.0,
        "fan_view_count": 43.0,
        "fan_viewers": 44.0,
        "fan_club_joins": 45.0,
        "fan_club_join_rate": 46.0,
        "tip_count": 47.0,
        "form_submits": 48.0,
        "form_users": 49.0,
        "form_cost": 50.0,
        "organic_traffic_rate": 51.0,
        "paid_traffic_rate": 52.0,
        "other_traffic_rate": 53.0,
    }
    assert normalize_metrics(
        payload,
        "https://www.autoengine.com/motor/dealer/jdc_saas/live/screen/trend/data",
    ) == {}


def test_final_transcript_schedules_ai(tmp_path: Path, monkeypatch):
    test_database = Database(tmp_path / "transcript-trigger.db")
    monkeypatch.setattr(main_module, "database", test_database)
    scheduled: list[str] = []
    monkeypatch.setattr(
        main_module,
        "schedule_ai_analysis",
        lambda session_id: scheduled.append(session_id),
    )

    with TestClient(main_module.app) as client:
        session_id = client.post(
            "/api/sessions",
            json={
                "title": "转写触发测试",
                "platform": "dongchedi",
                "operator_name": "测试优化师",
                "room_name": "测试直播间",
                "live_url": "",
            },
        ).json()["id"]
        callback = main_module.create_transcript_callback(session_id)
        asyncio.run(callback("临时结果", 0, 1000, False))
        asyncio.run(callback("最终结果", 0, 1000, True))

    assert scheduled == [session_id]


def test_metric_capture_and_dashboard(tmp_path: Path, monkeypatch):
    test_database = Database(tmp_path / "dashboard.db")
    monkeypatch.setattr(main_module, "database", test_database)
    monkeypatch.setattr(main_module.settings, "llm_api_key", None)
    main_module.ai_analysis_tasks.clear()
    main_module.last_ai_analysis_at.clear()

    with TestClient(main_module.app) as client:
        created = client.post(
            "/api/sessions",
            json={
                "title": "大屏指标测试",
                "platform": "dongchedi",
                "operator_name": "测试优化师",
                "room_name": "测试直播间",
                "live_url": "",
            },
        ).json()
        response = client.post(
            f"/api/sessions/{created['id']}/metrics",
            json={
                "endpoint": "/motor/dealer/jdc_saas/live/screen/overview/data",
                "page_url": "https://www.autoengine.com/jdc/industry/live/screen",
                "payload": {
                    "data": {
                        "online_user_count": 25,
                        "average_watch_duration": 18,
                    }
                },
            },
        )
        assert response.status_code == 200
        assert response.json()["normalized"] == {
            "online_users": 25.0,
            "average_watch_seconds": 18.0,
        }

        dashboard = client.get(
            f"/api/sessions/{created['id']}/dashboard"
        ).json()
        assert dashboard["latest_metrics"]["online_users"] == 25.0
        assert dashboard["latest_insight"] is None


def test_multi_room_overview_is_scoped_to_operator(tmp_path: Path, monkeypatch):
    test_database = Database(tmp_path / "multi-room.db")
    monkeypatch.setattr(main_module, "database", test_database)

    with TestClient(main_module.app) as client:
        first = client.post(
            "/api/sessions",
            json={
                "title": "优化师甲直播间",
                "platform": "dongchedi",
                "operator_name": "优化师甲",
                "room_name": "直播间A",
                "live_url": "",
            },
        ).json()
        client.post(
            "/api/sessions",
            json={
                "title": "优化师乙直播间",
                "platform": "douyin",
                "operator_name": "优化师乙",
                "room_name": "直播间B",
                "live_url": "",
            },
        )
        client.post(
            f"/api/sessions/{first['id']}/metrics",
            json={
                "endpoint": "/screen/overview/data",
                "payload": {"online_user_count": 18},
            },
        )

        overview = client.get(
            "/api/overview",
            params={"operator_name": "优化师甲"},
        )

    assert overview.status_code == 200
    body = overview.json()
    assert len(body["rooms"]) == 1
    assert body["rooms"][0]["session"]["id"] == first["id"]
    assert body["rooms"][0]["dashboard"]["latest_metrics"] == {
        "online_users": 18.0,
    }


def test_manual_end_schedules_session_review(tmp_path: Path, monkeypatch):
    test_database = Database(tmp_path / "review-trigger.db")
    monkeypatch.setattr(main_module, "database", test_database)
    scheduled: list[str] = []
    monkeypatch.setattr(
        main_module,
        "schedule_session_review",
        lambda session_id: scheduled.append(session_id),
    )

    with TestClient(main_module.app) as client:
        created = client.post(
            "/api/sessions",
            json={
                "title": "复盘触发测试",
                "platform": "douyin",
                "operator_name": "测试优化师",
                "room_name": "测试直播间",
                "live_url": "",
            },
        ).json()
        ended = client.post(f"/api/sessions/{created['id']}/end")

    assert ended.status_code == 200
    assert ended.json()["status"] == "ended"
    assert scheduled == [created["id"]]


def test_corpus_api_is_scoped_to_operator(tmp_path: Path, monkeypatch):
    test_database = Database(tmp_path / "corpus.db")
    monkeypatch.setattr(main_module, "database", test_database)

    with TestClient(main_module.app) as client:
        created = client.post(
            "/api/corpus",
            json={
                "operator_name": "优化师甲",
                "category": "script",
                "title": "邀约试驾话术",
                "content": "邀请用户留下联系方式并预约试驾。",
            },
        )
        own_entries = client.get(
            "/api/corpus",
            params={"operator_name": "优化师甲"},
        )
        other_entries = client.get(
            "/api/corpus",
            params={"operator_name": "优化师乙"},
        )

    assert created.status_code == 201
    assert own_entries.json()[0]["title"] == "邀约试驾话术"
    assert other_entries.json() == []
