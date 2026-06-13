from __future__ import annotations

import pytest
from devmanager_db.schema_validator import assert_valid, validate

_VALID_FINDING = {
    "finding_id": "F-20240101-001",
    "run_id": "550e8400-e29b-41d4-a716-446655440000",
    "category": "security",
    "severity": "high",
    "confidence": 0.9,
    "repository": "test-org/test-repo",
    "commit_sha": "abc1234",
    "file": "src/auth/login.py",
    "start_line": 42,
    "end_line": 55,
    "observation": "SQL query built from user input without sanitization.",
    "impact": "Allows attacker to read or modify arbitrary database rows.",
    "recommendation": "Use parameterized queries or an ORM.",
    "verification": "Reproduce by passing `' OR 1=1--` as the username field.",
    "evidence_refs": ["diff:src/auth/login.py:42-55"],
    "status": "open",
}


def test_valid_finding_passes():
    errors = validate(_VALID_FINDING, "reviewer-finding")
    assert errors == []


def test_assert_valid_does_not_raise_on_valid():
    assert_valid(_VALID_FINDING, "reviewer-finding")


def test_missing_required_field_fails():
    bad = {**_VALID_FINDING}
    del bad["evidence_refs"]
    errors = validate(bad, "reviewer-finding")
    assert len(errors) > 0


def test_empty_evidence_refs_fails():
    bad = {**_VALID_FINDING, "evidence_refs": []}
    errors = validate(bad, "reviewer-finding")
    assert len(errors) > 0


def test_invalid_finding_id_pattern_fails():
    bad = {**_VALID_FINDING, "finding_id": "INVALID-ID"}
    errors = validate(bad, "reviewer-finding")
    assert len(errors) > 0


def test_confidence_out_of_range_fails():
    bad = {**_VALID_FINDING, "confidence": 1.5}
    errors = validate(bad, "reviewer-finding")
    assert len(errors) > 0


def test_invalid_severity_fails():
    bad = {**_VALID_FINDING, "severity": "catastrophic"}
    errors = validate(bad, "reviewer-finding")
    assert len(errors) > 0


def test_assert_valid_raises_on_invalid():
    bad = {**_VALID_FINDING, "evidence_refs": []}
    with pytest.raises(Exception):
        assert_valid(bad, "reviewer-finding")
