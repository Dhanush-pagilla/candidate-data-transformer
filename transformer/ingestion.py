"""
ingestion.py
============
Source loading: local JSON files and live GitHub API.
Also provides ingest_and_enrich (single ATS-file entry point) and
mock_github_extraction (deterministic offline simulation).
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
import warnings
from pathlib import Path
from typing import Any

from .constants import (EMPTY_RECORD, SOURCE_ATS, SOURCE_GITHUB,
                         _GITHUB_API_BASE, _HTTP_TIMEOUT)
from .utils     import (_safe_str, _repair_email, _normalise_url,
                         _canonicalize_and_dedupe_skills)


# ---------------------------------------------------------------------------
# Public helpers used by CandidateTransformer
# ---------------------------------------------------------------------------

def ingest_source(file_path: str, source_type: str) -> dict:
    """
    Load a payload from a local JSON file or a live GitHub profile URL.

    Routing
    -------
    • URL + source_type == "github_profile"  →  fetch_github_profile()
    • Otherwise  →  read local JSON file

    Failure modes handled (all return {} with a stderr warning):
      1. File not found / OS error
      2. Empty file
      3. JSON decode error
      4. Root is not a dict
    """
    is_url = file_path.startswith(("http://", "https://"))
    if is_url and source_type == SOURCE_GITHUB:
        return fetch_github_profile(file_path)

    path = Path(file_path)
    try:
        raw_bytes = path.read_bytes()
    except FileNotFoundError:
        warnings.warn(
            f"[ingest_source] '{source_type}': file not found at '{file_path}'.",
            RuntimeWarning, stacklevel=2)
        return EMPTY_RECORD
    except OSError as exc:
        warnings.warn(
            f"[ingest_source] '{source_type}': OS error reading '{file_path}': {exc}.",
            RuntimeWarning, stacklevel=2)
        return EMPTY_RECORD

    if not raw_bytes.strip():
        warnings.warn(
            f"[ingest_source] '{source_type}': '{file_path}' is empty.",
            RuntimeWarning, stacklevel=2)
        return EMPTY_RECORD

    try:
        payload: dict = json.loads(raw_bytes)
    except json.JSONDecodeError as exc:
        warnings.warn(
            f"[ingest_source] '{source_type}': JSON decode error in '{file_path}': {exc}.",
            RuntimeWarning, stacklevel=2)
        return EMPTY_RECORD

    if not isinstance(payload, dict):
        warnings.warn(
            f"[ingest_source] '{source_type}': expected JSON object, "
            f"got {type(payload).__name__}.",
            RuntimeWarning, stacklevel=2)
        return EMPTY_RECORD

    return payload


def ingest_and_enrich(ats_path: str) -> tuple[dict, dict]:
    """
    Single-file entry point:
      1. Read ATS JSON from ats_path.
      2. Extract embedded GitHub URL.
      3. Generate a deterministic mock GitHub snapshot seeded from ATS identity.
      4. Return (raw_ats, raw_github).
    """
    raw_ats = ingest_source(ats_path, SOURCE_ATS)
    if not raw_ats:
        return EMPTY_RECORD, EMPTY_RECORD

    github_url  = _extract_github_url(raw_ats)
    personal    = raw_ats.get("personal") or {}
    professional = raw_ats.get("professional") or {}

    first = _safe_str(personal.get("first_name")) or ""
    last  = _safe_str(personal.get("last_name"))  or ""
    name  = f"{first} {last}".strip().title() or None

    email = _repair_email(_safe_str(personal.get("contact_email")))
    if email is None:
        email = _repair_email(_safe_str(personal.get("alt_email")))

    raw_skills = professional.get("tech_stack") or []
    raw_github  = mock_github_extraction(github_url, name, email, raw_skills)
    return raw_ats, raw_github


def mock_github_extraction(
    github_url: str | None,
    name:       str | None,
    email:      str | None,
    raw_skills: list,
) -> dict:
    """
    Generate a deterministic offline GitHub snapshot identity-matched to the
    ATS record.  Uses the same email so candidate_id hashes match and the
    merge engine accepts both records.
    """
    login = github_url.rstrip("/").split("/")[-1] if github_url else None
    canonical_skills = _canonicalize_and_dedupe_skills(raw_skills)
    languages        = [s.title() for s in canonical_skills if s]
    public_repos     = max(5, len(canonical_skills) * 3)
    bio = f"Software Engineer | {len(canonical_skills)} languages | Open Source"
    return {
        "login":        login,
        "name":         name,
        "email":        email,
        "html_url":     github_url,
        "bio":          bio,
        "blog":         None,
        "company":      None,
        "location":     None,
        "public_repos": public_repos,
        "followers":    0,
        "following":    0,
        "languages":    languages,
        "_mock":        True,
    }


def fetch_github_profile(profile_url: str) -> dict:
    """
    Fetch a live GitHub user profile + aggregate languages from repos.
    Uses GITHUB_TOKEN env var when available (raises limit 60→5000 req/hr).
    Returns {} on any network/parse error without crashing.
    """
    username = profile_url.rstrip("/").split("/")[-1]
    if not username or "." in username:
        warnings.warn(
            f"[fetch_github_profile] Cannot extract username from '{profile_url}'.",
            RuntimeWarning, stacklevel=3)
        return EMPTY_RECORD

    headers: dict[str, str] = {
        "Accept":     "application/vnd.github+json",
        "User-Agent": "candidate-data-transformer/1.0",
    }
    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    def _get(url: str) -> Any:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))

    try:
        profile = _get(f"{_GITHUB_API_BASE}/users/{username}")
    except urllib.error.HTTPError as exc:
        hint = " Rate limit — set GITHUB_TOKEN for higher limits." if exc.code == 403 else ""
        warnings.warn(
            f"[fetch_github_profile] HTTP {exc.code} for '{username}': {exc.reason}.{hint}",
            RuntimeWarning, stacklevel=3)
        return EMPTY_RECORD
    except (urllib.error.URLError, OSError) as exc:
        warnings.warn(
            f"[fetch_github_profile] Network error for '{username}': {exc}.",
            RuntimeWarning, stacklevel=3)
        return EMPTY_RECORD
    except json.JSONDecodeError as exc:
        warnings.warn(
            f"[fetch_github_profile] JSON error for '{username}': {exc}.",
            RuntimeWarning, stacklevel=3)
        return EMPTY_RECORD

    if not isinstance(profile, dict):
        warnings.warn(
            f"[fetch_github_profile] Unexpected response shape for '{username}'.",
            RuntimeWarning, stacklevel=3)
        return EMPTY_RECORD

    # Aggregate languages from up to 30 most-recently-pushed non-fork repos.
    language_bytes: dict[str, int] = {}
    try:
        repos = _get(
            f"{_GITHUB_API_BASE}/users/{username}/repos"
            f"?per_page=30&sort=pushed&type=owner"
        )
        if isinstance(repos, list):
            for repo in repos:
                repo_name = repo.get("name", "")
                if not repo_name or repo.get("fork"):
                    continue
                try:
                    lang_data = _get(
                        f"{_GITHUB_API_BASE}/repos/{username}/{repo_name}/languages"
                    )
                    if isinstance(lang_data, dict):
                        for lang, bytes_count in lang_data.items():
                            language_bytes[lang] = language_bytes.get(lang, 0) + bytes_count
                except Exception:
                    continue
    except Exception as exc:
        warnings.warn(
            f"[fetch_github_profile] Language fetch failed for '{username}': {exc}. "
            f"Continuing with profile data only.",
            RuntimeWarning, stacklevel=3)

    languages_sorted = [
        lang for lang, _ in
        sorted(language_bytes.items(), key=lambda kv: kv[1], reverse=True)
    ]

    return {
        "login":        profile.get("login"),
        "name":         profile.get("name"),
        "email":        profile.get("email"),
        "html_url":     profile.get("html_url"),
        "bio":          profile.get("bio"),
        "blog":         profile.get("blog"),
        "company":      profile.get("company"),
        "location":     profile.get("location"),
        "public_repos": profile.get("public_repos"),
        "followers":    profile.get("followers"),
        "following":    profile.get("following"),
        "languages":    languages_sorted,
    }


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _extract_github_url(raw_ats: dict) -> str | None:
    """
    Scan an ATS payload for an embedded GitHub URL.
    Checks (in priority order):
      1. professional.profile_links.github_url
      2. candidate_profile.personal_details.profile_links.github_url
      3. profile_links.github_url
      4. github_url  (top-level)
      5. links.github
    """
    candidates = [
        (raw_ats.get("professional") or {}).get("profile_links", {}).get("github_url"),
        ((raw_ats.get("candidate_profile") or {})
            .get("personal_details", {})
            .get("profile_links", {})
            .get("github_url")),
        (raw_ats.get("profile_links") or {}).get("github_url"),
        raw_ats.get("github_url"),
        (raw_ats.get("links") or {}).get("github"),
    ]
    for candidate in candidates:
        url = _safe_str(candidate) if candidate else None
        if url and "github.com" in url.lower():
            return _normalise_url(url)
    return None
