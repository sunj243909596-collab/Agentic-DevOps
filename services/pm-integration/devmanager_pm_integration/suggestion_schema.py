"""S4 P5 — Suggestion JSON Schema（沿用 contracts 模式）。

严守 PRD 边界：payload 文案只含"事实 + 趋势"，禁出现
"应该 / 必须 / 建议 / 推荐 / 应当 / 最好"等指令性语言。

校验由 Pydantic 模型执行；本模块提供：
- `SUGGESTION_PAYLOAD_SCHEMA`：纯 JSON Schema（供 docs / 测试用）
- `SuggestionPayload` Pydantic 模型（程序入口）
- `validate_payload()`：抛出 `ValueError` 当文案越界
"""
from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# 黑名单词（v1 简化：英文用 \b 边界，中文用前后非汉字字符）
# 注意：Python \b 对 CJK 无效，所以中文分支单独处理
_FORBIDDEN_EN = re.compile(
    r"\b(should|must|recommend|ought|need\s+to)\b",
    re.IGNORECASE,
)
_FORBIDDEN_CN = re.compile(r"应该|必须|建议|推荐|应当|最好")


def _has_forbidden(text: str) -> str | None:
    """返回第一个命中的黑名单词；未命中返回 None。"""
    m = _FORBIDDEN_EN.search(text)
    if m:
        return m.group(0)
    m = _FORBIDDEN_CN.search(text)
    if m:
        return m.group(0)
    return None


class SuggestionPayload(BaseModel):
    """Suggestion payload 的强类型结构。

    字段：
    - facts: 事实陈述列表（数字 + 来源 + 时间窗）
    - trends: 趋势观察（与上次对比变化量 + 方向）
    - notes: 简短上下文（不含指令性词）
    """

    model_config = ConfigDict(extra="ignore")

    facts: list[str | int | float | None] = Field(default_factory=list)
    trends: list[str | int | float | None] = Field(default_factory=list)
    notes: list[str | int | float | None] = Field(default_factory=list)

    def model_post_init(self, __context: Any) -> None:
        """Post-init hook: 校验所有文本字段不含黑名单词。"""
        for field_name in ("facts", "trends", "notes"):
            values = getattr(self, field_name)
            for text in values:
                if not isinstance(text, str):
                    continue
                hit = _has_forbidden(text)
                if hit is not None:
                    raise ValueError(
                        f"Suggestion payload {field_name!r} 包含指令性词 "
                        f"({hit!r})；违反 PRD 边界：仅事实 + 趋势。"
                    )


def validate_payload(payload: dict[str, Any]) -> SuggestionPayload:
    """校验 payload 文案合规性。返回强类型模型。"""
    return SuggestionPayload.model_validate(payload)


# ── 纯 JSON Schema 文档（供 docs / OpenAPI / 前端类型生成用） ──────────────

SUGGESTION_PAYLOAD_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "SuggestionPayload",
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "facts": {
            "type": "array",
            "items": {"type": "string"},
            "description": "事实陈述（数字 + 来源 + 时间窗），不含指令性词",
        },
        "trends": {
            "type": "array",
            "items": {"type": "string"},
            "description": "趋势观察（变化量 + 方向），不含指令性词",
        },
        "notes": {
            "type": "array",
            "items": {"type": "string"},
            "description": "上下文注释，不含指令性词",
        },
    },
    "required": ["facts", "trends", "notes"],
}


SUGGESTION_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "Suggestion",
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "suggestion_id": {"type": "string", "format": "uuid"},
        "target_type": {
            "type": "string",
            "enum": ["team", "person", "iteration", "issue"],
        },
        "target_id": {"type": "string", "format": "uuid"},
        "suggestion_type": {
            "type": "string",
            "enum": ["sprint_planning", "task_assignment", "priority", "growth"],
        },
        "payload": SUGGESTION_PAYLOAD_SCHEMA,
        "source_refs": {
            "type": "object",
            "description": "来源 row 引用（snapshot 表 / iteration / mr_review_event）",
            "additionalProperties": True,
        },
        "status": {
            "type": "string",
            "enum": ["pending", "viewed", "accepted", "dismissed", "expired"],
        },
        "generated_at": {"type": "string", "format": "date-time"},
    },
    "required": [
        "target_type", "target_id", "suggestion_type", "payload", "source_refs",
    ],
}
