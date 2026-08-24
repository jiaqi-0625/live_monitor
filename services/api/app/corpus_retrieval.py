from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Literal

from rank_bm25 import BM25Plus

RetrievalMode = Literal["realtime", "review"]

_CATEGORY_LABELS = {
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

_REQUIRED_CATEGORIES = (
    "constraint",
    "script",
    "metric_threshold",
    "metric_core",
)

_CATEGORY_BOOSTS = {
    "constraint": 8.0,
    "script": 5.0,
    "metric_threshold": 5.0,
    "metric_core": 4.0,
    "campaign": 2.5,
    "brand": 2.0,
}

_METRIC_QUERY_TERMS = {
    "online_users": "在线人数 在线用户 实时在线",
    "average_online_users": "平均在线人数",
    "peak_online_users": "峰值在线人数",
    "cumulative_viewers": "累计观看人数 累计观众",
    "average_watch_seconds": "平均观看时长 停留时长",
    "interaction_rate": "互动率 评论 点赞 分享",
    "comment_rate": "评论率 评论互动",
    "like_rate": "点赞率 点赞互动",
    "share_rate": "分享率 分享互动",
    "lead_count": "线索数 留资数 商机数",
    "lead_conversion_rate": "线索转化率 留资转化率",
    "lead_cost": "线索成本 留资成本",
    "card_click_rate": "卡片点击率 组件点击率",
    "exposure_entry_rate": "曝光进入率 进房率",
    "organic_traffic_rate": "自然流量占比",
    "paid_traffic_rate": "付费流量占比 投流",
    "spend": "消耗 投放金额",
}

_TOKEN_PATTERN = re.compile(
    r"[\u3400-\u4dbf\u4e00-\u9fff]+|[a-zA-Z0-9]+(?:[._%/-][a-zA-Z0-9]+)*"
)
_RULE_MARKERS = ("禁用", "禁止", "不得", "严禁", "合规", "限制", "标准话术", "口径")
_MAX_CHUNK_CHARS = 1_800
_CHUNK_OVERLAP_CHARS = 160


@dataclass(frozen=True)
class _CorpusChunk:
    entry: dict[str, Any]
    content: str
    chunk_index: int


def tokenize_for_retrieval(text: str) -> list[str]:
    """Tokenize mixed Chinese/Latin text for BM25 without a remote model."""
    tokens: list[str] = []
    for match in _TOKEN_PATTERN.finditer(text.lower()):
        value = match.group(0)
        if re.fullmatch(r"[\u3400-\u4dbf\u4e00-\u9fff]+", value):
            if len(value) == 1:
                tokens.append(value)
                continue
            tokens.extend(value[index : index + 2] for index in range(len(value) - 1))
            if len(value) <= 8:
                tokens.append(value)
        else:
            tokens.append(value)
    return tokens


def build_corpus_query(
    session: dict[str, Any],
    normalized_metrics: dict[str, float],
    transcripts: list[dict[str, Any]],
    *,
    mode: RetrievalMode,
) -> str:
    transcript_limit = 20 if mode == "realtime" else 200
    transcript_text = "\n".join(
        str(item.get("text", ""))
        for item in transcripts[-transcript_limit:]
        if item.get("text")
    )
    metric_terms = " ".join(
        f"{key} {_METRIC_QUERY_TERMS.get(key, '')} {value}"
        for key, value in normalized_metrics.items()
    )
    session_text = " ".join(
        str(session.get(key, ""))
        for key in ("title", "room_name", "platform", "operator_name")
    )
    return f"{session_text}\n{metric_terms}\n{transcript_text}".strip()


def retrieve_corpus_context(
    entries: list[dict[str, Any]],
    *,
    session: dict[str, Any],
    normalized_metrics: dict[str, float],
    transcripts: list[dict[str, Any]],
    mode: RetrievalMode,
    max_chars: int = 12_000,
    max_hits: int = 10,
) -> list[dict[str, Any]]:
    """Return compact, traceable corpus excerpts relevant to the current analysis."""
    enabled_entries = [entry for entry in entries if entry.get("enabled", True)]
    chunks = [
        chunk
        for entry in enabled_entries
        for chunk in _chunk_entry(entry)
    ]
    if not chunks or max_chars <= 0 or max_hits <= 0:
        return []

    query = build_corpus_query(
        session,
        normalized_metrics,
        transcripts,
        mode=mode,
    )
    tokenized_chunks = [
        tokenize_for_retrieval(
            " ".join(
                (
                    _CATEGORY_LABELS.get(str(chunk.entry.get("category", "other")), ""),
                    str(chunk.entry.get("title", "")),
                    chunk.content,
                )
            )
        )
        for chunk in chunks
    ]
    bm25 = BM25Plus(tokenized_chunks)
    query_tokens = tokenize_for_retrieval(query)
    bm25_scores = bm25.get_scores(query_tokens) if query_tokens else [0.0] * len(chunks)

    ranked: list[tuple[float, float, int, _CorpusChunk]] = []
    for position, (chunk, raw_score) in enumerate(zip(chunks, bm25_scores, strict=True)):
        category = str(chunk.entry.get("category", "other"))
        marker_boost = 1.5 if any(marker in chunk.content for marker in _RULE_MARKERS) else 0.0
        score = float(raw_score) + _CATEGORY_BOOSTS.get(category, 0.0) + marker_boost
        ranked.append((score, float(raw_score), -position, chunk))
    ranked.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)

    selected: list[tuple[float, float, _CorpusChunk, str]] = []
    selected_keys: set[tuple[object, int]] = set()

    for required_category in _REQUIRED_CATEGORIES:
        required_hit = next(
            (
                item
                for item in ranked
                if str(item[3].entry.get("category", "other")) == required_category
            ),
            None,
        )
        if required_hit is None:
            continue
        score, raw_score, _, chunk = required_hit
        key = (chunk.entry.get("id"), chunk.chunk_index)
        selected.append(
            (
                score,
                raw_score,
                chunk,
                f"强制优先：{_CATEGORY_LABELS.get(required_category, required_category)}",
            )
        )
        selected_keys.add(key)

    for score, raw_score, _, chunk in ranked:
        if len(selected) >= max_hits:
            break
        key = (chunk.entry.get("id"), chunk.chunk_index)
        if key in selected_keys:
            continue
        if raw_score <= 0 and selected:
            continue
        reason = f"BM25命中当前{('实时问题' if mode == 'realtime' else '复盘主题')}"
        selected.append((score, raw_score, chunk, reason))
        selected_keys.add(key)

    if not selected:
        score, raw_score, _, chunk = ranked[0]
        selected.append((score, raw_score, chunk, "无关键词命中，使用最高优先级语料"))

    results: list[dict[str, Any]] = []
    used_chars = 0
    for score, raw_score, chunk, reason in selected:
        title = str(chunk.entry.get("title", "")).strip()
        category = str(chunk.entry.get("category", "other"))
        overhead = len(title) + len(category) + len(reason) + 80
        remaining = max_chars - used_chars - overhead
        if remaining <= 0:
            break
        excerpt = chunk.content[:remaining].strip()
        if not excerpt:
            continue
        results.append(
            {
                **chunk.entry,
                "content": excerpt,
                "retrieval_score": round(score, 4),
                "retrieval_bm25_score": round(raw_score, 4),
                "retrieval_reason": reason,
                "retrieval_chunk": chunk.chunk_index,
            }
        )
        used_chars += len(excerpt) + overhead
        if len(results) >= max_hits:
            break
    return results


def corpus_retrieval_log_payload(entries: list[dict[str, Any]]) -> str:
    return json.dumps(
        [
            {
                "id": entry.get("id"),
                "title": entry.get("title"),
                "category": entry.get("category"),
                "reason": entry.get("retrieval_reason"),
                "score": entry.get("retrieval_score"),
                "chunk": entry.get("retrieval_chunk"),
            }
            for entry in entries
        ],
        ensure_ascii=False,
    )


def _chunk_entry(entry: dict[str, Any]) -> list[_CorpusChunk]:
    content = str(entry.get("content", "")).strip()
    if not content:
        return []
    pieces = _split_text(content)
    return [
        _CorpusChunk(entry=entry, content=piece, chunk_index=index)
        for index, piece in enumerate(pieces)
    ]


def _split_text(text: str) -> list[str]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    if not paragraphs:
        return []

    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(paragraph) > _MAX_CHUNK_CHARS:
            if current:
                chunks.append(current)
                current = ""
            start = 0
            while start < len(paragraph):
                end = min(len(paragraph), start + _MAX_CHUNK_CHARS)
                chunks.append(paragraph[start:end])
                if end >= len(paragraph):
                    break
                start = end - _CHUNK_OVERLAP_CHARS
            continue

        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate) <= _MAX_CHUNK_CHARS:
            current = candidate
        else:
            chunks.append(current)
            current = paragraph
    if current:
        chunks.append(current)
    return chunks
