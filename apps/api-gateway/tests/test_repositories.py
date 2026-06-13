"""Tests for repositories router — Pydantic validation."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

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