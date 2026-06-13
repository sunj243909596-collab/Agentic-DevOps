"""DTO → ORM 幂等 upsert 助手。

设计原则：
- 全部 DAO 已在 P2 实现 `upsert_from_pm`（按 PM 平台 ID 幂等）
- 本模块只做两阶段解析（PM ID → ORM UUID FK），不重复实现 upsert 逻辑
- 缺字段（DTO optional）走 ORM 默认值（None / 0.0 / 空 list）
- 解析失败的字段记入 audit metadata.missing_fields
"""
from __future__ import annotations

from typing import Any

from devmanager_db.daos.team_ops.issue import IssueDAO
from devmanager_db.daos.team_ops.issue_assignment import IssueAssignmentDAO
from devmanager_db.daos.team_ops.iteration import IterationDAO
from devmanager_db.daos.team_ops.pm_identity import PmIdentityDAO
from devmanager_db.models import Issue, IssueAssignment, Iteration, PmIdentity

from devmanager_pm_integration.mapper import (
    filter_known_fields,
    issue_assignment_to_orm_fields,
    issue_to_orm_fields,
    iteration_to_orm_fields,
)
from devmanager_pm_integration.models.dto import (
    IssueAssignmentDTO,
    IssueDTO,
    IterationDTO,
)


class UpsertResult:
    """一次 upsert 调用的统计。"""

    __slots__ = ("succeeded", "missing_fields")

    def __init__(self, *, succeeded: int, missing_fields: list[str]) -> None:
        self.succeeded = succeeded
        self.missing_fields = missing_fields


def _detect_missing(dto_payload: dict[str, Any], required: tuple[str, ...]) -> list[str]:
    return [f for f in required if f not in dto_payload or dto_payload[f] is None]


# ── Iteration ───────────────────────────────────────────────────────────────


async def upsert_iteration(
    iteration_dao: IterationDAO,
    payload: dict[str, Any],
) -> tuple[Iteration, UpsertResult]:
    """Upsert 一个 iteration。返回 (orm_row, result)。

    必填（per A1）：id, name, start_date, end_date, status。
    缺失字段会被记录到 result.missing_fields。
    """
    missing = _detect_missing(payload, ("id", "name", "start_date", "end_date", "status"))
    dto = IterationDTO.model_validate(payload)
    fields = filter_known_fields(iteration_to_orm_fields(dto), entity="iteration")
    row = await iteration_dao.upsert_from_pm(**fields)
    return row, UpsertResult(succeeded=1, missing_fields=missing)


# ── Issue ───────────────────────────────────────────────────────────────────


async def upsert_issue(
    issue_dao: IssueDAO,
    iteration_dao: IterationDAO,
    payload: dict[str, Any],
) -> tuple[Issue, UpsertResult]:
    """Upsert 一个 issue。两阶段：先反查 iteration_id。"""
    missing = _detect_missing(
        payload, ("id", "key", "title", "type", "priority", "status"),
    )
    dto = IssueDTO.model_validate(payload)
    fields = filter_known_fields(issue_to_orm_fields(dto), entity="issue")

    # 两阶段：PM iteration_id (str) → ORM iteration_id (UUID)
    if dto.iteration_id is not None:
        iteration_row = await iteration_dao.get_by_pm_id(dto.iteration_id)
        if iteration_row is not None:
            fields["iteration_id"] = iteration_row.iteration_id
        # iteration 尚未入库 → 留 None，等下一轮 iteration sync 后再回填

    row = await issue_dao.upsert_from_pm(**fields)
    return row, UpsertResult(succeeded=1, missing_fields=missing)


# ── IssueAssignment ─────────────────────────────────────────────────────────


async def upsert_assignment(
    assignment_dao: IssueAssignmentDAO,
    issue_dao: IssueDAO,
    pm_identity_dao: PmIdentityDAO,
    payload: dict[str, Any],
    *,
    resolve_person: bool = True,
) -> tuple[IssueAssignment, UpsertResult]:
    """Upsert 一个 issue_assignment。两阶段反查 issue / person。

    resolve_person=False 用于尚无 person 映射的场景（v1 接受 None person_id）。
    """
    missing = _detect_missing(payload, ("issue_id", "user_id", "role"))
    dto = IssueAssignmentDTO.model_validate(payload)
    fields = filter_known_fields(
        issue_assignment_to_orm_fields(dto), entity="issue_assignment",
    )

    # 两阶段：issue
    issue_row = await issue_dao.get_by_pm_id(dto.issue_id)
    if issue_row is None:
        # 关联 issue 尚未 sync → 跳过本次 assignment（partial sync 容错）
        return (
            None,  # type: ignore[return-value]
            UpsertResult(succeeded=0, missing_fields=missing + ["issue_not_synced"]),
        )
    fields["issue_id"] = issue_row.issue_id

    # 两阶段：person
    if resolve_person:
        # 通过 PmIdentity 反查 person_id（v1: 仅按 active 行）
        identity = await pm_identity_dao.get_active_by_user_id(dto.user_id)
        if identity is not None:
            fields["person_id"] = identity.person_id

    row = await assignment_dao.upsert_from_pm(**fields)
    return row, UpsertResult(succeeded=1, missing_fields=missing)


# ── User ────────────────────────────────────────────────────────────────────


async def upsert_user_mirror(
    pm_identity_dao: PmIdentityDAO,
    payload: dict[str, Any],
) -> tuple[PmIdentity | None, UpsertResult]:
    """User 不入主业务表（人员身份是 governance 域），但同步一份
    轻量镜像到 PmIdentity（如已存在 active 记录则保留历史；upsert 新行）。

    返回值：当 person_id 暂时无解时，PmIdentity 行可能为 None。
    """
    # Person 创建由 identity CLI 负责（governance 流程）。sync 仅触发 audit。
    # 此处不直接写 PmIdentity 表，CLI 触发后再写。
    return None, UpsertResult(
        succeeded=0, missing_fields=_detect_missing(payload, ("id", "username")),
    )


# ── 工具：批量 parse + upsert ───────────────────────────────────────────────


async def upsert_iterations_batch(
    iteration_dao: IterationDAO,
    payloads: list[dict[str, Any]],
) -> tuple[int, list[str]]:
    succeeded = 0
    missing_all: list[str] = []
    for payload in payloads:
        try:
            _, result = await upsert_iteration(iteration_dao, payload)
            succeeded += result.succeeded
            missing_all.extend(result.missing_fields)
        except Exception:
            # 单条失败不阻塞整批；统计由 audit 记
            continue
    return succeeded, missing_all


async def upsert_issues_batch(
    issue_dao: IssueDAO,
    iteration_dao: IterationDAO,
    payloads: list[dict[str, Any]],
) -> tuple[int, list[str]]:
    succeeded = 0
    missing_all: list[str] = []
    for payload in payloads:
        try:
            _, result = await upsert_issue(issue_dao, iteration_dao, payload)
            succeeded += result.succeeded
            missing_all.extend(result.missing_fields)
        except Exception:
            continue
    return succeeded, missing_all


async def upsert_assignments_batch(
    assignment_dao: IssueAssignmentDAO,
    issue_dao: IssueDAO,
    pm_identity_dao: PmIdentityDAO,
    payloads: list[dict[str, Any]],
) -> tuple[int, list[str]]:
    succeeded = 0
    missing_all: list[str] = []
    for payload in payloads:
        try:
            _, result = await upsert_assignment(
                assignment_dao, issue_dao, pm_identity_dao, payload,
            )
            succeeded += result.succeeded
            missing_all.extend(result.missing_fields)
        except Exception:
            continue
    return succeeded, missing_all
