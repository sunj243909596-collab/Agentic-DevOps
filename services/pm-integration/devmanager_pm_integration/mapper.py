"""DTO → ORM 字段映射。

设计原则：
- **缺字段降级**：PM 平台某次响应缺字段时，不抛错，置 None / ORM 默认
- **last_synced_at** 由 DAO 内部统一设置，**不在本模块**（避免 mapper / DAO 抢值）
- 返回 dict（key 是 ORM 字段名），调用方负责构造 ORM 实例或 upsert

调用方示例：
    dto = IterationDTO.model_validate(api_response)
    fields = iteration_to_orm_fields(dto)
    await iteration_dao.upsert_from_pm(**fields)
"""

from __future__ import annotations

from typing import Any

from devmanager_pm_integration.models.dto import (
    IssueAssignmentDTO,
    IssueDTO,
    IterationDTO,
)


def iteration_to_orm_fields(dto: IterationDTO) -> dict[str, Any]:
    """IterationDTO → Iteration ORM 字段 dict。

    注意：
    - pm_iteration_id 对应 DTO 的 id（PM 平台字段名）
    - last_synced_at 不在此处（DAO 内部 = now()）
    """
    return {
        "pm_iteration_id": dto.id,
        "name": dto.name,
        "start_date": dto.start_date,
        "end_date": dto.end_date,
        "status": dto.status,
        "pm_created_at": dto.created_at,
        "pm_updated_at": dto.updated_at,
    }


def issue_to_orm_fields(dto: IssueDTO) -> dict[str, Any]:
    """IssueDTO → Issue ORM 字段 dict。

    注意：
    - iteration_id 在 ORM 是 UUID FK，但 DTO 是 str（PM 平台外键）。
      调用方（sync 逻辑）负责两阶段：先 upsert iteration，再解析 iteration_id 再 upsert issue。
    - last_synced_at 不在此处。
    """
    return {
        "pm_issue_id": dto.id,
        "issue_key": dto.key,
        "title": dto.title,
        "issue_type": dto.type,
        "priority": dto.priority,
        "status": dto.status,
        "estimate_hours": dto.estimate_hours,
        # iteration_id 留给 sync 层用 pm_iteration_id 反查后填
        "pm_created_at": dto.created_at,
        "pm_updated_at": dto.updated_at,
    }


def issue_assignment_to_orm_fields(dto: IssueAssignmentDTO) -> dict[str, Any]:
    """IssueAssignmentDTO → IssueAssignment ORM 字段 dict。

    注意：
    - issue_id 在 ORM 是 UUID FK，但 DTO 是 str（PM 平台 issue id）。
      sync 层负责两阶段。
    - person_id 留给 sync 层用 pm_user_id 反查 PmIdentity 后填。
    - last_synced_at 不在此处。
    """
    return {
        "pm_user_id": dto.user_id,
        "pm_username": dto.username or dto.user_id,
        "role": dto.role,
        "weight": dto.weight,
    }


# ── 字段白名单（防御 DTO 越界） ─────────────────────────────────────────────


_ITERATION_FIELDS = frozenset(
    iteration_to_orm_fields(
        IterationDTO(
            id="x",
            name="x",
            start_date=__import__("datetime").date(2026, 1, 1),
            end_date=__import__("datetime").date(2026, 1, 7),
            status="planning",
        )
    ).keys()
)

_ISSUE_FIELDS = frozenset(
    issue_to_orm_fields(
        IssueDTO(
            id="x",
            key="x-1",
            title="x",
            type="task",
            priority="low",
            status="open",
        )
    ).keys()
)

_ASSIGNMENT_FIELDS = frozenset(
    issue_assignment_to_orm_fields(
        IssueAssignmentDTO(
            issue_id="x",
            user_id="u",
            role="assignee",
        )
    ).keys()
)


def filter_known_fields(fields: dict[str, Any], *, entity: str) -> dict[str, Any]:
    """白名单过滤：丢弃 ORM 不认识的字段，防止 mapper 扩展时污染 ORM。"""
    if entity == "iteration":
        allowed = _ITERATION_FIELDS
    elif entity == "issue":
        allowed = _ISSUE_FIELDS
    elif entity == "issue_assignment":
        allowed = _ASSIGNMENT_FIELDS
    else:
        raise ValueError(f"Unknown entity: {entity}")
    return {k: v for k, v in fields.items() if k in allowed}
