"""Tests for repositories router — Pydantic validation + POST /sync endpoint."""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from api_gateway.dependencies import get_db
from api_gateway.main import app
from api_gateway.routers.repositories import UpdateRepositoryIn


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


def _mock_db_with_repo(*, clone_url: str = "https://gitlab.example.com/org/repo.git",
                       access_token: str | None = None,
                       repo_exists: bool = True):
    """Build a mock AsyncSession with RepositoryDAO that returns a fake repo."""
    fake_repo = MagicMock()
    fake_repo.repository_id = REPO_ID
    fake_repo.clone_url = clone_url
    fake_repo.access_token = access_token

    class _MockRepoDAO:
        def __init__(self, db): self._db = db
        async def get_by_id(self, repository_id):
            return fake_repo if repo_exists else None

    class _MockSettingDAO:
        def __init__(self, db): self._db = db
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
            def __init__(self, _db): pass
            async def get_by_id(self, repository_id):
                return fake_repo

        class _FakeSettingDAO:
            def __init__(self, _db): pass
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