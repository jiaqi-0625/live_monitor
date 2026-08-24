import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import Settings


@dataclass(frozen=True)
class AnalysisResult:
    risk_level: str
    summary: str
    signals: list[str]
    actions: list[str]
    talk_track: str
    model: str


@dataclass(frozen=True)
class ReviewResult:
    summary: str
    metric_summary: str
    highlights: list[str]
    issues: list[str]
    actions: list[str]
    model: str


class EmptyLlmContentError(RuntimeError):
    """The model completed a request without returning visible content."""


def _call_llm_text(
    settings: Settings,
    *,
    system_prompt: str,
    user_prompt: str,
    timeout: int = 50,
    max_tokens: int = 3000,
) -> str:
    if not settings.llm_configured or not settings.llm_api_key:
        raise ValueError("大模型服务尚未配置，无法智能整理语料")
    base = settings.llm_api_base.rstrip("/")
    payload: dict[str, Any] = {
        "model": settings.llm_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
        "max_tokens": max_tokens,
    }
    if "v4" in settings.llm_model.lower() or "reasoner" in settings.llm_model.lower():
        payload["thinking"] = {"type": "disabled"}

    request = Request(
        f"{base}/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {settings.llm_api_key.get_secret_value()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(f"大模型接口返回 HTTP {exc.code}") from exc
    except TimeoutError as exc:
        raise RuntimeError("大模型处理超时，请稍后重试") from exc
    except URLError as exc:
        raise RuntimeError("服务器无法连接大模型服务") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("大模型返回内容无法识别") from exc
    try:
        choice = body["choices"][0]
        content = choice["message"].get("content")
    except (KeyError, IndexError, TypeError, AttributeError) as exc:
        raise RuntimeError("大模型返回内容无法识别") from exc
    if not isinstance(content, str) or not content.strip():
        finish_reason = str(choice.get("finish_reason") or "unknown")
        raise EmptyLlmContentError(f"大模型未返回正文（{finish_reason}）")
    return content.strip()


def condense_corpus_markdown(
    settings: Settings,
    *,
    filename: str,
    category: str,
    source_text: str,
) -> str:
    """Condense extracted source text into factual, storage-efficient Markdown."""
    if not settings.llm_configured or not settings.llm_api_key:
        raise ValueError("大模型服务尚未配置，无法智能整理语料")

    category_label = CORPUS_CATEGORY_LABELS.get(category, category)
    source_chunks = [
        source_text[index : index + 30_000]
        for index in range(0, len(source_text), 30_000)
    ]
    notes: list[str] = []
    for index, chunk in enumerate(source_chunks, start=1):
        try:
            note = _call_llm_text(
                settings,
                system_prompt=(
                    "你是汽车直播业务知识工程师。只提取原文中明确存在的事实，"
                    "绝不补充、猜测或改写数字、日期、价格、车型配置和限制条件。"
                ),
                user_prompt=f"""
从以下资料第 {index}/{len(source_chunks)} 段提取高密度事实笔记。
删除重复、修辞、目录、页眉页脚和无业务意义内容。
保留所有车型名称、配置差异、金额、日期、指标、阈值、条件、禁用词和标准话术。
使用简洁 Markdown 列表，不要写分析过程。

资料分类：{category_label}
原文：
{chunk}
""".strip(),
                max_tokens=2600,
            )
        except EmptyLlmContentError:
            note = chunk
        notes.append(note)

    combined_notes = "\n\n".join(notes)
    try:
        markdown = _call_llm_text(
            settings,
            system_prompt=(
                "你负责把汽车直播资料固化为可检索的 Markdown 语料。"
                "必须忠于输入笔记，不得引入常识或新信息。"
            ),
            user_prompt=f"""
将下列事实笔记去重、合并并整理为固定 Markdown 文档。必须严格使用这些一级结构：

# {Path(filename).stem}
> 分类：{category_label}｜来源：{filename}

## 核心摘要
## 关键事实与口径
## 数据、时间与阈值
## 规则、限制与禁用
## 可执行话术与动作

要求：
- 每节只写输入中确实存在的内容；没有内容时写“无”。
- 优先用紧凑列表和表格，合并同义项，删除重复和解释性废话。
- 原样保留数字、单位、日期、适用条件、车型版本和否定表述。
- 总长度尽量控制在 9000 个汉字以内，不要代码围栏，不要输出说明。

事实笔记：
{combined_notes}
""".strip(),
            max_tokens=6000,
        )
    except EmptyLlmContentError:
        return _fallback_corpus_markdown(
            filename=filename,
            category_label=category_label,
            source_text=source_text,
        )
    return _normalize_corpus_markdown_output(
        markdown,
        filename=filename,
        category_label=category_label,
    )


CORPUS_MARKDOWN_SECTIONS = (
    "核心摘要",
    "关键事实与口径",
    "数据、时间与阈值",
    "规则、限制与禁用",
    "可执行话术与动作",
)


def _normalize_corpus_markdown_output(
    output: str,
    *,
    filename: str,
    category_label: str,
) -> str:
    """Turn common LLM formatting variations into importable Markdown."""
    content = output.strip().lstrip("\ufeff")
    if not content:
        raise RuntimeError("大模型未返回可用语料")

    # Models sometimes add an explanation or wrap the answer in a Markdown fence.
    lines = [
        line
        for line in content.splitlines()
        if not re.fullmatch(r"\s*```(?:markdown|md)?\s*", line, re.IGNORECASE)
    ]
    h1_index: int | None = None
    for index, line in enumerate(lines):
        if re.match(r"^\s*#(?!#)\s*\S", line):
            h1_index = index
            break

    source_header = (
        f"# {Path(filename).stem}\n"
        f"> 分类：{category_label}｜来源：{filename}"
    )
    if h1_index is not None:
        lines = lines[h1_index:]
        title = re.sub(r"^\s*#(?!#)\s*", "", lines[0]).strip()
        lines[0] = f"# {title or Path(filename).stem}"
        if not any(
            line.lstrip().startswith(">") and "来源" in line
            for line in lines[1:5]
        ):
            lines.insert(1, f"> 分类：{category_label}｜来源：{filename}")
    else:
        first_h2 = next(
            (
                index
                for index, line in enumerate(lines)
                if re.match(r"^\s*##(?!#)\s*\S", line)
            ),
            None,
        )
        if first_h2 is None:
            lines = [source_header, "", "## 核心摘要", *lines]
        else:
            lines = [source_header, "", *lines[first_h2:]]

    markdown = "\n".join(lines).strip()
    existing_sections = {
        match.group(1).strip()
        for match in re.finditer(r"^\s*##(?!#)\s*(.+?)\s*$", markdown, re.MULTILINE)
    }
    missing_sections = [
        section for section in CORPUS_MARKDOWN_SECTIONS if section not in existing_sections
    ]
    if missing_sections:
        markdown += "\n\n" + "\n\n".join(
            f"## {section}\n无" for section in missing_sections
        )
    return markdown


def _fallback_corpus_markdown(
    *,
    filename: str,
    category_label: str,
    source_text: str,
) -> str:
    """Preserve extracted source text when the model returns no visible answer."""
    return (
        f"# {Path(filename).stem}\n"
        f"> 分类：{category_label}｜来源：{filename}\n\n"
        "## 核心摘要\n"
        "- 大模型本次未生成摘要，已按原文导入，建议后续人工检查。\n\n"
        "## 关键事实与口径\n"
        f"{source_text}\n\n"
        "## 数据、时间与阈值\n无\n\n"
        "## 规则、限制与禁用\n无\n\n"
        "## 可执行话术与动作\n无"
    )


METRIC_ALIASES = {
    "online_user_count": "online_users",
    "online_users": "online_users",
    "online_num": "online_users",
    "user_count": "online_users",
    "watch_user_count": "cumulative_viewers",
    "total_watch_user_count": "cumulative_viewers",
    "cumulative_viewers": "cumulative_viewers",
    "average_watch_duration": "average_watch_seconds",
    "avg_watch_duration": "average_watch_seconds",
    "average_watch_seconds": "average_watch_seconds",
    "exposure_enter_rate": "exposure_entry_rate",
    "exposure_entry_rate": "exposure_entry_rate",
    "interaction_rate": "interaction_rate",
    "comment_rate": "comment_rate",
    "follow_count": "new_followers",
    "new_followers": "new_followers",
    "clue_count": "lead_count",
    "business_opportunity_count": "lead_count",
    "lead_count": "lead_count",
    "cost": "spend",
    "spend": "spend",
    "card_click_count": "card_clicks",
    "card_clicks": "card_clicks",
    "component_click_count": "windmill_clicks",
    "windmill_click_count": "windmill_clicks",
}

AUTOENGINE_DATA_MAP_ALIASES = {
    "1": "average_watch_seconds",
    "2": "fans_average_watch_seconds",
    "3": "lead_count",
    "4": "lead_conversion_rate",
    "5": "private_message_users",
    "6": "private_message_longterm_conversions",
    "7": "online_users",
    "8": "preview_viewers",
    "9": "cumulative_viewers",
    "10": "fans_viewer_rate",
    "11": "view_count",
    "12": "exposure_entry_rate",
    "13": "exposure_users",
    "14": "fans_exposure_entry_rate",
    "15": "peak_online_users",
    "16": "average_online_users",
    "17": "spend",
    "18": "lead_cost",
    "19": "windmill_clicks",
    "20": "windmill_impressions",
    "21": "windmill_click_rate",
    "22": "new_followers",
    "23": "follower_rate",
    "24": "share_rate",
    "25": "share_users",
    "26": "share_count",
    "27": "like_rate",
    "28": "like_users",
    "29": "like_count",
    "30": "comment_rate",
    "31": "comment_users",
    "32": "comment_count",
    "33": "interaction_rate",
    "34": "interaction_users",
    "35": "interaction_count",
    "36": "card_clicks",
    "37": "card_impressions",
    "38": "card_click_rate",
    "39": "windmill_card_click_users",
    "40": "exposure_count",
    "41": "fans_exposure_share",
    "42": "watch_over_one_minute",
    "43": "fan_view_count",
    "44": "fan_viewers",
    "45": "fan_club_joins",
    "46": "fan_club_join_rate",
    "47": "tip_count",
    "48": "form_submits",
    "49": "form_users",
    "50": "form_cost",
    "51": "organic_traffic_rate",
    "52": "paid_traffic_rate",
    "53": "other_traffic_rate",
}


def _numeric_value(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if not isinstance(value, str):
        return None
    cleaned = value.strip().replace(",", "").removesuffix("%").strip()
    if not cleaned or cleaned in {"-", "--"}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def normalize_metrics(payload: Any, endpoint: str = "") -> dict[str, float]:
    normalized: dict[str, float] = {}
    is_autoengine_overview = "/screen/overview/data" in endpoint

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            data_map = value.get("data_map")
            if is_autoengine_overview and isinstance(data_map, dict):
                for source_key, normalized_key in AUTOENGINE_DATA_MAP_ALIASES.items():
                    numeric = _numeric_value(data_map.get(source_key))
                    if numeric is not None:
                        normalized[normalized_key] = numeric
            for key, child in value.items():
                normalized_key = METRIC_ALIASES.get(str(key).lower())
                numeric = _numeric_value(child) if normalized_key else None
                if normalized_key and numeric is not None:
                    normalized[normalized_key] = numeric
                else:
                    visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(payload)
    return normalized


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = text.removeprefix("```json").removeprefix("```")
        text = text.removesuffix("```").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("大模型未返回JSON结果")
    return json.loads(text[start : end + 1])


CORPUS_CATEGORY_LABELS = {
    "brand": "品牌口径",
    "vehicle": "车型卖点",
    "campaign": "活动政策",
    "script": "标准话术",
    "constraint": "禁用与约束",
    "metric_core": "核心指标目标",
    "metric_traffic": "流量与观看",
    "metric_conversion": "转化与经营",
    "metric_engagement": "互动表现",
    "metric_threshold": "指标阈值与预警",
    "other": "其他资料",
}


def _format_corpus_context(corpus_entries: list[dict[str, Any]] | None) -> str:
    corpus_parts: list[str] = []
    corpus_length = 0
    for entry in corpus_entries or []:
        category = str(entry.get("category", "other"))
        category_label = CORPUS_CATEGORY_LABELS.get(category, category)
        retrieval_reason = str(entry.get("retrieval_reason", "")).strip()
        source = f"语料ID={entry.get('id', '未知')}"
        if retrieval_reason:
            source += f"；命中原因={retrieval_reason}"
        text = (
            f"[{category_label}] {entry.get('title', '')}\n"
            f"[{source}]\n"
            f"{entry.get('content', '')}"
        ).strip()
        if not text:
            continue
        remaining = 12000 - corpus_length
        if remaining <= 0:
            break
        corpus_parts.append(text[:remaining])
        corpus_length += len(corpus_parts[-1])
    return "\n\n".join(corpus_parts)


def analyze_with_llm(
    settings: Settings,
    metric_payloads: list[dict[str, Any]],
    normalized_metrics: dict[str, float],
    transcripts: list[dict[str, Any]],
    corpus_entries: list[dict[str, Any]] | None = None,
) -> AnalysisResult:
    if not settings.llm_configured or not settings.llm_api_key:
        raise ValueError("大模型服务尚未配置")

    transcript_text = "\n".join(
        f"- {item['text']}" for item in transcripts[-20:] if item.get("text")
    )
    raw_metrics = json.dumps(metric_payloads[-6:], ensure_ascii=False)
    if len(raw_metrics) > 24000:
        raw_metrics = raw_metrics[-24000:]

    corpus_context = _format_corpus_context(corpus_entries)

    prompt = f"""
你是汽车直播间的实时盯播优化师。请结合大屏数据和主播最近话术，判断当前风险并给出可立即执行的动作。

标准化指标：
{json.dumps(normalized_metrics, ensure_ascii=False)}

最近大屏接口数据：
{raw_metrics}

最近转写：
{transcript_text or "暂无转写"}

当前优化师启用的个性化语料：
{corpus_context or "暂无个性化语料"}

生成提醒和主播话术时，应优先遵守上述语料中的品牌口径、车型卖点、活动政策、标准话术、禁用要求，以及各监控指标的目标、阈值和诊断规则；语料与实时数据冲突时，以实时数据为准。

只返回以下JSON，不要Markdown：
{{
  "risk_level": "normal|attention|critical",
  "summary": "不超过80字的实时诊断",
  "signals": ["最多3条，必须引用具体指标或趋势"],
  "actions": ["最多3条，按优先级排列的具体动作"],
  "talk_track": "主播下一句可直接使用的话术，不超过80字"
}}
""".strip()

    base = settings.llm_api_base.rstrip("/")
    request = Request(
        f"{base}/chat/completions",
        data=json.dumps(
            {
                "model": settings.llm_model,
                "messages": [
                    {
                        "role": "system",
                        "content": "你负责汽车直播实时诊断，输出必须准确、简洁、可执行。",
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
                "response_format": {"type": "json_object"},
            },
            ensure_ascii=False,
        ).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {settings.llm_api_key.get_secret_value()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=35) as response:
            body = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(f"大模型接口返回 HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError("服务器无法连接大模型服务") from exc

    content = body["choices"][0]["message"]["content"]
    result = _extract_json(content)
    risk_level = str(result.get("risk_level", "attention"))
    if risk_level not in {"normal", "attention", "critical"}:
        risk_level = "attention"
    return AnalysisResult(
        risk_level=risk_level,
        summary=str(result.get("summary", "已完成本轮实时分析")),
        signals=[str(item) for item in result.get("signals", [])][:3],
        actions=[str(item) for item in result.get("actions", [])][:3],
        talk_track=str(result.get("talk_track", "")),
        model=settings.llm_model,
    )


def analyze_session_review(
    settings: Settings,
    session: dict[str, Any],
    normalized_metrics: dict[str, float],
    transcripts: list[dict[str, Any]],
    corpus_entries: list[dict[str, Any]] | None = None,
) -> ReviewResult:
    if not settings.llm_configured or not settings.llm_api_key:
        raise ValueError("大模型服务尚未配置")

    transcript_text = "\n".join(
        f"[{int(item.get('start_ms', 0)) // 1000}秒] {item.get('text', '')}"
        for item in transcripts
        if item.get("text")
    )
    if len(transcript_text) > 60000:
        transcript_text = (
            transcript_text[:30000]
            + "\n……中间内容已压缩……\n"
            + transcript_text[-30000:]
        )

    corpus_context = _format_corpus_context(corpus_entries)

    prompt = f"""
你是汽车直播运营复盘专家。请根据整场直播的最终指标和完整转写，生成可供优化师执行的整场复盘。

场次信息：
{json.dumps(session, ensure_ascii=False, default=str)}

最终及累计指标：
{json.dumps(normalized_metrics, ensure_ascii=False)}

本场命中的个性化语料：
{corpus_context or "暂无个性化语料"}

整场转写：
{transcript_text or "暂无有效转写"}

复盘结论必须优先遵守上述语料中的标准话术、禁用要求、活动条件和指标阈值；问题和亮点应引用具体指标或转写时间点作为证据。

只返回以下JSON，不要Markdown：
{{
  "summary": "不超过180字的整场结论",
  "metric_summary": "不超过160字的数据表现概括，引用关键数字",
  "highlights": ["最多5条做得好的地方"],
  "issues": ["最多5条需要改进的问题，需有证据"],
  "actions": ["最多6条下一场直播可直接执行的改进动作"]
}}
""".strip()

    base = settings.llm_api_base.rstrip("/")
    request = Request(
        f"{base}/chat/completions",
        data=json.dumps(
            {
                "model": settings.llm_model,
                "messages": [
                    {
                        "role": "system",
                        "content": "你负责汽车直播整场复盘，结论必须基于数据和话术证据。",
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
                "response_format": {"type": "json_object"},
            },
            ensure_ascii=False,
        ).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {settings.llm_api_key.get_secret_value()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=50) as response:
            body = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(f"大模型接口返回 HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError("服务器无法连接大模型服务") from exc

    result = _extract_json(body["choices"][0]["message"]["content"])
    return ReviewResult(
        summary=str(result.get("summary", "已完成整场复盘")),
        metric_summary=str(result.get("metric_summary", "")),
        highlights=[str(item) for item in result.get("highlights", [])][:5],
        issues=[str(item) for item in result.get("issues", [])][:5],
        actions=[str(item) for item in result.get("actions", [])][:6],
        model=settings.llm_model,
    )
