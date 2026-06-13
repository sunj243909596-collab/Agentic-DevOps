from __future__ import annotations

from devmanager_agents.base import extract_json_array

# ── extract_json_array ────────────────────────────────────────────────────────


def test_extract_plain_json_array():
    text = '[{"category": "correctness", "severity": "high"}]'
    result = extract_json_array(text)
    assert len(result) == 1
    assert result[0]["category"] == "correctness"


def test_extract_markdown_fenced_json():
    text = '```json\n[{"category": "security"}]\n```'
    result = extract_json_array(text)
    assert len(result) == 1


def test_extract_empty_array():
    assert extract_json_array("[]") == []


def test_extract_invalid_returns_empty():
    assert extract_json_array("not json") == []


def test_extract_json_inside_prose():
    text = 'Here are the findings:\n[{"category": "testing", "severity": "low"}]\nEnd.'
    result = extract_json_array(text)
    assert len(result) == 1


def test_extract_single_object_wrapped_in_list():
    text = '{"category": "correctness", "severity": "medium"}'
    result = extract_json_array(text)
    assert len(result) == 1
