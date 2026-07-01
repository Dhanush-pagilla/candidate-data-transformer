"""Text / string utilities — safe coercion, email repair, URL normalisation."""
from __future__ import annotations
import re
from typing import Any


def _safe_str(value: Any) -> str | None:
    """Return stripped string or None.  Guards the 'honestly-empty' rule."""
    if value is None:
        return None
    if not isinstance(value, str):
        if isinstance(value, (int, float)):
            value = str(value)
        else:
            return None
    stripped = value.strip()
    return stripped if stripped else None


# Valid email pattern used after repair attempts.
_RE_EMAIL_VALID = re.compile(
    r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
)


def _repair_email(raw: str | None) -> str | None:
    """
    Attempt to fix a corrupted email and return it if valid after repair.
    Returns None (honestly-empty) if it cannot be salvaged — never invents data.

    Repairs (in order):
      1. [at] / (at)  →  @
      2. [dot] / (dot)  →  .
      3. @@@@  →  @
      4. ....  →  .
      5. Strip trailing dots from domain
      6. Lowercase + strip
      7. Validate against regex
    """
    if not raw:
        return None
    s = raw.strip().lower()
    s = re.sub(r"\[at\]|\(at\)",   "@", s, flags=re.IGNORECASE)
    s = re.sub(r"\[dot\]|\(dot\)", ".", s, flags=re.IGNORECASE)
    s = re.sub(r"@{2,}", "@", s)
    s = re.sub(r"\.{2,}", ".", s)
    if "@" in s:
        local, _, domain = s.partition("@")
        domain = domain.rstrip(".")
        s = f"{local}@{domain}"
    return s if _RE_EMAIL_VALID.match(s) else None


def _normalise_url(raw: str | None) -> str | None:
    """
    Fix common URL formatting issues:
      - Uppercase scheme  →  https://
      - Missing scheme    →  add https://
      - Double slashes in path  →  collapsed
      - Trailing slash stripped
    """
    if not raw:
        return None
    s = raw.strip()
    s = re.sub(r"^HTTPS?://", lambda m: m.group().lower(), s, flags=re.IGNORECASE)
    if not s.startswith(("http://", "https://")):
        s = "https://" + s
    scheme_end = s.index("//") + 2
    scheme, rest = s[:scheme_end], s[scheme_end:]
    rest = re.sub(r"/{2,}", "/", rest)
    s = (scheme + rest).rstrip("/")
    return s or None
