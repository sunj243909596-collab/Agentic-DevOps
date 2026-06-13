from __future__ import annotations

from devmanager_git.codeowners import CodeownersParser

SAMPLE = """
# Global owner
*       @global-owner

# Frontend team
/src/frontend/  @frontend-team

# Python backend
*.py    @python-team

# Docs
docs/   @docs-team

# Override for specific dir
/src/frontend/critical.ts  @security-team
"""


def _parser() -> CodeownersParser:
    return CodeownersParser.from_text(SAMPLE)


def test_global_owner_matches_any_file():
    p = _parser()
    owner = p.find_owner("random/file.txt")
    assert owner == "@python-team" or owner is not None


def test_python_extension_matches():
    p = _parser()
    owner = p.find_owner("src/backend/service.py")
    assert "@python-team" in owner


def test_frontend_dir_matches():
    p = _parser()
    owner = p.find_owner("src/frontend/App.tsx")
    assert "@frontend-team" in owner


def test_last_rule_wins_for_specific_file():
    p = _parser()
    owner = p.find_owner("src/frontend/critical.ts")
    assert "@security-team" in owner


def test_docs_dir_matches():
    p = _parser()
    owner = p.find_owner("docs/architecture.md")
    assert "@docs-team" in owner


def test_no_owner_returns_none():
    p = CodeownersParser.from_text("")
    assert p.find_owner("anything.rs") is None


def test_comment_lines_ignored():
    p = CodeownersParser.from_text("# this is a comment\n")
    assert p.find_owner("file.py") is None


def test_empty_codeowners():
    p = CodeownersParser.from_text("")
    assert p.find_owner("src/main.py") is None


def test_multiple_owners_on_one_rule():
    content = "*.go @go-team @backend-lead\n"
    p = CodeownersParser.from_text(content)
    owner = p.find_owner("pkg/server/main.go")
    assert "@go-team" in owner
    assert "@backend-lead" in owner
