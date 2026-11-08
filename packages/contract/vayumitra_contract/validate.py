"""JSON-Schema validation against ``schema/messages.schema.json``.

Usage::

    from vayumitra_contract.validate import validate, ValidationError
    validate(payload, "SensorReading")   # raises ValidationError on bad data

The schema file is located robustly whether the package is installed with
``pip install -e`` (source tree) or as a wheel.
"""
from __future__ import annotations

import functools
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema import ValidationError as _JsonSchemaValidationError

# Re-export so callers depend only on this module.
ValidationError = _JsonSchemaValidationError


@functools.lru_cache(maxsize=1)
def _schema_path() -> Path:
    """Find messages.schema.json by walking a few likely locations."""
    here = Path(__file__).resolve()
    candidates = [
        here.parent / "schema" / "messages.schema.json",          # inside package (wheel copy)
        here.parent.parent / "schema" / "messages.schema.json",   # packages/contract/schema (source)
        here.parent.parent.parent / "schema" / "messages.schema.json",
    ]
    for c in candidates:
        if c.is_file():
            return c
    raise FileNotFoundError(
        "messages.schema.json not found; looked in: "
        + ", ".join(str(c) for c in candidates)
    )


@functools.lru_cache(maxsize=1)
def _full_schema() -> dict:
    return json.loads(_schema_path().read_text(encoding="utf-8"))


@functools.lru_cache(maxsize=None)
def _validator_for(msg_type: str) -> Draft202012Validator:
    schema = _full_schema()
    if msg_type not in schema.get("$defs", {}):
        raise KeyError(f"unknown msg_type in contract: {msg_type!r}")
    # Build a sub-schema that still resolves $defs (siblings may reference each other).
    sub = {"$ref": f"#/$defs/{msg_type}", "$defs": schema["$defs"]}
    return Draft202012Validator(sub)


def validate(payload: Any, msg_type: str) -> None:
    """Validate ``payload`` against the ``msg_type`` sub-schema.

    Raises :class:`ValidationError` on the first problem.  Returns ``None`` on
    success.
    """
    _validator_for(msg_type).validate(payload)


def is_valid(payload: Any, msg_type: str) -> bool:
    """Non-raising variant."""
    try:
        validate(payload, msg_type)
        return True
    except (ValidationError, KeyError):
        return False


def iter_errors(payload: Any, msg_type: str) -> list[str]:
    """Return a list of human-readable error strings (empty if valid)."""
    v = _validator_for(msg_type)
    return [f"{'/'.join(str(p) for p in e.path) or '<root>'}: {e.message}"
            for e in v.iter_errors(payload)]
