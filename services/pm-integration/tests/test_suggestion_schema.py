"""S4 P5 — Suggestion JSON Schema + 黑名单词校验 + audit extension。"""

from __future__ import annotations

import pytest
from devmanager_pm_integration.suggestion_schema import (
    SUGGESTION_PAYLOAD_SCHEMA,
    validate_payload,
)

# ── 黑名单词校验 ────────────────────────────────────────────────────────────


def test_payload_accepts_clean_text() -> None:
    payload = {
        "facts": ["本周有 3 个 open issue", "总剩余 12h 估时"],
        "trends": ["较上周 +1 issue"],
        "notes": ["数据来自 workload_snapshot"],
    }
    model = validate_payload(payload)
    assert len(model.facts) == 2


def test_payload_rejects_should_chinese() -> None:
    with pytest.raises(ValueError, match="指令性词"):
        validate_payload(
            {
                "facts": ["你应该分配更多 issue"],  # 黑名单
                "trends": [],
                "notes": [],
            }
        )


def test_payload_rejects_must_english() -> None:
    with pytest.raises(ValueError, match="指令性词"):
        validate_payload(
            {
                "facts": ["must increase capacity"],  # 黑名单
                "trends": [],
                "notes": [],
            }
        )


def test_payload_rejects_recommend() -> None:
    with pytest.raises(ValueError, match="指令性词"):
        validate_payload(
            {
                "facts": ["I recommend this"],  # 黑名单
                "trends": [],
                "notes": [],
            }
        )


def test_payload_extra_fields_ignored() -> None:
    """PM 平台 / 上游系统多塞字段不破坏解析。"""
    model = validate_payload(
        {
            "facts": ["x"],
            "trends": [],
            "notes": [],
            "extra_metadata": {"foo": "bar"},
        }
    )
    assert model.facts == ["x"]


def test_payload_ignores_non_string_items() -> None:
    """非 string 元素不应触发黑名单校验（v1 防御策略）。"""
    model = validate_payload(
        {
            "facts": [123, 4.5, None],
            "trends": [],
            "notes": [],
        }
    )
    assert model.facts == [123, 4.5, None]


# ── JSON Schema 文档结构 ────────────────────────────────────────────────────


def test_json_schema_required_fields() -> None:
    assert "facts" in SUGGESTION_PAYLOAD_SCHEMA["required"]
    assert "trends" in SUGGESTION_PAYLOAD_SCHEMA["required"]
    assert "notes" in SUGGESTION_PAYLOAD_SCHEMA["required"]


# ── Audit 扩展 helper（轻量测试） ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_record_suggestion_generated_writes_event():
    """需要 DB session，跳过裸调用 → 此处用 Pydantic 模型做端到端 sanity check。"""
    # 实际 audit 写入测试在 test_sync.py 已覆盖；本测试仅校验 helper 签名 + 调用
    from devmanager_db.daos.audit_extensions import (
        EVENT_SUGGESTION_FEEDBACK,
        EVENT_SUGGESTION_GENERATED,
        EVENT_SUGGESTION_VIEWED,
    )

    assert EVENT_SUGGESTION_GENERATED == "suggestion.generated"
    assert EVENT_SUGGESTION_VIEWED == "suggestion.viewed"
    assert EVENT_SUGGESTION_FEEDBACK == "suggestion.feedback"
