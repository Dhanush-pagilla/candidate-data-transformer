"""
projection.py
=============
project_to_output  — config-driven, non-mutating output projection.
validate_schema    — runtime type + presence enforcement.
"""
from __future__ import annotations
import re
import warnings
from typing import Any

from .merger import _is_honestly_empty

# ── Path expression patterns ──────────────────────────────────────────────
_RE_ARRAY_INDEX = re.compile(r"^(\w+)\[(\d+)\]$")
_RE_OBJ_EXPAND  = re.compile(r"^(\w+)\[\]\.(\w+)$")
_RE_E164_VALID  = re.compile(r"^\+?\d{7,15}$")


def _resolve_path(record: dict, expr: str) -> Any:
    """
    Resolve a path expression against the canonical record (read-only).

    Three forms:
      1. "full_name"       → plain key
      2. "emails[0]"       → array index (None-safe)
      3. "skills[].name"   → object expansion → flat list
    """
    m = _RE_OBJ_EXPAND.match(expr)
    if m:
        arr = record.get(m.group(1))
        if not isinstance(arr, list):
            return []
        return [item[m.group(2)] for item in arr
                if isinstance(item, dict) and m.group(2) in item]
    m = _RE_ARRAY_INDEX.match(expr)
    if m:
        arr = record.get(m.group(1))
        idx = int(m.group(2))
        if not isinstance(arr, list) or idx >= len(arr):
            return None
        return arr[idx]
    return record.get(expr)


def _apply_e164(value: Any) -> Any:
    def _scrub(raw: str) -> str:
        s = re.sub(r"[\s\-\.\(\)]", "", raw)
        if _RE_E164_VALID.match(s):
            return s
        warnings.warn(
            f"[project] E164: '{raw}' could not be verified. Returning scrubbed.",
            RuntimeWarning, stacklevel=4)
        return s
    if isinstance(value, list):
        return [_scrub(v) if isinstance(v, str) else v for v in value]
    if isinstance(value, str):
        return _scrub(value)
    return value


def _apply_canonical(value: Any) -> Any:
    if isinstance(value, list):
        return [v.strip().lower() if isinstance(v, str) else v for v in value]
    if isinstance(value, str):
        return value.strip().lower()
    return value


def project_to_output(canonical_record: dict, config: dict) -> dict:
    """
    Project the canonical record onto a consumer-specific shape.
    The canonical record is NEVER mutated.

    Config keys
    -----------
    fields[]         list of field rules (path, from, normalize, required)
    on_missing       "null" | "omit" | "error"
    include_confidence  bool (default True) — strip provenance + score when False
    """
    field_defs       = config.get("fields", [])
    global_on_missing = config.get("on_missing", "null").lower()
    include_confidence = config.get("include_confidence", True)

    output: dict = {}

    for fd in field_defs:
        out_key     = fd["path"]
        src_expr    = fd.get("from", out_key)
        norm_op     = fd.get("normalize", "").strip().upper()
        is_required = fd.get("required", False)
        allow_empty = fd.get("allow_empty", False)   # pass [] through as-is

        resolved = _resolve_path(canonical_record, src_expr)

        if not _is_honestly_empty(resolved):
            if norm_op == "E164":
                resolved = _apply_e164(resolved)
            elif norm_op == "CANONICAL":
                resolved = _apply_canonical(resolved)

        # allow_empty: an empty list is a valid result, not a missing value
        if allow_empty and isinstance(resolved, list):
            output[out_key] = resolved
            continue

        policy = "error" if is_required else global_on_missing

        if _is_honestly_empty(resolved):
            if policy == "omit":
                continue
            elif policy == "error":
                raise ValueError(
                    f"[project] Required field '{out_key}' (from '{src_expr}') "
                    f"is empty. Serialisation aborted."
                )
            else:
                output[out_key] = None
                continue

        output[out_key] = resolved

    if not include_confidence:
        _META = {"provenance", "overall_confidence"}
        for fd in field_defs:
            if fd.get("from", fd["path"]) in _META or fd["path"] in _META:
                output.pop(fd["path"], None)

    return output


def validate_schema(projected_data: dict, config: dict) -> bool:
    """
    Validate a projected record against config schema rules.
    Accumulates all failures before returning so every issue is visible.

    Supported type tokens: string, string[], int, float, bool, dict, list, any
    """
    field_defs        = config.get("fields", [])
    global_on_missing = config.get("on_missing", "null").lower()
    failures: list[str] = []

    for fd in field_defs:
        key          = fd["path"]
        dtype        = fd.get("type", "any").lower().strip()
        is_required  = fd.get("required", False)
        policy       = "error" if is_required else global_on_missing

        present = key in projected_data
        value   = projected_data.get(key)
        empty   = _is_honestly_empty(value)

        if not present or empty:
            if policy == "error":
                failures.append(
                    f"Field '{key}' is required but missing or empty.")
            continue

        if dtype == "any":
            pass
        elif dtype == "string":
            if not isinstance(value, str):
                failures.append(f"'{key}' expected string, got {type(value).__name__}.")
        elif dtype == "string[]":
            if not isinstance(value, list):
                failures.append(f"'{key}' expected string[], got {type(value).__name__}.")
            else:
                for i, el in enumerate(value):
                    if not isinstance(el, str):
                        failures.append(
                            f"'{key}[{i}]' expected str, got {type(el).__name__}.")
                        break
        elif dtype == "int":
            if not isinstance(value, int) or isinstance(value, bool):
                failures.append(f"'{key}' expected int, got {type(value).__name__}.")
        elif dtype == "float":
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                failures.append(f"'{key}' expected float, got {type(value).__name__}.")
        elif dtype == "bool":
            if not isinstance(value, bool):
                failures.append(f"'{key}' expected bool, got {type(value).__name__}.")
        elif dtype == "dict":
            if not isinstance(value, dict):
                failures.append(f"'{key}' expected dict, got {type(value).__name__}.")
        elif dtype == "list":
            if not isinstance(value, list):
                failures.append(f"'{key}' expected list, got {type(value).__name__}.")
        else:
            warnings.warn(
                f"[validate] Unknown type token '{dtype}' for '{key}'. Skipping.",
                RuntimeWarning, stacklevel=2)

    for msg in failures:
        warnings.warn(f"[validate] FAILURE — {msg}", UserWarning, stacklevel=2)

    return len(failures) == 0
