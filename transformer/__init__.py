"""
transformer package
===================
Multi-Source Candidate Data Transformer.

Quick-start
-----------
    from transformer import run

    canonical = run("sample_inputs/dhanush_ats.json",
                    github="sample_inputs/dhanush_github.json")
"""
from __future__ import annotations
import json
import sys
import warnings
from pathlib import Path
from typing import Any

from .constants   import SOURCE_ATS, SOURCE_GITHUB
from .ingestion   import ingest_source, ingest_and_enrich
from .normalizers import detect_and_normalize, normalize_github_data
from .merger      import merge_and_deduplicate, calculate_confidence
from .projection  import project_to_output, validate_schema
from .ingestion   import _extract_github_url


# ---------------------------------------------------------------------------
# Default output config (matches assignment spec)
# ---------------------------------------------------------------------------
DEFAULT_CONFIG: dict = {
    "on_missing": "null",
    "include_confidence": True,
    "fields": [
        {"path": "candidate_id",         "from": "candidate_id",         "type": "string",   "required": True},
        {"path": "full_name",            "from": "full_name",            "type": "string"},
        {"path": "primary_email",        "from": "emails[0]",            "type": "string",   "required": True},
        {"path": "emails",               "from": "emails",               "type": "string[]"},
        {"path": "phone",                "from": "phones[0]",            "type": "string",   "normalize": "E164"},
        {"path": "phones",               "from": "phones",               "type": "string[]"},
        {"path": "location",             "from": "location",             "type": "dict"},
        {"path": "links",                "from": "links",                "type": "dict"},
        {"path": "headline",             "from": "headline",             "type": "string"},
        {"path": "current_organization", "from": "current_organization", "type": "string"},
        {"path": "years_experience",     "from": "years_experience",     "type": "float"},
        {"path": "skills",               "from": "skills[].name",        "type": "string[]", "normalize": "canonical"},
        {"path": "experience",           "from": "experience",           "type": "list",      "allow_empty": True},
        {"path": "education",            "from": "education",            "type": "list",      "allow_empty": True},
        {"path": "overall_confidence",   "from": "overall_confidence",   "type": "float"},
        {"path": "provenance",           "from": "provenance",           "type": "list"},
    ],
}


# ---------------------------------------------------------------------------
# High-level pipeline runner
# ---------------------------------------------------------------------------

def run(
    ats_path:    str | None = None,
    github:      str | None = None,
    config:      dict | None = None,
    out_path:    str | None = None,
    quiet:       bool = False,
) -> dict:
    """
    Execute the full pipeline end-to-end.

    Parameters
    ----------
    ats_path  : Path to the ATS JSON file.
    github    : GitHub profile URL  OR  local JSON snapshot path.
                If omitted, the URL is auto-extracted from the ATS payload.
    config    : Projection config dict.  Defaults to DEFAULT_CONFIG.
    out_path  : Write JSON output here instead of printing.
    quiet     : Suppress informational messages.

    Returns
    -------
    dict
        The projected, validated output record.
    """
    cfg = config or DEFAULT_CONFIG
    records: list[dict] = []
    raw_ats: dict = {}

    # ── Step 1: Ingest + normalise ATS ────────────────────────────────────
    if ats_path:
        raw_ats = ingest_source(ats_path, SOURCE_ATS)
        if raw_ats:
            norm = detect_and_normalize(raw_ats)
            records.append(norm)
            if not quiet:
                _log("ATS", ats_path, norm)
        elif not quiet:
            print(f"  [warn] ATS '{ats_path}' returned empty — skipping.", file=sys.stderr)

    # ── Step 2: Resolve GitHub source ─────────────────────────────────────
    if not github and raw_ats:
        auto = _extract_github_url(raw_ats)
        if auto:
            if not quiet:
                print(f"  [info] GitHub URL found in ATS — fetching: {auto}", file=sys.stderr)
            github = auto

    # ── Step 3: Ingest + normalise GitHub ─────────────────────────────────
    if github:
        is_url = github.startswith(("http://", "https://"))
        if not quiet:
            label = "live API" if is_url else "local snapshot"
            print(f"  [info] GitHub source ({label}): {github}", file=sys.stderr)
        raw_gh = ingest_source(github, SOURCE_GITHUB)
        if raw_gh:
            gh_norm = normalize_github_data(raw_gh)
            # Edge case: GitHub has no public email → inject ATS candidate_id
            ats_id = records[0].get("candidate_id") if records else None
            if gh_norm.get("candidate_id") is None and ats_id:
                if not quiet:
                    print("  [info] GitHub has no public email — "
                          "injecting candidate_id from ATS.", file=sys.stderr)
                gh_norm["candidate_id"] = ats_id
                gh_norm["provenance"].append({
                    "field":  "candidate_id",
                    "source": SOURCE_GITHUB,
                    "method": "injected_from_ats:no_public_email",
                })
            records.append(gh_norm)
        elif not quiet:
            print(f"  [warn] GitHub source '{github}' returned empty — skipping.", file=sys.stderr)

    if not records:
        print("[error] No usable source records.", file=sys.stderr)
        sys.exit(1)

    # ── Step 4: Merge ─────────────────────────────────────────────────────
    canonical = merge_and_deduplicate(records)

    # ── Step 5: Project ───────────────────────────────────────────────────
    try:
        projected = project_to_output(canonical, cfg)
    except ValueError as exc:
        print(f"[error] Projection aborted: {exc}", file=sys.stderr)
        sys.exit(1)

    # ── Step 6: Validate ──────────────────────────────────────────────────
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        is_valid = validate_schema(projected, cfg)

    if not is_valid and not quiet:
        print("[warn] Validation issues:", file=sys.stderr)
        for w in caught:
            if "FAILURE" in str(w.message):
                print(f"  • {w.message}", file=sys.stderr)

    # ── Step 7: Output ────────────────────────────────────────────────────
    output_json = json.dumps(projected, indent=2, default=str)

    if out_path:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_text(output_json, encoding="utf-8")
        if not quiet:
            print(f"  [ok] Output written → '{out_path}'")
    else:
        print(output_json)

    return projected


def _log(source_label: str, path: str, norm: dict) -> None:
    """Print a compact normalisation summary to stderr."""
    print(f"\n  ── {source_label}: {path}", file=sys.stderr)
    print(f"     candidate_id  : {(norm.get('candidate_id') or '')[:16]}…", file=sys.stderr)
    print(f"     full_name     : {norm.get('full_name')}", file=sys.stderr)
    print(f"     email         : {norm.get('email')}", file=sys.stderr)
    print(f"     phones        : {norm.get('phones')}", file=sys.stderr)
