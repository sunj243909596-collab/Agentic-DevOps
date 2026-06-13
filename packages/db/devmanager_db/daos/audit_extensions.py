"""S4 P5 — AuditEventDAO 扩展 helper。

把 `suggestion.generated` / `suggestion.viewed` / `suggestion.feedback` 事件
封装成薄函数，调用方只传业务字段。
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from devmanager_db.daos.audit_event import AuditEventDAO

# 事件类型常量
EVENT_SUGGESTION_GENERATED = "suggestion.generated"
EVENT_SUGGESTION_VIEWED = "suggestion.viewed"
EVENT_SUGGESTION_FEEDBACK = "suggestion.feedback"


async def record_suggestion_generated(
    audit_dao: AuditEventDAO,
    *,
    actor: str,
    suggestion_id: uuid.UUID,
    target_type: str,
    target_id: uuid.UUID,
    suggestion_type: str,
    source_refs: dict[str, Any],
) -> None:
    """记录一次"建议生成"事件。

    注意：v1 实际"生成"是策略模块的工作，本函数只是 audit 记录。
    """
    await audit_dao.append(
        actor=actor,
        workflow_id=None,
        event_type=EVENT_SUGGESTION_GENERATED,
        event_timestamp=datetime.now(UTC),
        tool="suggestion-engine",
        metadata={
            "suggestion_id": str(suggestion_id),
            "target_type": target_type,
            "target_id": str(target_id),
            "suggestion_type": suggestion_type,
            "source_refs": source_refs,
        },
    )


async def record_suggestion_viewed(
    audit_dao: AuditEventDAO,
    *,
    actor: str,
    suggestion_id: uuid.UUID,
) -> None:
    await audit_dao.append(
        actor=actor,
        workflow_id=None,
        event_type=EVENT_SUGGESTION_VIEWED,
        event_timestamp=datetime.now(UTC),
        tool="suggestion-ui",
        metadata={"suggestion_id": str(suggestion_id)},
    )


async def record_suggestion_feedback(
    audit_dao: AuditEventDAO,
    *,
    actor: str,
    suggestion_id: uuid.UUID,
    feedback_type: str,             # 'accepted' | 'dismissed' | 'commented'
    comment: str | None = None,
) -> None:
    await audit_dao.append(
        actor=actor,
        workflow_id=None,
        event_type=EVENT_SUGGESTION_FEEDBACK,
        event_timestamp=datetime.now(UTC),
        tool="suggestion-ui",
        metadata={
            "suggestion_id": str(suggestion_id),
            "feedback_type": feedback_type,
            "comment": comment,
        },
    )
