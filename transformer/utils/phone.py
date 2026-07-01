"""E.164 phone normalisation — library-first, scrub-based fallback."""
from __future__ import annotations
import re

import phonenumbers
from phonenumbers import NumberParseException


def _normalize_phone(raw: str) -> str | None:
    """
    Normalise a raw phone string toward E.164 format.

    Strategy
    --------
    1. phonenumbers.parse() with region hint "IN".
       Returns "+91XXXXXXXXXX" on success.
    2. Fallback: strip formatting chars, retain digits + leading '+'.
       Returns None if fewer than 7 digits remain.
    """
    if not raw or not raw.strip():
        return None
    try:
        parsed = phonenumbers.parse(raw, "IN")
        if phonenumbers.is_valid_number(parsed):
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except NumberParseException:
        pass

    scrubbed = re.sub(r"[\s\-\.\(\)]", "", raw)
    scrubbed = re.sub(r"[^\d+]", "", scrubbed)
    scrubbed = scrubbed.lstrip("+")
    if raw.strip().startswith("+"):
        scrubbed = "+" + scrubbed
    if sum(c.isdigit() for c in scrubbed) < 7:
        return None
    return scrubbed
