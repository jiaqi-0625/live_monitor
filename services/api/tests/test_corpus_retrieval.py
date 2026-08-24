import asyncio
import json
from pathlib import Path

from pydantic import SecretStr

from app import ai_analysis as ai_analysis_module
from app import main as main_module
from app.ai_analysis import AnalysisResult, ReviewResult
from app.config import Settings
from app.corpus_retrieval import retrieve_corpus_context, tokenize_for_retrieval
from app.database import Database
from app.schemas import SessionCreate


def _entry(
    entry_id: int,
    category: str,
    title: str,
    content: str,
    *,
    enabled: bool = True,
) -> dict:
    return {
        "id": entry_id,
        "operator_name": "优化师甲",
        "category": category,
        "title": title,
        "content": content,
        "enabled": enabled,
    }


def test_chinese_tokenizer_produces_searchable_bigrams():
    tokens = tokenize_for_retrieval("直播间在线人数下降 lead_count")

    assert "在线" in tokens
    assert "人数" in tokens
    assert "lead_count" in tokens


def test_retrieval_keeps_rules_and_ranks_relevant_older_corpus():
    entries = [
        _entry(4, "other", "最新但无关", "展厅每日九点开门。"),
        _entry(3, "vehicle", "车型安全", "车辆配备六安全气囊。"),
        _entry(2, "metric_traffic", "流量层级", "在线人数下降时先加强互动和停留话术。"),
        _entry(1, "constraint", "禁用要求", "禁止承诺最低价，不得虚构优惠。"),
    ]

    hits = retrieve_corpus_context(
        entries,
        session={"title": "测试直播"},
        normalized_metrics={"online_users": 8},
        transcripts=[{"text": "在线人数一直下降怎么办"}],
        mode="realtime",
    )

    ids = [hit["id"] for hit in hits]
    assert 1 in ids
    assert 2 in ids
    assert ids.index(2) < ids.index(3) if 3 in ids else True
    assert next(hit for hit in hits if hit["id"] == 1)["retrieval_reason"].startswith(
        "强制优先"
    )


def test_retrieval_never_returns_disabled_corpus():
    hits = retrieve_corpus_context(
        [
            _entry(1, "constraint", "启用规则", "不得虚构优惠。"),
            _entry(2, "script", "已停用话术", "在线下降时使用这段话术。", enabled=False),
        ],
        session={"title": "测试直播"},
        normalized_metrics={"online_users": 5},
        transcripts=[{"text": "在线下降"}],
        mode="realtime",
    )

    assert [hit["id"] for hit in hits] == [1]


def test_retrieval_respects_prompt_budget():
    hits = retrieve_corpus_context(
        [_entry(1, "constraint", "长规则", "禁止虚构。" * 1000)],
        session={},
        normalized_metrics={},
        transcripts=[],
        mode="review",
        max_chars=600,
    )

    assert hits
    assert sum(len(hit["content"]) for hit in hits) <= 600


class _FakeAiConfig:
    configured = True
    model = "test-model"

    @staticmethod
    def as_settings(settings):
        return settings


def _create_owned_session(database: Database) -> dict:
    return database.create_session(
        SessionCreate(
            title="流量层级测试",
            platform="douyin",
            operator_name="优化师甲",
            room_name="直播间A",
            live_url="",
        ),
        owner_user_id="user-a",
    )


def test_realtime_analysis_uses_retrieved_owner_corpus(
    tmp_path: Path,
    monkeypatch,
):
    database = Database(tmp_path / "realtime-retrieval.db")
    database.initialize()
    session = _create_owned_session(database)
    relevant = database.add_corpus_entry(
        operator_name="优化师甲",
        owner_user_id="user-a",
        category="metric_traffic",
        title="流量诊断",
        content="在线人数下降时加强互动与停留话术。",
    )
    database.add_corpus_entry(
        operator_name="优化师乙",
        owner_user_id="user-b",
        category="script",
        title="其他用户话术",
        content="在线人数下降时使用不属于你的话术。",
    )
    disabled = database.add_corpus_entry(
        operator_name="优化师甲",
        owner_user_id="user-a",
        category="script",
        title="停用话术",
        content="在线人数下降时使用已停用话术。",
        enabled=False,
    )
    database.add_transcript(session["id"], "现在在线人数下降", 0, 1000, True)
    captured: list[dict] = []

    def fake_analysis(settings, payloads, metrics, transcripts, corpus_entries):
        captured.extend(corpus_entries)
        return AnalysisResult(
            risk_level="attention",
            summary="已检索语料",
            signals=[],
            actions=[],
            talk_track="请大家在评论区告诉我最关注的配置。",
            model="test-model",
        )

    monkeypatch.setattr(main_module, "database", database)
    monkeypatch.setattr(main_module, "resolve_ai_config", lambda *args: _FakeAiConfig())
    monkeypatch.setattr(main_module, "analyze_with_llm", fake_analysis)

    asyncio.run(main_module.run_ai_analysis(session["id"]))

    captured_ids = [entry["id"] for entry in captured]
    assert relevant["id"] in captured_ids
    assert disabled["id"] not in captured_ids
    assert all(entry.get("owner_user_id") == "user-a" for entry in captured)


def test_session_review_uses_same_retrieval_tool(tmp_path: Path, monkeypatch):
    database = Database(tmp_path / "review-retrieval.db")
    database.initialize()
    session = _create_owned_session(database)
    script = database.add_corpus_entry(
        operator_name="优化师甲",
        owner_user_id="user-a",
        category="script",
        title="标准留资话术",
        content="邀请用户留下联系方式并预约试驾。",
    )
    database.add_transcript(session["id"], "欢迎大家预约试驾", 0, 1000, True)
    captured: list[dict] = []

    def fake_review(settings, session, metrics, transcripts, corpus_entries):
        captured.extend(corpus_entries)
        return ReviewResult(
            summary="已按语料复盘",
            metric_summary="",
            highlights=[],
            issues=[],
            actions=[],
            model="test-model",
        )

    monkeypatch.setattr(main_module, "database", database)
    monkeypatch.setattr(main_module, "resolve_ai_config", lambda *args: _FakeAiConfig())
    monkeypatch.setattr(main_module, "analyze_session_review", fake_review)

    asyncio.run(main_module.run_session_review(session["id"]))

    assert [entry["id"] for entry in captured] == [script["id"]]
    assert database.get_session_review(session["id"])["status"] == "completed"


def test_review_prompt_contains_retrieval_evidence(monkeypatch):
    captured_payload = None

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return json.dumps(
                {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "summary": "复盘完成",
                                        "metric_summary": "",
                                        "highlights": [],
                                        "issues": [],
                                        "actions": [],
                                    },
                                    ensure_ascii=False,
                                )
                            }
                        }
                    ]
                },
                ensure_ascii=False,
            ).encode()

    def capture_request(request, **kwargs):
        nonlocal captured_payload
        captured_payload = json.loads(request.data.decode())
        return FakeResponse()

    monkeypatch.setattr(ai_analysis_module, "urlopen", capture_request)
    ai_analysis_module.analyze_session_review(
        Settings(llm_api_key=SecretStr("test-key")),
        {"title": "测试直播"},
        {"online_users": 8},
        [{"text": "欢迎预约试驾", "start_ms": 3000}],
        [
            {
                "id": 7,
                "category": "script",
                "title": "标准留资话术",
                "content": "邀请用户留下联系方式并预约试驾。",
                "retrieval_reason": "强制优先：标准话术",
            }
        ],
    )

    prompt = captured_payload["messages"][1]["content"]
    assert "语料ID=7" in prompt
    assert "强制优先：标准话术" in prompt
    assert "[3秒] 欢迎预约试驾" in prompt
