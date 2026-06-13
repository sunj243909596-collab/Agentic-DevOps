"""S4 P1 — Team Operations foundation DAO tests.

测试模式：与 test_daos.py 一致（直连 agent_devops，commit）。
每个测试用唯一 prefix 避免冲突 + 在测试末尾清理。
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from devmanager_db.daos.team_ops.gitlab_identity import GitlabIdentityDAO
from devmanager_db.daos.team_ops.person import PersonDAO
from devmanager_db.daos.team_ops.pm_identity import PmIdentityDAO
from devmanager_db.daos.team_ops.team import TeamDAO
from devmanager_db.daos.team_ops.team_membership import TeamMembershipDAO
from devmanager_db.models import (
    GitlabIdentity,
    Person,
    PmIdentity,
    Team,
    TeamMembership,
)
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

# ── Cleanup fixture ──────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def cleanup(session: AsyncSession) -> AsyncGenerator[None, None]:
    """Test-scoped cleanup. Tests must `yield` data they create; we wipe after."""
    yield
    # Reverse-FK order: identity → membership → person → team
    await session.execute(delete(GitlabIdentity))
    await session.execute(delete(PmIdentity))
    await session.execute(delete(TeamMembership))
    await session.execute(delete(Person))
    await session.execute(delete(Team))
    await session.commit()


# ── TeamDAO ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_team_create_and_get_by_id(session: AsyncSession, cleanup: None) -> None:
    dao = TeamDAO(session)
    suffix = uuid.uuid4().hex[:8]
    team = await dao.create(name=f"platform-team-{suffix}", description="platform")
    assert team.team_id is not None
    assert team.name == f"platform-team-{suffix}"

    fetched = await dao.get_by_id(team.team_id)
    assert fetched is not None
    assert fetched.description == "platform"


@pytest.mark.asyncio
async def test_team_get_by_name(session: AsyncSession, cleanup: None) -> None:
    dao = TeamDAO(session)
    suffix = uuid.uuid4().hex[:8]
    team = await dao.create(name=f"wms-team-{suffix}")
    found = await dao.get_by_name(f"wms-team-{suffix}")
    assert found is not None
    assert found.team_id == team.team_id


@pytest.mark.asyncio
async def test_team_get_by_name_missing_returns_none(session: AsyncSession, cleanup: None) -> None:
    dao = TeamDAO(session)
    assert await dao.get_by_name("nonexistent-team-xyz") is None


@pytest.mark.asyncio
async def test_team_list_all(session: AsyncSession, cleanup: None) -> None:
    dao = TeamDAO(session)
    suffix = uuid.uuid4().hex[:8]
    await dao.create(name=f"a-team-{suffix}")
    await dao.create(name=f"b-team-{suffix}")
    teams = await dao.list_all()
    names = [t.name for t in teams]
    assert f"a-team-{suffix}" in names
    assert f"b-team-{suffix}" in names


@pytest.mark.asyncio
async def test_team_update_description_and_clear(session: AsyncSession, cleanup: None) -> None:
    dao = TeamDAO(session)
    suffix = uuid.uuid4().hex[:8]
    team = await dao.create(name=f"upd-team-{suffix}", description="initial")

    await dao.update(team.team_id, description="updated")
    fetched = await dao.get_by_id(team.team_id)
    assert fetched is not None
    assert fetched.description == "updated"

    await dao.update(team.team_id, clear_description=True)
    fetched = await dao.get_by_id(team.team_id)
    assert fetched is not None
    assert fetched.description is None


@pytest.mark.asyncio
async def test_team_delete_returns_true_on_hit(session: AsyncSession, cleanup: None) -> None:
    dao = TeamDAO(session)
    suffix = uuid.uuid4().hex[:8]
    team = await dao.create(name=f"del-team-{suffix}")
    assert await dao.delete(team.team_id) is True
    assert await dao.get_by_id(team.team_id) is None


# ── PersonDAO ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_person_create_with_defaults(session: AsyncSession, cleanup: None) -> None:
    dao = PersonDAO(session)
    suffix = uuid.uuid4().hex[:8]
    person = await dao.create(display_name=f"Alice {suffix}", email=f"alice-{suffix}@example.com")
    assert person.status == "active"
    assert person.data_access_scope == "self"


@pytest.mark.asyncio
async def test_person_get_by_email(session: AsyncSession, cleanup: None) -> None:
    dao = PersonDAO(session)
    suffix = uuid.uuid4().hex[:8]
    email = f"bob-{suffix}@example.com"
    person = await dao.create(display_name=f"Bob {suffix}", email=email)
    found = await dao.get_by_email(email)
    assert found is not None
    assert found.person_id == person.person_id


@pytest.mark.asyncio
async def test_person_update_status_and_scope(session: AsyncSession, cleanup: None) -> None:
    dao = PersonDAO(session)
    suffix = uuid.uuid4().hex[:8]
    person = await dao.create(display_name=f"Carol {suffix}", email=f"carol-{suffix}@example.com")
    await dao.update(person.person_id, status="inactive", data_access_scope="team_lead")
    fetched = await dao.get_by_id(person.person_id)
    assert fetched is not None
    assert fetched.status == "inactive"
    assert fetched.data_access_scope == "team_lead"


@pytest.mark.asyncio
async def test_person_list_by_status(session: AsyncSession, cleanup: None) -> None:
    dao = PersonDAO(session)
    suffix = uuid.uuid4().hex[:8]
    p1 = await dao.create(
        display_name=f"X {suffix}", email=f"x-{suffix}@example.com", status="inactive"
    )
    _ = await dao.create(
        display_name=f"Y {suffix}", email=f"y-{suffix}@example.com", status="active"
    )
    inactives = await dao.list_by_status("inactive")
    ids = [p.person_id for p in inactives]
    assert p1.person_id in ids


# ── TeamMembershipDAO ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_membership_add_and_get(session: AsyncSession, cleanup: None) -> None:
    team_dao = TeamDAO(session)
    person_dao = PersonDAO(session)
    m_dao = TeamMembershipDAO(session)
    suffix = uuid.uuid4().hex[:8]

    team = await team_dao.create(name=f"t-{suffix}")
    person = await person_dao.create(display_name=f"D {suffix}", email=f"d-{suffix}@example.com")

    m = await m_dao.add(team_id=team.team_id, person_id=person.person_id, role="lead")
    assert m.role == "lead"
    assert m.left_at is None

    fetched = await m_dao.get(team.team_id, person.person_id)
    assert fetched is not None
    assert fetched.role == "lead"


@pytest.mark.asyncio
async def test_membership_update_role(session: AsyncSession, cleanup: None) -> None:
    team_dao = TeamDAO(session)
    person_dao = PersonDAO(session)
    m_dao = TeamMembershipDAO(session)
    suffix = uuid.uuid4().hex[:8]

    team = await team_dao.create(name=f"t2-{suffix}")
    person = await person_dao.create(display_name=f"E {suffix}", email=f"e-{suffix}@example.com")
    await m_dao.add(team_id=team.team_id, person_id=person.person_id, role="member")
    await m_dao.update_role(team.team_id, person.person_id, role="admin")
    fetched = await m_dao.get(team.team_id, person.person_id)
    assert fetched is not None
    assert fetched.role == "admin"


@pytest.mark.asyncio
async def test_membership_mark_left_and_active_filter(session: AsyncSession, cleanup: None) -> None:
    team_dao = TeamDAO(session)
    person_dao = PersonDAO(session)
    m_dao = TeamMembershipDAO(session)
    suffix = uuid.uuid4().hex[:8]

    team = await team_dao.create(name=f"t3-{suffix}")
    p1 = await person_dao.create(display_name=f"F {suffix}", email=f"f-{suffix}@example.com")
    p2 = await person_dao.create(display_name=f"G {suffix}", email=f"g-{suffix}@example.com")
    await m_dao.add(team_id=team.team_id, person_id=p1.person_id)
    await m_dao.add(team_id=team.team_id, person_id=p2.person_id)
    await m_dao.mark_left(team.team_id, p1.person_id)

    active = await m_dao.list_by_team(team.team_id, active_only=True)
    active_ids = [m.person_id for m in active]
    assert p1.person_id not in active_ids
    assert p2.person_id in active_ids

    all_m = await m_dao.list_by_team(team.team_id, active_only=False)
    all_ids = [m.person_id for m in all_m]
    assert p1.person_id in all_ids
    assert p2.person_id in all_ids


# ── GitlabIdentityDAO ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_gitlab_identity_map_and_get_active(session: AsyncSession, cleanup: None) -> None:
    person_dao = PersonDAO(session)
    g_dao = GitlabIdentityDAO(session)
    suffix = uuid.uuid4().hex[:8]

    person = await person_dao.create(display_name=f"H {suffix}", email=f"h-{suffix}@example.com")
    gid = await g_dao.map(
        person_id=person.person_id,
        gitlab_user_id=100 + abs(hash(suffix)) % 10000,
        gitlab_username=f"h_user_{suffix}",
    )
    assert gid.effective_to is None

    found = await g_dao.get_active_by_user_id(gid.gitlab_user_id)
    assert found is not None
    assert found.person_id == person.person_id


@pytest.mark.asyncio
async def test_gitlab_identity_deactivate_creates_history(
    session: AsyncSession, cleanup: None
) -> None:
    person_dao = PersonDAO(session)
    g_dao = GitlabIdentityDAO(session)
    suffix = uuid.uuid4().hex[:8]
    person = await person_dao.create(display_name=f"I {suffix}", email=f"i-{suffix}@example.com")
    gid = await g_dao.map(
        person_id=person.person_id,
        gitlab_user_id=200 + abs(hash(suffix)) % 10000,
        gitlab_username=f"i_user_{suffix}",
    )

    ok = await g_dao.deactivate(gid.identity_id)
    assert ok is True

    # 再次 deactivate 应该返回 False（已被 deactivate）
    assert await g_dao.deactivate(gid.identity_id) is False

    # 找不到 active 记录
    assert await g_dao.get_active_by_user_id(gid.gitlab_user_id) is None

    # 但 history 还在
    history = await g_dao.list_history_by_person(person.person_id)
    ids = [r.identity_id for r in history]
    assert gid.identity_id in ids


@pytest.mark.asyncio
async def test_gitlab_identity_duplicate_active_user_violates_unique(
    session: AsyncSession, cleanup: None
) -> None:
    """同一 gitlab_user_id 不允许同时有两条 active 记录。"""
    from sqlalchemy.exc import IntegrityError

    person_dao = PersonDAO(session)
    g_dao = GitlabIdentityDAO(session)
    suffix = uuid.uuid4().hex[:8]
    p1 = await person_dao.create(display_name=f"J {suffix}", email=f"j-{suffix}@example.com")
    p2 = await person_dao.create(display_name=f"K {suffix}", email=f"k-{suffix}@example.com")
    same_uid = 300 + abs(hash(suffix)) % 10000

    await g_dao.map(
        person_id=p1.person_id,
        gitlab_user_id=same_uid,
        gitlab_username=f"u1_{suffix}",
    )
    with pytest.raises(IntegrityError):
        await g_dao.map(
            person_id=p2.person_id,
            gitlab_user_id=same_uid,
            gitlab_username=f"u2_{suffix}",
        )
    await session.rollback()


# ── PmIdentityDAO ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pm_identity_map_and_get_active(session: AsyncSession, cleanup: None) -> None:
    person_dao = PersonDAO(session)
    p_dao = PmIdentityDAO(session)
    suffix = uuid.uuid4().hex[:8]
    person = await person_dao.create(display_name=f"L {suffix}", email=f"l-{suffix}@example.com")
    pid = await p_dao.map(
        person_id=person.person_id,
        pm_user_id=f"pm-{suffix}",
        pm_username=f"l_pm_{suffix}",
    )
    assert pid.effective_to is None
    found = await p_dao.get_active_by_user_id(f"pm-{suffix}")
    assert found is not None
    assert found.person_id == person.person_id


@pytest.mark.asyncio
async def test_pm_identity_deactivate(session: AsyncSession, cleanup: None) -> None:
    person_dao = PersonDAO(session)
    p_dao = PmIdentityDAO(session)
    suffix = uuid.uuid4().hex[:8]
    person = await person_dao.create(display_name=f"M {suffix}", email=f"m-{suffix}@example.com")
    pid = await p_dao.map(
        person_id=person.person_id,
        pm_user_id=f"pm2-{suffix}",
        pm_username=f"m_pm_{suffix}",
    )
    assert await p_dao.deactivate(pid.identity_id) is True
    assert await p_dao.get_active_by_user_id(f"pm2-{suffix}") is None


# ── Cross-DAO 集成测试 ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_full_workflow_create_team_add_member_map_identities(
    session: AsyncSession, cleanup: None
) -> None:
    """S4 P1 端到端：create team → add member → map gitlab → map pm → 全部链可查。"""
    team_dao = TeamDAO(session)
    person_dao = PersonDAO(session)
    m_dao = TeamMembershipDAO(session)
    g_dao = GitlabIdentityDAO(session)
    p_dao = PmIdentityDAO(session)
    suffix = uuid.uuid4().hex[:8]

    # 1. create team
    team = await team_dao.create(name=f"full-{suffix}", description="integration test team")
    # 2. create person
    person = await person_dao.create(
        display_name=f"Full User {suffix}",
        email=f"full-{suffix}@example.com",
        data_access_scope="team_lead",
    )
    # 3. add membership
    await m_dao.add(team_id=team.team_id, person_id=person.person_id, role="lead")
    # 4. map gitlab + pm
    uid = 400 + abs(hash(suffix)) % 10000
    gid = await g_dao.map(
        person_id=person.person_id,
        gitlab_user_id=uid,
        gitlab_username=f"full_gl_{suffix}",
    )
    pid = await p_dao.map(
        person_id=person.person_id,
        pm_user_id=f"pm-full-{suffix}",
        pm_username=f"full_pm_{suffix}",
    )

    # 5. 全部可查
    assert (await team_dao.get_by_id(team.team_id)) is not None
    assert (await person_dao.get_by_id(person.person_id)) is not None
    m = await m_dao.get(team.team_id, person.person_id)
    assert m is not None and m.role == "lead"
    gl = await g_dao.get_active_by_user_id(uid)
    assert gl is not None and gl.identity_id == gid.identity_id
    pm = await p_dao.get_active_by_user_id(f"pm-full-{suffix}")
    assert pm is not None and pm.identity_id == pid.identity_id
