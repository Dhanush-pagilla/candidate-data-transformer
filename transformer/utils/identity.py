"""Deterministic candidate identity — SHA-256 hash of normalised email."""
from __future__ import annotations
import hashlib


def _derive_candidate_id(email: str | None) -> str | None:
    """
    SHA-256 hash of the lowercase-stripped email address.
    Returns None when no valid email is available (honestly-empty rule).
    """
    if not email:
        return None
    return hashlib.sha256(email.lower().strip().encode("utf-8")).hexdigest()
