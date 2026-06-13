import re

from devmanager_agents.prompts import AGENT_SYSTEM_PROMPT


def test_prompt_lists_5_dimensions():
    for dim in ("correctness", "security", "testing", "maintainability", "performance"):
        assert dim in AGENT_SYSTEM_PROMPT, f"missing dimension: {dim}"


def test_prompt_mentions_6_evidence_ref_formats():
    for fmt in (
        "diff:{file}:{start}-{end}",
        "read:{file}:{start}-{end}",
        "grep:{file}:{line}",
        "knowledge:{chunk_id}",
        "rule:{rule_id}",
        "linter:{file}:{rule_id}",
    ):
        assert fmt in AGENT_SYSTEM_PROMPT, f"missing evidence_ref format: {fmt}"


def test_prompt_mandates_classify_change_first():
    classify_idx = AGENT_SYSTEM_PROMPT.find("**Classify**")
    getdiff_idx = AGENT_SYSTEM_PROMPT.find("GetDiff")
    assert classify_idx > 0 and getdiff_idx > 0
    assert classify_idx < getdiff_idx


def test_prompt_no_prescriptive_language():
    forbidden_en = re.compile(r"\b(should|must|recommend|ought|need\s+to)\b", re.IGNORECASE)
    forbidden_cn = re.compile(r"应该|必须|建议|推荐|应当|最好")
    assert not forbidden_en.search(AGENT_SYSTEM_PROMPT)
    assert not forbidden_cn.search(AGENT_SYSTEM_PROMPT)
