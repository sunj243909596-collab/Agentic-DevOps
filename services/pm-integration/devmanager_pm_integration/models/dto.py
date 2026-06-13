"""PM 平台 API 原始响应的 Pydantic 模型。

设计原则：
- 字段名与 PM API 返回保持一致（不做 ORM 字段命名转换）
- 所有非必填字段 Optional + 默认 None
- 未知字段被静默忽略（extra='ignore'）—— PM 平台升级字段不破坏同步
- 类型尽量宽容（str 接收数字、None 替代空值）

A1 假设字段集：
- iteration: id, name, start_date, end_date, status
- issue: id, key, title, type, priority, estimate_hours, status,
  iteration_id, created_at, updated_at
- issue_assignment: issue_id, user_id, role, weight
- user: id, username, display_name, email, status
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class _BaseDTO(BaseModel):
    """所有 DTO 共用配置。"""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


# ── Iteration ────────────────────────────────────────────────────────────────


class IterationDTO(_BaseDTO):
    id: str
    name: str
    start_date: date
    end_date: date
    status: str  # 'planning' | 'active' | 'completed' | 'cancelled'
    created_at: datetime | None = None
    updated_at: datetime | None = None


# ── Issue ────────────────────────────────────────────────────────────────────


class IssueDTO(_BaseDTO):
    id: str
    key: str  # 如 "WMS-123"
    title: str
    type: str  # 'story' | 'task' | 'bug' | 'epic' | 'subtask'
    priority: str  # 'low' | 'medium' | 'high' | 'urgent'
    status: str
    estimate_hours: float | None = None
    iteration_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


# ── IssueAssignment ──────────────────────────────────────────────────────────


class IssueAssignmentDTO(_BaseDTO):
    issue_id: str
    user_id: str
    role: str  # 'assignee' | 'reporter' | 'watcher' | 'mentioned'
    weight: float = 1.0
    username: str | None = None  # PM 平台若返回则带上


# ── User ─────────────────────────────────────────────────────────────────────


class UserDTO(_BaseDTO):
    id: str
    username: str
    display_name: str
    email: str | None = None
    status: str = "active"


# ── 列表响应包装（PM 平台分页通用结构） ──────────────────────────────────────


class PaginatedResponse(BaseModel):
    """PM 平台 list 接口的通用分页结构。

    实际 PM 平台可能用 cursor 而非 offset。预留 model_config 让子类可覆盖。
    """

    model_config = ConfigDict(extra="ignore")

    items: list[dict[str, Any]] = []
    total: int | None = None
    page: int | None = None
    page_size: int | None = None
    next_cursor: str | None = None
