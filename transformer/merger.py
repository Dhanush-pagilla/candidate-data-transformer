"""
merger.py
=========
merge_and_deduplicate  — authority-ranked field merge + skill unification.
calculate_confidence   — deterministic completeness scoring engine.
"""
from __future__ import annotations
import warnings
from typing import Any

from .constants import SOURCE_ATS, SOURCE_GITHUB


# ---------------------------------------------------------------------------
# Provenance field-name → canonical schema name map
# ---------------------------------------------------------------------------
_PROVENANCE_FIELD_MAP: dict[str, str] = {
    "current_role": "headline", "current_organization": "current_organization",
    "email": "emails", "mail_id": "emails", "mobile": "phones",
    "github_languages": "skills", "skills": "skills",
    "github_url": "links", "portfolio_url": "links",
    "linkedin_url": "links", "blog": "links", "public_repos": "links",
}


# ---------------------------------------------------------------------------
# Blank canonical profile
# ---------------------------------------------------------------------------

def _blank_canonical_profile() -> dict:
    return {
        "candidate_id": None, "full_name": None,
        "emails": [], "phones": [],
        "location": {"city": None, "region": None, "country": None},
        "links": {"linkedin": None, "github": None, "portfolio": None, "other": []},
        "headline": None, "current_organization": None,
        "years_experience": None, "skills": [],
        "experience": [], "education": [],
        "provenance": [], "overall_confidence": 0.0,
    }


# ---------------------------------------------------------------------------
# Merge helpers
# ---------------------------------------------------------------------------

def _is_honestly_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, list):
        return len(value) == 0
    if isinstance(value, dict):
        return all(_is_honestly_empty(v) for v in value.values())
    return False


def _first_truthy(records: list[dict], field: str) -> Any:
    for r in records:
        v = r.get(field)
        if not _is_honestly_empty(v):
            return v
    return None


def _specialist_field(records: list[dict], field: str, specialist: str) -> Any:
    specialist_val: Any = None
    fallback: Any = None
    for r in records:
        prov   = r.get("provenance") or []
        source = prov[0]["source"] if prov else ""
        v = r.get(field)
        if source == specialist and not _is_honestly_empty(v):
            specialist_val = v
        elif fallback is None and not _is_honestly_empty(v):
            fallback = v
    return specialist_val if specialist_val is not None else fallback


def _merge_scalar_list(records: list[dict], field: str) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for r in records:
        raw = r.get(field)
        if raw and isinstance(raw, str):
            n = raw.lower().strip()
            if n and n not in seen:
                seen.add(n)
                result.append(n)
    return result


def _merge_list_field(records: list[dict], field: str) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for r in records:
        for item in (r.get(field) or []):
            if isinstance(item, str):
                k = item.strip().lower()
                if k and k not in seen:
                    seen.add(k)
                    result.append(item.strip())
    return result


def _merge_skills(records: list[dict], authority_map: dict[str, float]) -> list[dict]:
    """
    Unify skill tokens from ATS ``skills`` and GitHub ``github_languages``
    into structured objects: {name, confidence, sources[]}.
    MAX confidence wins when a skill appears in multiple sources.
    """
    skill_index: dict[str, dict] = {}
    for r in records:
        prov   = r.get("provenance") or []
        source = prov[0]["source"] if prov else ""
        weight = authority_map.get(source, 0.5)
        tokens: list[tuple[str, str, float]] = []
        for tok in r.get("skills") or []:
            if isinstance(tok, str) and tok.strip():
                tokens.append((tok.strip().lower(), source, weight))
        for tok in r.get("github_languages") or []:
            if isinstance(tok, str) and tok.strip():
                tokens.append((tok.strip().lower(), source, weight))
        for name, src, conf in tokens:
            if name not in skill_index:
                skill_index[name] = {"name": name, "confidence": conf, "sources": {src}}
            else:
                skill_index[name]["confidence"] = max(skill_index[name]["confidence"], conf)
                skill_index[name]["sources"].add(src)

    result = [
        {"name": e["name"], "confidence": e["confidence"], "sources": sorted(e["sources"])}
        for e in skill_index.values()
    ]
    result.sort(key=lambda s: (-s["confidence"], s["name"]))
    return result


# ---------------------------------------------------------------------------
# Main engine
# ---------------------------------------------------------------------------

SOURCE_AUTHORITY: dict[str, float] = {SOURCE_ATS: 0.9, SOURCE_GITHUB: 0.7}


def merge_and_deduplicate(records: list[dict]) -> dict:
    """
    Merge normalised records sharing the same candidate_id into one
    authoritative Canonical Profile.

    Steps
    -----
    1. Guard: empty input → blank shell.
    2. Candidate-ID coherence check — quarantine mismatches.
    3. Sort by source authority (ATS 0.9 > GitHub 0.7).
    4. Scalar field resolution:
         full_name     → longest name across all sources (title-cased)
         other scalars → HIGH-AUTHORITY-WINS
         portfolio/bio → SPECIALIST-WINS (GitHub)
    5. List merging (emails, phones, skills).
    6. Provenance unification.
    7. Confidence scoring.
    """
    if not records:
        warnings.warn(
            "[merge] Empty records list — returning blank profile.",
            RuntimeWarning, stacklevel=2)
        return _blank_canonical_profile()

    # Step 2 — ID coherence
    reference_id: str | None = next(
        (r.get("candidate_id") for r in records if r.get("candidate_id")), None
    )
    clean: list[dict] = []
    for r in records:
        if r.get("candidate_id") != reference_id:
            warnings.warn(
                f"[merge] candidate_id '{r.get('candidate_id')}' ≠ "
                f"'{reference_id}' — quarantined.",
                RuntimeWarning, stacklevel=2)
        else:
            clean.append(r)

    if not clean:
        warnings.warn("[merge] No records survived ID check.", RuntimeWarning, stacklevel=2)
        return _blank_canonical_profile()

    # Step 3 — sort by authority
    def _authority(r: dict) -> float:
        prov = r.get("provenance") or []
        src  = prov[0]["source"] if prov else ""
        return SOURCE_AUTHORITY.get(src, 0.0)

    authority_sorted = sorted(clean, key=_authority, reverse=True)

    # Step 4 — scalar resolution
    # full_name: longest across ALL sources (handles single-token ATS name)
    all_names = [
        r.get("full_name") for r in authority_sorted
        if isinstance(r.get("full_name"), str) and r.get("full_name", "").strip()
    ]
    full_name = (
        max(all_names, key=lambda n: len(n.strip())).strip().title()
        if all_names else None
    )

    headline             = _first_truthy(authority_sorted, "current_role")
    location             = _first_truthy(authority_sorted, "location") or \
                           {"city": None, "region": None, "country": None}
    years_experience     = _first_truthy(authority_sorted, "years_experience")
    current_organization = _first_truthy(authority_sorted, "current_organization")

    bio           = _specialist_field(authority_sorted, "bio",          SOURCE_GITHUB)
    github_url    = _specialist_field(authority_sorted, "github_url",   SOURCE_GITHUB)
    portfolio_url = _specialist_field(authority_sorted, "portfolio_url",SOURCE_GITHUB)
    public_repos  = _specialist_field(authority_sorted, "public_repos", SOURCE_GITHUB)
    linkedin_url  = _specialist_field(authority_sorted, "linkedin_url", SOURCE_ATS)
    other_links   = _merge_list_field(authority_sorted, "other_links")

    links = {
        "linkedin":  linkedin_url,
        "github":    github_url,
        "portfolio": portfolio_url,
        "other":     other_links,
    }

    # Step 5 — list merging
    emails      = _merge_scalar_list(authority_sorted, "email")
    phones      = _merge_list_field(authority_sorted, "phones")
    skills      = _merge_skills(authority_sorted, SOURCE_AUTHORITY)
    experience  = _first_truthy(authority_sorted, "experience") or []
    education   = _first_truthy(authority_sorted, "education")  or []

    # years_experience — use calculated value if present.
    # If None AND experience is empty, the candidate has no work history
    # at all (e.g. fresh graduate) → store as 0.0, not null.
    if years_experience is None and not experience:
        years_experience = 0.0

    # Step 6 — provenance
    provenance: list[dict] = []
    for r in authority_sorted:
        provenance.extend(r.get("provenance") or [])

    canonical: dict = {
        "candidate_id": reference_id, "full_name": full_name,
        "emails": emails, "phones": phones,
        "location": location, "links": links,
        "headline": headline, "current_organization": current_organization,
        "years_experience": years_experience, "skills": skills,
        "experience": experience, "education": education,
        "provenance": provenance, "overall_confidence": 0.0,
    }

    # Step 7 — confidence
    canonical["overall_confidence"] = calculate_confidence(canonical)
    return canonical


# ---------------------------------------------------------------------------
# Confidence engine
# ---------------------------------------------------------------------------

FIELD_WEIGHTS: dict[str, float] = {
    "candidate_id": 1.00, "full_name": 0.95, "emails": 0.95,
    "phones": 0.80, "location": 0.75, "headline": 0.80,
    "current_organization": 0.75, "skills": 0.90,
    "links": 0.60, "years_experience": 0.70,
    "experience": 0.65, "education": 0.55,
}


def calculate_confidence(merged_record: dict) -> float:
    """
    Overall confidence = Σ(field_importance × source_authority) / Σ(field_importance)
    Honestly-empty fields contribute 0 to numerator but full weight to denominator.
    """
    prov_authority: dict[str, float] = {}
    for entry in merged_record.get("provenance") or []:
        field  = entry.get("field", "")
        source = entry.get("source", "")
        weight = SOURCE_AUTHORITY.get(source, 0.5)
        canon  = _PROVENANCE_FIELD_MAP.get(field, field)
        if canon in FIELD_WEIGHTS:
            prov_authority[canon] = max(prov_authority.get(canon, 0.0), weight)

    numerator   = 0.0
    denominator = sum(FIELD_WEIGHTS.values())

    for field, importance in FIELD_WEIGHTS.items():
        value = merged_record.get(field)
        if not _is_honestly_empty(value):
            auth = prov_authority.get(field, 0.5)
            numerator += importance * auth

    if denominator == 0.0:
        return 0.0
    return round(min(numerator / denominator, 1.0), 2)
