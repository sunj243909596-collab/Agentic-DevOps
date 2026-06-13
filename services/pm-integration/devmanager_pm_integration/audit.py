"""pm-integration 审计写入助手。

把 `integration.sync` / `integration.identity_changed` 等事件类型
封装成薄函数，调用方只传业务字段，DAO 的元数据/时间戳规则由本模块统一处理。
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from devmanager_db.daos.audit_event import AuditEventDAO

# 事件类型常量（避免拼写漂移）
EVENT_INTEGRATION_SYNC = "integration.sync"
EVENT_IDENTITY_CHANGED = "integration.identity_changed"


async def record_sync(
    audit_dao: AuditEventDAO,
    *,
    actor: str,
    sync_type: str,           # 'full' | 'incremental'
    source: str,              # 'pm' | 'gitlab' | 'reconciliation'
    records_processed: int,
    duration_ms: int,
    success: bool,
    failure_reason: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """记录一次同步事件。"""
    payload: dict[str, Any] = {
        "sync_type": sync_type,
        "source": source,
        "records_processed": records_processed,
        "duration_ms": duration_ms,
        "success": success,
    }
    if failure_reason:
        payload["failure_reason"] = failure_reason
    if metadata:
        payload.update(metadata)

    await audit_dao.append(
        actor=actor,
        workflow_id=None,
        event_type=EVENT_INTEGRATION_SYNC,
        event_timestamp=datetime.now(UTC),
        tool="pm-integration",
        metadata=payload,
    )


async def record_identity_change(
    audit_dao: AuditEventDAO,
    *,
    actor: str,
    person_id: uuid.UUID,
    action: str,              # 'map' | 'unmap'
    identity_kind: str,       # 'gitlab' | 'pm'
    identity_value: str,
) -> None:
    """记录身份映射变更（CLI / 手动）。"""
    await audit_dao.append(
        actor=actor,
        workflow_id=None,
        event_type=EVENT_IDENTITY_CHANGED,
        event_timestamp=datetime.now(UTC),
        tool="identity-cli",
        metadata={
            "person_id": str(person_id),
            "action": action,
            "identity_kind": identity_kind,
            "identity_value": identity_value,
        },
    )
