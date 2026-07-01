"""Date parsing, year normalisation, experience calculation."""
from __future__ import annotations
import datetime
import re
from typing import Any

_RE_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_WORD_NUMBERS: dict[str, int] = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20, "thirty": 30, "forty": 40,
}
_ONGOING_TOKENS = {"tbd", "present", "current", "ongoing", "now"}


def _normalise_year(raw: Any) -> str | None:
    """
    Convert a year value to a 4-digit string.
      • int < 100     → 2000+int  (26 → "2026")
      • "2026 (exp)"  → "2026"
      • None          → None
    """
    if raw is None:
        return None
    if isinstance(raw, int):
        return str(2000 + raw) if raw < 100 else str(raw)
    s = str(raw).strip()
    m = re.search(r"\b(\d{4})\b", s)
    if m:
        return m.group(1)
    m2 = re.search(r"\b(\d{2})\b", s)
    if m2:
        return str(2000 + int(m2.group(1)))
    return None


def _parse_date_to_ym(raw: str | None) -> str | None:
    """
    Parse a messy date string to YYYY-MM.
    Handles: MM/YYYY, YYYY/MM, MM-YYYY, YYYY-MM, YYYY.
    Keeps ongoing tokens as-is ("present", "tbd", …).
    Returns None for unparseable prose.
    """
    if not raw:
        return None
    lower = raw.strip().lower()
    if lower in _ONGOING_TOKENS:
        return lower
    if re.search(r"[a-zA-Z]", raw):
        return None
    parts = re.findall(r"\d+", raw)
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0] if len(parts[0]) == 4 else None
    a, b = parts[0], parts[1]
    if len(a) == 4:
        year, month = a, b
    elif len(b) == 4:
        year, month = b, a
    else:
        return None
    try:
        m = int(month)
        if 1 <= m <= 12:
            return f"{year}-{m:02d}"
    except ValueError:
        pass
    return None


def _parse_experience_prose(raw: str | None) -> float | None:
    """
    Extract years of experience from prose.
    "approximately eleven-ish months" → 0.9
    "2 years" → 2.0
    Fallback when no structured work history is available.
    """
    if not raw:
        return None
    lower = raw.lower()
    m = _RE_NUMBER.search(lower)
    value: float | None = float(m.group()) if m else None
    if value is None:
        for word, num in _WORD_NUMBERS.items():
            if re.search(rf"\b{word}\b", lower):
                value = float(num)
                break
    if value is None:
        return None
    if "month" in lower:
        value /= 12.0
    return round(value, 1)


def _calculate_years_from_experience(experience: list[dict]) -> float | None:
    """
    Sum durations of all work history entries with parseable YYYY-MM dates.
    Returns None if no entry has calculable dates (honestly-empty).
    Uses today's date for ongoing tokens ("present", "tbd", …).
    """
    if not experience:
        return None

    today = datetime.date.today()

    def _to_date(ym: str | None) -> datetime.date | None:
        if not ym:
            return None
        if ym.strip().lower() in _ONGOING_TOKENS:
            return today
        m = re.fullmatch(r"(\d{4})-(\d{2})", ym.strip().lower())
        if not m:
            return None
        try:
            return datetime.date(int(m.group(1)), int(m.group(2)), 1)
        except ValueError:
            return None

    total_days, counted = 0, 0
    for entry in experience:
        s = _to_date(entry.get("start"))
        e = _to_date(entry.get("end"))
        if s and e and e >= s:
            total_days += (e - s).days
            counted += 1

    return round(total_days / 365.25, 1) if counted > 0 else None
