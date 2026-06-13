from __future__ import annotations

import uuid

from devmanager_git.classifier import (
    compute_risk_tags,
    detect_language,
    is_generated,
    is_test_file,
    is_vendor,
)


def _parse_numstat(numstat: str) -> dict[str, tuple[int, int, bool]]:
    """Returns {file_path: (added, deleted, is_binary)}."""
    stats: dict[str, tuple[int, int, bool]] = {}
    for line in numstat.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t", 2)
        if len(parts) < 3:
            continue
        added_s, deleted_s, path = parts
        if added_s == "-" and deleted_s == "-":
            stats[path] = (0, 0, True)
        else:
            try:
                stats[path] = (int(added_s), int(deleted_s), False)
            except ValueError:
                continue
    return stats


def _parse_name_status(name_status: str) -> list[tuple[str, str, str | None]]:
    """Returns list of (status_code, file_path, previous_file_path|None)."""
    entries: list[tuple[str, str, str | None]] = []
    for line in name_status.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        code = parts[0]
        if code.startswith("R") or code.startswith("C"):
            # Rename or Copy: old_path\tnew_path
            if len(parts) >= 3:
                entries.append((code[0], parts[2], parts[1]))
            elif len(parts) == 2:
                entries.append((code[0], parts[1], None))
        elif len(parts) >= 2:
            entries.append((code, parts[1], None))
    return entries


_STATUS_MAP = {
    "A": "added",
    "M": "modified",
    "D": "deleted",
    "R": "renamed",
    "C": "copied",
    "T": "modified",  # type change
    "U": "modified",  # unmerged
}


def parse_diff(
    numstat: str,
    name_status: str,
    run_id: uuid.UUID,
    repository_full_name: str,
    baseline_sha: str,
    target_sha: str,
) -> list[dict]:
    stats = _parse_numstat(numstat)
    ns_entries = _parse_name_status(name_status)

    units: list[dict] = []
    for code, file_path, prev_path in ns_entries:
        added, deleted, binary = stats.get(file_path, (0, 0, False))
        # For renames, numstat may key by "old → new" or just new
        if prev_path and file_path not in stats:
            added, deleted, binary = stats.get(prev_path, (0, 0, False))

        lang = detect_language(file_path)
        gen = is_generated(file_path)
        vend = is_vendor(file_path)
        test = is_test_file(file_path)
        tags = compute_risk_tags(file_path, added, deleted, binary, gen, vend, test)

        units.append(
            {
                "change_unit_id": uuid.uuid4(),
                "run_id": run_id,
                "repository_full_name": repository_full_name,
                "file_path": file_path,
                "previous_file_path": prev_path,
                "change_type": _STATUS_MAP.get(code, "modified"),
                "language": lang,
                "added_lines": added,
                "deleted_lines": deleted,
                "is_binary": binary,
                "is_generated": gen,
                "is_vendor": vend,
                "is_test_file": test,
                "risk_tags": tags,
                "baseline_sha": baseline_sha,
                "target_sha": target_sha,
            }
        )
    return units
