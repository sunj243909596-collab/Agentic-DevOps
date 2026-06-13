"""DTO parsing tests — 缺字段降级 + 未知字段忽略。"""

from __future__ import annotations

from datetime import date

import pytest
from devmanager_pm_integration.models.dto import (
    IssueAssignmentDTO,
    IssueDTO,
    IterationDTO,
    PaginatedResponse,
    UserDTO,
)
from pydantic import ValidationError

# ── IterationDTO ─────────────────────────────────────────────────────────────


def test_iteration_dto_full_payload() -> None:
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
    assert dto.id == "pm-it-1"
    assert dto.start_date == date(2026, 6, 1)
    assert dto.status == "active"
    assert dto.created_at is not None


def test_iteration_dto_missing_optional_fields() -> None:
    """缺 created_at/updated_at → None，不抛错。"""
    dto = IterationDTO.model_validate(
        {
            "id": "pm-it-2",
            "name": "Sprint 2",
            "start_date": "2026-06-01",
            "end_date": "2026-06-14",
            "status": "planning",
        }
    )
    assert dto.created_at is None
    assert dto.updated_at is None


def test_iteration_dto_ignores_extra_fields() -> None:
    """PM 平台多塞字段进来不破坏解析。"""
    dto = IterationDTO.model_validate(
        {
            "id": "pm-it-3",
            "name": "S",
            "start_date": "2026-06-01",
            "end_date": "2026-06-14",
            "status": "active",
            "goal": "ship something",  # 未知字段
            "owner_avatar": "https://...",  # 未知字段
        }
    )
    assert dto.id == "pm-it-3"


def test_iteration_dto_missing_required_field_raises() -> None:
    with pytest.raises(ValidationError):
        IterationDTO.model_validate(
            {
                "id": "pm-it-4",
                # name 缺失
                "start_date": "2026-06-01",
                "end_date": "2026-06-14",
                "status": "active",
            }
        )


# ── IssueDTO ─────────────────────────────────────────────────────────────────


def test_issue_dto_full_payload() -> None:
    dto = IssueDTO.model_validate(
        {
            "id": "100",
            "key": "WMS-100",
            "title": "Implement X",
            "type": "task",
            "priority": "high",
            "status": "in_progress",
            "estimate_hours": 8.5,
            "iteration_id": "pm-it-1",
            "created_at": "2026-05-01T00:00:00Z",
            "updated_at": "2026-06-01T00:00:00Z",
        }
    )
    assert dto.key == "WMS-100"
    assert dto.estimate_hours == 8.5
    assert dto.iteration_id == "pm-it-1"


def test_issue_dto_no_estimate_no_iteration() -> None:
    """estimate_hours / iteration_id 可空。"""
    dto = IssueDTO.model_validate(
        {
            "id": "101",
            "key": "WMS-101",
            "title": "T",
            "type": "bug",
            "priority": "urgent",
            "status": "open",
        }
    )
    assert dto.estimate_hours is None
    assert dto.iteration_id is None


# ── IssueAssignmentDTO ───────────────────────────────────────────────────────


def test_assignment_dto_default_weight() -> None:
    dto = IssueAssignmentDTO.model_validate(
        {
            "issue_id": "100",
            "user_id": "u-1",
            "role": "assignee",
        }
    )
    assert dto.weight == 1.0
    assert dto.username is None


def test_assignment_dto_with_username_and_weight() -> None:
    dto = IssueAssignmentDTO.model_validate(
        {
            "issue_id": "100",
            "user_id": "u-1",
            "username": "alice",
            "role": "assignee",
            "weight": 0.5,
        }
    )
    assert dto.username == "alice"
    assert dto.weight == 0.5


# ── UserDTO ──────────────────────────────────────────────────────────────────


def test_user_dto_minimal() -> None:
    dto = UserDTO.model_validate({"id": "u-1", "username": "alice", "display_name": "Alice"})
    assert dto.email is None
    assert dto.status == "active"


# ── PaginatedResponse ────────────────────────────────────────────────────────


def test_paginated_response_default() -> None:
    pr = PaginatedResponse()
    assert pr.items == []
    assert pr.next_cursor is None


def test_paginated_response_cursor() -> None:
    pr = PaginatedResponse.model_validate(
        {
            "items": [{"x": 1}],
            "next_cursor": "abc",
        }
    )
    assert len(pr.items) == 1
    assert pr.next_cursor == "abc"
