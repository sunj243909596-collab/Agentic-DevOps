from __future__ import annotations

import pytest
from devmanager_db.daos.analysis_run import AnalysisRunDAO
from devmanager_db.daos.baseline import BaselineDAO
from devmanager_db.daos.repository import RepositoryDAO
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_repository_create_and_get(session: AsyncSession):
    dao = RepositoryDAO(session)
    repo = await dao.create(
        provider="github",
        full_name="test-org/test-repo",
        default_branch="main",
        owner_team="platform",
    )
    assert repo.repository_id is not None
    assert repo.full_name == "test-org/test-repo"

    fetched = await dao.get_by_id(repo.repository_id)
    assert fetched is not None
    assert fetched.full_name == "test-org/test-repo"


@pytest.mark.asyncio
async def test_repository_get_by_full_name(session: AsyncSession):
    dao = RepositoryDAO(session)
    await dao.create(provider="github", full_name="test-org/repo-lookup")
    found = await dao.get_by_full_name("test-org/repo-lookup")
    assert found is not None
    assert found.provider == "github"


@pytest.mark.asyncio
async def test_repository_not_found_returns_none(session: AsyncSession):
    dao = RepositoryDAO(session)
    import uuid

    result = await dao.get_by_id(uuid.uuid4())
    assert result is None


@pytest.mark.asyncio
async def test_analysis_run_create_and_status_update(session: AsyncSession):
    repo_dao = RepositoryDAO(session)
    run_dao = AnalysisRunDAO(session)

    repo = await repo_dao.create(provider="github", full_name="test-org/run-repo")
    run = await run_dao.create(
        repository_id=repo.repository_id,
        repository_full_name=repo.full_name,
        trigger_type="manual",
        target_branch="main",
        baseline_sha="abc1234",
        target_sha="def5678",
        status="trigger_received",
        policy_version="v1",
        scoring_version="v1",
    )
    assert run.run_id is not None
    assert run.status == "trigger_received"

    updated = await run_dao.update_status(run.run_id, "authorized")
    assert updated is not None
    assert updated.status == "authorized"
    assert updated.completed_at is None

    completed = await run_dao.update_status(run.run_id, "completed")
    assert completed.completed_at is not None


@pytest.mark.asyncio
async def test_analysis_run_failed_run_has_failure_reason(session: AsyncSession):
    repo_dao = RepositoryDAO(session)
    run_dao = AnalysisRunDAO(session)

    repo = await repo_dao.create(provider="github", full_name="test-org/fail-repo")
    run = await run_dao.create(
        repository_id=repo.repository_id,
        repository_full_name=repo.full_name,
        trigger_type="manual",
        target_branch="main",
        baseline_sha="aaa1111",
        target_sha="bbb2222",
        status="trigger_received",
        policy_version="v1",
        scoring_version="v1",
    )
    failed = await run_dao.update_status(run.run_id, "failed", failure_reason="git fetch timed out")
    assert failed.status == "failed"
    assert failed.failure_reason == "git fetch timed out"


@pytest.mark.asyncio
async def test_baseline_upsert_and_get(session: AsyncSession):
    repo_dao = RepositoryDAO(session)
    run_dao = AnalysisRunDAO(session)
    baseline_dao = BaselineDAO(session)

    repo = await repo_dao.create(provider="github", full_name="test-org/baseline-repo")
    run = await run_dao.create(
        repository_id=repo.repository_id,
        repository_full_name=repo.full_name,
        trigger_type="manual",
        target_branch="main",
        baseline_sha="000dead0",
        target_sha="abc12345",
        status="completed",
        policy_version="v1",
        scoring_version="v1",
    )

    baseline = await baseline_dao.upsert(
        repository_id=repo.repository_id,
        branch="main",
        last_successful_sha="abc12345",
        run_id=run.run_id,
    )
    assert baseline.last_successful_sha == "abc12345"

    fetched = await baseline_dao.get(repo.repository_id, "main")
    assert fetched is not None
    assert fetched.last_successful_sha == "abc12345"


@pytest.mark.asyncio
async def test_baseline_upsert_updates_sha(session: AsyncSession):
    repo_dao = RepositoryDAO(session)
    baseline_dao = BaselineDAO(session)

    repo = await repo_dao.create(provider="github", full_name="test-org/baseline-update-repo")

    await baseline_dao.upsert(
        repository_id=repo.repository_id,
        branch="main",
        last_successful_sha="aaa1111",
    )
    updated = await baseline_dao.upsert(
        repository_id=repo.repository_id,
        branch="main",
        last_successful_sha="bbb2222",
    )
    assert updated.last_successful_sha == "bbb2222"


@pytest.mark.asyncio
async def test_baseline_not_found_returns_none(session: AsyncSession):
    repo_dao = RepositoryDAO(session)
    baseline_dao = BaselineDAO(session)

    repo = await repo_dao.create(provider="github", full_name="test-org/no-baseline-repo")
    result = await baseline_dao.get(repo.repository_id, "nonexistent-branch")
    assert result is None
