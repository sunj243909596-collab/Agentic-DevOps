"""Helpers for parsing JSON arrays from LLM responses.

Kept after the BaseReviewer removal (plan 7.10.2 follow-up, 2026-06-11):
``extract_json_array`` is still used by ``agent_reviewer.py`` to parse the
final findings JSON returned by the unified agent loop.
"""
from __future__ import annotations

import json
import re


def extract_json_array(text: str) -> list[dict]:
    # Strip markdown fences if present
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = re.sub(r"```\s*$", "", text, flags=re.MULTILINE).strip()
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            return [data]
    except json.JSONDecodeError:
        # Try to find JSON array inside the text
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
                if isinstance(data, list):
                    return [item for item in data if isinstance(item, dict)]
            except json.JSONDecodeError:
                pass
    return []
