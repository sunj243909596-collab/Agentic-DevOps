from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema

_SCHEMAS_DIR = Path(__file__).parent.parent.parent / "contracts/schemas"


def _load_schema(name: str) -> dict:
    path = _SCHEMAS_DIR / f"{name}.schema.json"
    if not path.exists():
        raise FileNotFoundError(f"Schema not found: {path}")
    with path.open() as f:
        return json.load(f)


def validate(data: dict[str, Any], schema_name: str) -> list[str]:
    """Validate *data* against *schema_name*.schema.json.

    Returns a list of error messages; empty list means valid.
    """
    schema = _load_schema(schema_name)
    validator = jsonschema.Draft202012Validator(schema)
    return [e.message for e in validator.iter_errors(data)]


def assert_valid(data: dict[str, Any], schema_name: str) -> None:
    """Validate and raise ValidationError on first failure."""
    schema = _load_schema(schema_name)
    jsonschema.validate(data, schema, cls=jsonschema.Draft202012Validator)
