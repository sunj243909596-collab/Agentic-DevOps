"""familiarity_edge 重算（v1 简化版）。

数据源：change_units (已有) JOIN GitlabIdentity + Person。
逻辑：按 (person, language) 聚合 added_lines / deleted_lines / commits_count。
v2: 用 LLM 标注代码领域（path: / repo: 维度）。

注意：change_units.owner 是 GitLab username（str），与 Person.display_name 模糊匹配。
v2 应改用 gitlab_identity.gitlab_username 严格匹配。
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from devmanager_db.daos.team_ops.familiarity_edge import FamiliarityEdgeDAO
from devmanager_db.daos.team_ops.gitlab_identity import GitlabIdentityDAO
from devmanager_db.daos.team_ops.person import PersonDAO
from devmanager_db.models import ChangeUnit, GitlabIdentity, Person
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def recompute_familiarity(
    session: AsyncSession,
) -> dict[str, Any]:
    """重算 familiarity_edge 全表（v1 按 lang:<language> 聚合）。

    返回 stats：{ persons: int, edges: int, lines_total: int }
    """
    person_dao = PersonDAO(session)
    gl_dao = GitlabIdentityDAO(session)
    dao = FamiliarityEdgeDAO(session)

    persons = await person_dao.list_active()

    # person_id → gitlab_username（active）反向索引
    username_to_person: dict[str, uuid.UUID] = {}
    for p in persons:
        identities = await gl_dao.list_active_by_person(p.person_id)
        for ident in identities:
            if ident.gitlab_username:
                username_to_person[ident.gitlab_username.lower()] = p.person_id

    # 拉所有 change_units（按 author / language 聚合 v1 字段集）
    cols = (ChangeUnit.owner, ChangeUnit.language, ChangeUnit.added_lines, ChangeUnit.deleted_lines)
    result = await session.execute(select(*cols))
    rows = result.all()

    # 聚合: person_id × lang → (lines, commits)
    agg: dict[tuple[uuid.UUID, str], dict[str, int]] = defaultdict(
        lambda: {"lines": 0, "commits": 0}
    )
    stats = {"persons": 0, "edges": 0, "lines_total": 0}

    for owner, language, added, deleted in rows:
        if not owner or not language:
            continue
        person_id = username_to_person.get(owner.lower())
        if person_id is None:
            continue
        key = (person_id, f"lang:{language}")
        agg[key]["lines"] += int(added or 0) + int(deleted or 0)
        agg[key]["commits"] += 1  # v1 简化：1 row = 1 commit

    # 写入
    seen_persons: set[uuid.UUID] = set()
    for (person_id, area_key), data in agg.items():
        await dao.upsert(
            person_id=person_id,
            area_key=area_key,
            commits_count=data["commits"],
            lines_changed=data["lines"],
        )
        seen_persons.add(person_id)
        stats["edges"] += 1
        stats["lines_total"] += data["lines"]

    stats["persons"] = len(seen_persons)
    await session.commit()
    return stats


# suppress unused import (used in v2 JOIN Person directly)
_ = (Person, GitlabIdentity, datetime, UTC)
