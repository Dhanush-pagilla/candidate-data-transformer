"""Skill canonicalisation — three levels: basic, dedup+junk-filter, compound-expand."""
from __future__ import annotations
import re
from typing import Any

_SKILL_JUNK: set[str] = {"n/a", "na", "none", "null", "-", "other", ""}
_ALIASES:    dict[str, str] = {"py": "python", "js": "javascript"}


def _canonicalize_skills(raw: Any) -> list[str]:
    """Basic: lowercase + strip.  Duplicates preserved (merger deduplicates later)."""
    if raw is None:
        return []
    if not isinstance(raw, list):
        if isinstance(raw, str) and raw.strip():
            raw = [s.strip() for s in raw.split(",")]
        else:
            return []
    result: list[str] = []
    for item in raw:
        if not isinstance(item, (str, int, float)):
            continue
        token = str(item).strip().lower()
        if token:
            result.append(token)
    return result


def _canonicalize_and_dedupe_skills(raw: Any) -> list[str]:
    """
    Lowercase + strip + dedup + junk-filter + alias resolution.
    Insertion-order-preserving; first occurrence wins.
    """
    if not isinstance(raw, list):
        if isinstance(raw, str) and raw.strip():
            raw = [s.strip() for s in raw.split(",")]
        else:
            return []
    seen: set[str] = set()
    result: list[str] = []
    for item in raw:
        if item is None:
            continue
        token = str(item).strip().lower()
        if not token or token in _SKILL_JUNK:
            continue
        token = _ALIASES.get(token, token)
        if token not in seen:
            seen.add(token)
            result.append(token)
    return result


def _canonicalize_skills_expanded(raw: list) -> list[str]:
    """
    Full normalisation for resume skill lists:
      • "HTML + CSS"         → ["html", "css"]       (split on ' + ')
      • "HTML+CSS"           → ["html", "css"]       (split on '+')
      • "MongoDB (BASIC)"    → "mongodb"             (strip qualifier)
      • "Data Structures & Algorithms (INTERMEDIATE)"→ "data structures & algorithms"
      • Aliases, junk-filter, dedup — same as above.
    """
    seen: set[str] = set()
    result: list[str] = []

    def _emit(token: str) -> None:
        t = token.strip().lower()
        t = re.sub(r"\s*\([^)]*\)\s*$", "", t).strip()   # strip "(BASIC)" etc.
        if not t or t in _SKILL_JUNK:
            return
        t = _ALIASES.get(t, t)
        if t not in seen:
            seen.add(t)
            result.append(t)

    for raw_token in raw:
        if not isinstance(raw_token, str) or not raw_token.strip():
            continue
        if " + " in raw_token:
            for part in raw_token.split(" + "):
                _emit(part)
        elif "+" in raw_token and not raw_token.startswith("+"):
            for part in raw_token.split("+"):
                _emit(part)
        else:
            _emit(raw_token)

    return result
