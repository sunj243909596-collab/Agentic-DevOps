from __future__ import annotations

import uuid

from devmanager_git.differ import parse_diff

_RUN_ID = uuid.uuid4()
_REPO = "test-org/test-repo"
_BASE_SHA = "aaa1111"
_TARGET_SHA = "bbb2222"


def test_parse_diff_added_file():
    numstat = "10\t0\tsrc/new_file.py\n"
    name_status = "A\tsrc/new_file.py\n"
    units = parse_diff(numstat, name_status, _RUN_ID, _REPO, _BASE_SHA, _TARGET_SHA)
    assert len(units) == 1
    u = units[0]
    assert u["file_path"] == "src/new_file.py"
    assert u["change_type"] == "added"
    assert u["added_lines"] == 10
    assert u["deleted_lines"] == 0
    assert not u["is_binary"]
    assert u["language"] == "python"


def test_parse_diff_modified_file():
    numstat = "5\t3\tapp/main.ts\n"
    name_status = "M\tapp/main.ts\n"
    units = parse_diff(numstat, name_status, _RUN_ID, _REPO, _BASE_SHA, _TARGET_SHA)
    assert len(units) == 1
    assert units[0]["change_type"] == "modified"
    assert units[0]["language"] == "typescript"


def test_parse_diff_binary_file():
    numstat = "-\t-\tassets/logo.png\n"
    name_status = "M\tassets/logo.png\n"
    units = parse_diff(numstat, name_status, _RUN_ID, _REPO, _BASE_SHA, _TARGET_SHA)
    assert len(units) == 1
    assert units[0]["is_binary"]
    assert "binary" in units[0]["risk_tags"]


def test_parse_diff_renamed_file():
    numstat = "0\t0\tsrc/renamed.py\n"
    name_status = "R100\tsrc/old.py\tsrc/renamed.py\n"
    units = parse_diff(numstat, name_status, _RUN_ID, _REPO, _BASE_SHA, _TARGET_SHA)
    assert len(units) == 1
    assert units[0]["change_type"] == "renamed"
    assert units[0]["previous_file_path"] == "src/old.py"
    assert units[0]["file_path"] == "src/renamed.py"


def test_parse_diff_deleted_file():
    numstat = "0\t20\tsrc/old.py\n"
    name_status = "D\tsrc/old.py\n"
    units = parse_diff(numstat, name_status, _RUN_ID, _REPO, _BASE_SHA, _TARGET_SHA)
    assert len(units) == 1
    assert units[0]["change_type"] == "deleted"


def test_parse_diff_test_file_tagged():
    numstat = "15\t0\ttests/test_auth.py\n"
    name_status = "A\ttests/test_auth.py\n"
    units = parse_diff(numstat, name_status, _RUN_ID, _REPO, _BASE_SHA, _TARGET_SHA)
    assert units[0]["is_test_file"]
    assert "test" in units[0]["risk_tags"]


def test_parse_diff_large_change_tagged():
    numstat = "400\t200\tsrc/big.py\n"
    name_status = "M\tsrc/big.py\n"
    units = parse_diff(numstat, name_status, _RUN_ID, _REPO, _BASE_SHA, _TARGET_SHA)
    assert "large_change" in units[0]["risk_tags"]


def test_parse_diff_multiple_files():
    numstat = "5\t2\ta.py\n3\t1\tb.ts\n"
    name_status = "M\ta.py\nA\tb.ts\n"
    units = parse_diff(numstat, name_status, _RUN_ID, _REPO, _BASE_SHA, _TARGET_SHA)
    assert len(units) == 2


def test_parse_diff_empty():
    units = parse_diff("", "", _RUN_ID, _REPO, _BASE_SHA, _TARGET_SHA)
    assert units == []
