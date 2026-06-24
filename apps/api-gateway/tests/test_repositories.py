"""Tests for repositories router — Pydantic validation + POST /sync endpoint."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from api_gateway.dependencies import get_db
from api_gateway.main import app
from api_gateway.routers.repositories import UpdateRepositoryIn
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError


class TestUpdateRepositoryInCloneUrl:
    """clone_url field must be https:// or None/empty."""

    def test_https_url_accepted(self):
        m = UpdateRepositoryIn(clone_url="https://gitlab.example.com/org/repo.git")
        assert m.clone_url == "https://gitlab.example.com/org/repo.git"

    def test_http_url_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            UpdateRepositoryIn(clone_url="http://gitlab.example.com/org/repo.git")
        assert "https" in str(exc_info.value).lower()

    def test_ssh_url_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            UpdateRepositoryIn(clone_url="ssh://git@gitlab.example.com/org/repo.git")
        assert "https" in str(exc_info.value).lower()

    def test_git_at_syntax_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            UpdateRepositoryIn(clone_url="git@gitlab.example.com:org/repo.git")
        assert "https" in str(exc_info.value).lower()

    def test_file_url_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            UpdateRepositoryIn(clone_url="file:///tmp/local-repo")
        assert "https" in str(exc_info.value).lower()

    def test_empty_string_accepted(self):
        m = UpdateRepositoryIn(clone_url="")
        assert m.clone_url == ""

    def test_none_accepted(self):
        m = UpdateRepositoryIn(clone_url=None)
        assert m.clone_url is None


REPO_ID = uuid.UUID("84b52da7-e57e-41db-9813-066729bfd299")


def _mock_db_with_repo(
    *,
    clone_url: str = "https://gitlab.example.com/org/repo.git",
    access_token: str | None = None,
    repo_exists: bool = True,
):
    """Build a mock AsyncSession with RepositoryDAO that returns a fake repo."""
    fake_repo = MagicMock()
    fake_repo.repository_id = REPO_ID
    fake_repo.clone_url = clone_url
    fake_repo.access_token = access_token

    class _MockRepoDAO:
        def __init__(self, db):
            self._db = db

        async def get_by_id(self, repository_id):
            return fake_repo if repo_exists else None

    class _MockSettingDAO:
        def __init__(self, db):
            self._db = db

        async def get_value(self, key, default=None):
            return "/tmp/devmanager/repos"

    db = MagicMock()
    db.bind = MagicMock()
    db.bind.dialect.name = "sqlite"  # skip PG advisory lock in tests
    return db


@pytest.mark.asyncio
async def test_sync_repository_success(monkeypatch):
    """POST /sync with valid clone_url returns 200 and ok=true."""
    db = _mock_db_with_repo()

    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    try:

        def fake_clone_or_fetch(clone_url, repo_dir, access_token=None):
            return None  # success

        monkeypatch.setattr(
            "api_gateway.routers.repositories.clone_or_fetch_sync",
            fake_clone_or_fetch,
        )

        # Mock the DAOs at the module level so the endpoint uses mocks, not real DB.
        from api_gateway.routers import repositories as repo_module

        fake_repo = MagicMock()
        fake_repo.repository_id = REPO_ID
        fake_repo.clone_url = "https://gitlab.example.com/org/repo.git"
        fake_repo.access_token = None

        class _FakeRepoDAO:
            def __init__(self, _db):
                pass

            async def get_by_id(self, repository_id):
                return fake_repo

        class _FakeSettingDAO:
            def __init__(self, _db):
                pass

            async def get_value(self, key, default=None):
                return "/tmp/devmanager/repos"

        monkeypatch.setattr(repo_module, "RepositoryDAO", _FakeRepoDAO)
        monkeypatch.setattr(repo_module, "SettingDAO", _FakeSettingDAO)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            r = await ac.post(f"/v1/repositories/{REPO_ID}/sync")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["ok"] is True
        assert "elapsed_sec" in data
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_sync_repository_404_when_not_found(monkeypatch):
    """POST /sync on a non-existent repository returns 404."""

    db = MagicMock()
    db.bind = MagicMock()
    db.bind.dialect.name = "sqlite"

    class _RepoDAOMissing:
        def __init__(self, _db):
            pass

        async def get_by_id(self, repository_id):
            return None

    monkeypatch.setattr("api_gateway.routers.repositories.RepositoryDAO", _RepoDAOMissing)

    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            r = await ac.post(f"/v1/repositories/{REPO_ID}/sync")
        assert r.status_code == 404
        body = r.json()
        assert body["error_code"] == "NOT_FOUND"
        assert "not found" in body["message"].lower()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_sync_repository_422_when_clone_url_not_https(monkeypatch):
    """POST /sync rejects non-https clone_url (defense in depth, also covered by Pydantic)."""

    db = MagicMock()
    db.bind = MagicMock()
    db.bind.dialect.name = "sqlite"

    fake_repo = MagicMock()
    fake_repo.repository_id = REPO_ID
    fake_repo.clone_url = "ssh://git@gitlab.example.com/org/repo.git"
    fake_repo.access_token = None

    class _RepoDAOWithSsh:
        def __init__(self, _db):
            pass

        async def get_by_id(self, repository_id):
            return fake_repo

    monkeypatch.setattr("api_gateway.routers.repositories.RepositoryDAO", _RepoDAOWithSsh)

    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            r = await ac.post(f"/v1/repositories/{REPO_ID}/sync")
        assert r.status_code == 422
        body = r.json()
        assert body["error_code"] in ("VALIDATION_ERROR", "ERROR")
        assert "https" in body["message"].lower()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_sync_repository_502_on_git_error(monkeypatch):
    """POST /sync returns 502 with stderr detail when git fails."""
    from devmanager_git.fetcher import GitError

    db = MagicMock()
    db.bind = MagicMock()
    db.bind.dialect.name = "sqlite"

    fake_repo = MagicMock()
    fake_repo.repository_id = REPO_ID
    fake_repo.clone_url = "https://gitlab.example.com/org/repo.git"
    fake_repo.access_token = None

    class _RepoDAOOk:
        def __init__(self, _db):
            pass

        async def get_by_id(self, repository_id):
            return fake_repo

    class _SettingDAOOk:
        def __init__(self, _db):
            pass

        async def get_value(self, key, default=None):
            return "/tmp/devmanager/repos"

    monkeypatch.setattr("api_gateway.routers.repositories.RepositoryDAO", _RepoDAOOk)
    monkeypatch.setattr("api_gateway.routers.repositories.SettingDAO", _SettingDAOOk)

    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    try:

        def fake_sync_that_fails(clone_url, repo_dir, access_token=None):
            raise GitError("git fetch failed: fatal: unable to update url base")

        monkeypatch.setattr(
            "api_gateway.routers.repositories.clone_or_fetch_sync",
            fake_sync_that_fails,
        )
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            r = await ac.post(f"/v1/repositories/{REPO_ID}/sync")
        assert r.status_code == 502
        body = r.json()
        assert body["error_code"] == "ERROR"
        assert "git sync failed" in body["message"]
        assert "url base" in body["message"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_sync_repository_stderr_truncated_to_8kb(monkeypatch):
    """POST /sync truncates stderr to 8KB and appends marker."""
    from devmanager_git.fetcher import GitError

    db = MagicMock()
    db.bind = MagicMock()
    db.bind.dialect.name = "sqlite"

    fake_repo = MagicMock()
    fake_repo.repository_id = REPO_ID
    fake_repo.clone_url = "https://gitlab.example.com/org/repo.git"
    fake_repo.access_token = None

    class _RepoDAOOk:
        def __init__(self, _db):
            pass

        async def get_by_id(self, repository_id):
            return fake_repo

    class _SettingDAOOk:
        def __init__(self, _db):
            pass

        async def get_value(self, key, default=None):
            return "/tmp/devmanager/repos"

    monkeypatch.setattr("api_gateway.routers.repositories.RepositoryDAO", _RepoDAOOk)
    monkeypatch.setattr("api_gateway.routers.repositories.SettingDAO", _SettingDAOOk)

    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        huge_stderr = "x" * 20_000

        def fake_sync_huge_stderr(clone_url, repo_dir, access_token=None):
            raise GitError(huge_stderr)

        monkeypatch.setattr(
            "api_gateway.routers.repositories.clone_or_fetch_sync",
            fake_sync_huge_stderr,
        )
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            r = await ac.post(f"/v1/repositories/{REPO_ID}/sync")
        assert r.status_code == 502
        body = r.json()
        message = body["message"]
        assert "truncated" in message
        assert len(message) < 12_000  # 8KB + overhead
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_sync_repository_409_on_concurrent_same_repo(monkeypatch):
    """A second sync on the same repository while first is in progress → 409."""
    import asyncio as _asyncio

    db = MagicMock()
    db.bind = MagicMock()
    db.bind.dialect.name = "sqlite"

    fake_repo = MagicMock()
    fake_repo.repository_id = REPO_ID
    fake_repo.clone_url = "https://gitlab.example.com/org/repo.git"
    fake_repo.access_token = None

    class _RepoDAOOk:
        def __init__(self, _db):
            pass

        async def get_by_id(self, repository_id):
            return fake_repo

    class _SettingDAOOk:
        def __init__(self, _db):
            pass

        async def get_value(self, key, default=None):
            return "/tmp/devmanager/repos"

    monkeypatch.setattr("api_gateway.routers.repositories.RepositoryDAO", _RepoDAOOk)
    monkeypatch.setattr("api_gateway.routers.repositories.SettingDAO", _SettingDAOOk)

    started = _asyncio.Event()
    release = _asyncio.Event()
    main_loop = _asyncio.get_running_loop()

    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db

    # Reset module-level lock dict between tests
    import api_gateway.routers.repositories as repo_mod

    repo_mod._REPO_SYNC_LOCKS.clear()
    try:

        def slow_sync(clone_url, repo_dir, access_token=None):
            # Block the worker thread until the test releases the event.
            # asyncio.Event.wait() must be driven by the event loop, so we
            # schedule its coroutine on the main loop and block the thread.
            started.set()
            fut = _asyncio.run_coroutine_threadsafe(release.wait(), main_loop)
            fut.result(timeout=5)
            return None

        monkeypatch.setattr(
            "api_gateway.routers.repositories.clone_or_fetch_sync",
            slow_sync,
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            # Launch first sync (background, will block)
            task1 = _asyncio.create_task(ac.post(f"/v1/repositories/{REPO_ID}/sync"))
            # Wait for the first to enter the lock
            await _asyncio.wait_for(started.wait(), timeout=2)

            # Second sync should be rejected
            r2 = await ac.post(f"/v1/repositories/{REPO_ID}/sync")
            assert r2.status_code == 409
            assert "in progress" in r2.json()["message"].lower()

            # Release first; it should succeed
            release.set()
            r1 = await task1
            assert r1.status_code == 200
    finally:
        app.dependency_overrides.clear()
        repo_mod._REPO_SYNC_LOCKS.clear()
