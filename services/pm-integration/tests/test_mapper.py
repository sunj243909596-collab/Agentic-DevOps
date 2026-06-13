"""DTO → ORM 字段映射测试。"""

from __future__ import annotations

from datetime import UTC, date, datetime

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


def test_iteration_to_orm_fields_maps_id_to_pm_iteration_id() -> None:
    dto = IterationDTO.model_validate(
        {
            "id": "pm-it-1",
            "name": "Sprint 1",
            "start_date": "2026-06-01",
            "end_date": "2026-06-14",
            "status": "active",
            "created_at": "2026-05-25T10:00:00Z",
            "updated_at": "2026-05-30T10:00:00Z",
        }
    )
    fields = iteration_to_orm_fields(dto)
    assert fields["pm_iteration_id"] == "pm-it-1"
    assert fields["name"] == "Sprint 1"
    assert fields["status"] == "active"
    assert fields["start_date"] == date(2026, 6, 1)
    assert fields["end_date"] == date(2026, 6, 14)
    assert fields["pm_created_at"] == datetime(2026, 5, 25, 10, 0, 0, tzinfo=UTC)
    assert "last_synced_at" not in fields  # DAO 内部设置


def test_iteration_to_orm_fields_missing_timestamps_become_none() -> None:
    """缺 created_at/updated_at 时 ORM 字段为 None（缺字段降级）。"""
    dto = IterationDTO.model_validate(
        {
            "id": "pm-it-2",
            "name": "Sprint 2",
            "start_date": "2026-06-01",
            "end_date": "2026-06-14",
            "status": "planning",
        }
    )
    fields = iteration_to_orm_fields(dto)
    assert fields["pm_created_at"] is None
    assert fields["pm_updated_at"] is None


def test_iteration_no_last_synced_at_in_mapper() -> None:
    """last_synced_at 由 DAO 内部统一设置，mapper 不应输出。"""
    dto = IterationDTO.model_validate(
        {
            "id": "x",
            "name": "x",
            "start_date": "2026-06-01",
            "end_date": "2026-06-14",
            "status": "active",
        }
    )
    fields = iteration_to_orm_fields(dto)
    assert "last_synced_at" not in fields


def test_issue_to_orm_fields_does_not_resolve_iteration_id() -> None:
    """iteration_id 由 sync 层两阶段查表填，mapper 只透传 None。"""
    dto = IssueDTO.model_validate(
        {
            "id": "100",
            "key": "WMS-100",
            "title": "T",
            "type": "task",
            "priority": "high",
            "status": "open",
            "estimate_hours": 4.0,
            "iteration_id": "pm-it-1",  # str，sync 层负责转 UUID
        }
    )
    fields = issue_to_orm_fields(dto)
    assert "iteration_id" not in fields  # mapper 不解析
    assert fields["pm_issue_id"] == "100"
    assert fields["issue_key"] == "WMS-100"
    assert fields["issue_type"] == "task"  # type → issue_type
    assert fields["estimate_hours"] == 4.0


def test_issue_to_orm_fields_no_estimate() -> None:
    dto = IssueDTO.model_validate(
        {
            "id": "1",
            "key": "WMS-1",
            "title": "T",
            "type": "bug",
            "priority": "low",
            "status": "open",
        }
    )
    fields = issue_to_orm_fields(dto)
    assert fields["estimate_hours"] is None


def test_assignment_to_orm_fields_username_fallback_to_user_id() -> None:
    """username 缺省时回退到 user_id。"""
    dto = IssueAssignmentDTO.model_validate(
        {
            "issue_id": "100",
            "user_id": "u-1",
            "role": "assignee",
        }
    )
    fields = issue_assignment_to_orm_fields(dto)
    assert fields["pm_user_id"] == "u-1"
    assert fields["pm_username"] == "u-1"  # fallback
    assert fields["role"] == "assignee"


def test_assignment_to_orm_fields_with_username() -> None:
    dto = IssueAssignmentDTO.model_validate(
        {
            "issue_id": "100",
            "user_id": "u-1",
            "username": "alice",
            "role": "reporter",
            "weight": 0.3,
        }
    )
    fields = issue_assignment_to_orm_fields(dto)
    assert fields["pm_username"] == "alice"
    assert fields["weight"] == 0.3


def test_filter_known_fields_drops_unknown() -> None:
    fields = {
        "pm_iteration_id": "x",
        "name": "x",
        "start_date": date(2026, 1, 1),
        "unknown_extra": "should be dropped",
    }
    out = filter_known_fields(fields, entity="iteration")
    assert "unknown_extra" not in out
    assert "pm_iteration_id" in out


def test_filter_known_fields_unknown_entity_raises() -> None:
    with __import__("pytest").raises(ValueError, match="Unknown entity"):
        filter_known_fields({"x": 1}, entity="nonsense")
