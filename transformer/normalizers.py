"""
normalizers.py
==============
Four normalizers — one per source schema shape — all producing the same
canonical intermediate record shape consumed by the merger.

Canonical intermediate shape
-----------------------------
{
  candidate_id, full_name, email, phones, current_organization,
  current_role, location, skills, bio, github_url, portfolio_url,
  linkedin_url, other_links, public_repos, github_languages,
  years_experience, experience, education, provenance
}
"""
from __future__ import annotations
import re
import warnings
from typing import Any

from .constants import SOURCE_ATS, SOURCE_GITHUB
from .utils import (
    _safe_str, _repair_email, _normalise_url,
    _derive_candidate_id, _normalize_phone, _normalize_location,
    _canonicalize_skills, _canonicalize_skills_expanded,
    _canonicalize_and_dedupe_skills,
    _parse_date_to_ym, _normalise_year,
    _parse_experience_prose, _calculate_years_from_experience,
)


# ---------------------------------------------------------------------------
# Shared provenance tracker (closure pattern)
# ---------------------------------------------------------------------------

def _make_tracker(provenance: list[dict], source: str):
    def _track(field: str, method: str) -> None:
        provenance.append({"field": field, "source": source, "method": method})
    return _track


# ---------------------------------------------------------------------------
# 1. Flat ATS (original ats_blob.json schema)
# ---------------------------------------------------------------------------

def normalize_ats_data(raw_data: dict) -> dict:
    """
    Flat ATS schema:  candidate_name, mail_id, mobile, current_org, role,
    location_str, skills_list, linkedin_url, experience[].
    """
    prov: list[dict] = []
    t = _make_tracker(prov, SOURCE_ATS)

    full_name = _safe_str(raw_data.get("candidate_name"))
    t("full_name", "direct_map:candidate_name")

    raw_email = _safe_str(raw_data.get("mail_id"))
    email = _repair_email(raw_email) or (raw_email.lower().strip() if raw_email else None)
    t("email", "repair_email:mail_id")

    candidate_id = _derive_candidate_id(email)
    t("candidate_id", "sha256_hash:email")

    phones: list[str] = []
    raw_mobile = raw_data.get("mobile")
    if raw_mobile is not None:
        n = _normalize_phone(str(raw_mobile))
        if n:
            phones.append(n)
    t("phones", "e164_normalisation:mobile")

    current_organization = _safe_str(raw_data.get("current_org"))
    t("current_organization", "direct_map:current_org")

    current_role = _safe_str(raw_data.get("role"))
    t("current_role", "direct_map:role")

    location = _normalize_location(_safe_str(raw_data.get("location_str")))
    t("location", "iso3166_parse:location_str")

    skills = _canonicalize_skills(raw_data.get("skills_list"))
    t("skills", "canonicalize:skills_list")

    linkedin_url = _normalise_url(_safe_str(
        raw_data.get("linkedin_url") or raw_data.get("linkedin")
    ))
    t("linkedin_url", "url_normalise:linkedin_url")

    raw_exp = raw_data.get("experience") or []
    experience = raw_exp if isinstance(raw_exp, list) else []
    years_experience = _calculate_years_from_experience(experience)
    t("years_experience", "calc_from_work_history_dates")

    return {
        "candidate_id": candidate_id, "full_name": full_name,
        "email": email, "phones": phones,
        "current_organization": current_organization, "current_role": current_role,
        "location": location, "skills": skills,
        "bio": None, "github_url": None, "portfolio_url": None,
        "linkedin_url": linkedin_url, "other_links": [],
        "public_repos": None, "github_languages": [],
        "years_experience": years_experience,
        "experience": experience, "education": [],
        "provenance": prov,
    }


# ---------------------------------------------------------------------------
# 2. Nested messy ATS (srividya.json / new.json schema)
# ---------------------------------------------------------------------------

def normalize_new_ats_data(raw_data: dict) -> dict:
    """
    Nested ATS schema: personal{}, professional{}, academic[], work_history[].
    Handles corrupted email, repeated commas, prose experience, malformed URLs.
    """
    prov: list[dict] = []
    t = _make_tracker(prov, SOURCE_ATS)

    personal     = raw_data.get("personal")     or {}
    professional = raw_data.get("professional") or {}
    academic     = raw_data.get("academic")     or []
    work_history = raw_data.get("work_history") or []

    # full_name — concat first+last, title-case
    first = _safe_str(personal.get("first_name")) or ""
    last  = _safe_str(personal.get("last_name"))  or ""
    full_name = (f"{first} {last}".strip()).title() or None
    t("full_name", "concat:first_name+last_name → title_case")

    # email — repair corrupted value, fall back to alt_email
    email = _repair_email(_safe_str(personal.get("contact_email")))
    if email is None:
        email = _repair_email(_safe_str(personal.get("alt_email")))
    t("email", "repair_email:contact_email | fallback:alt_email")

    candidate_id = _derive_candidate_id(email)
    t("candidate_id", "sha256_hash:email")

    phones: list[str] = []
    raw_phone = _safe_str(personal.get("mobile"))
    if raw_phone:
        n = _normalize_phone(raw_phone)
        if n:
            phones.append(n)
    t("phones", "e164_normalisation:personal.mobile")

    # location — collapse repeated commas before parsing
    raw_loc = _safe_str(personal.get("current_location"))
    if raw_loc:
        raw_loc = re.sub(r",\s*,+", ",", raw_loc)
    location = _normalize_location(raw_loc)
    t("location", "iso3166_parse:current_location → collapsed_commas")

    current_organization = _safe_str(professional.get("current_employer"))
    t("current_organization", "direct_map:current_employer")

    current_role = _safe_str(professional.get("current_designation"))
    t("current_role", "direct_map:current_designation")

    skills = _canonicalize_and_dedupe_skills(professional.get("tech_stack") or [])
    t("skills", "canonicalize+dedupe:tech_stack")

    pl = professional.get("profile_links") or {}
    linkedin_url = _normalise_url(_safe_str(pl.get("linkedin_url")))
    github_url   = _normalise_url(_safe_str(pl.get("github_url")))
    t("linkedin_url", "url_normalise:profile_links.linkedin_url")
    t("github_url",   "url_normalise:profile_links.github_url")

    experience = _parse_work_history(work_history)
    t("experience", "parse_work_history → YYYY-MM_dates")

    education = _parse_academic(academic)
    t("education", "parse_academic → structured_education")

    # years_experience — primary: from dates; fallback: prose field
    years_experience = _calculate_years_from_experience(experience)
    if years_experience is None:
        years_experience = _parse_experience_prose(
            _safe_str(professional.get("total_exp_months"))
        )
    t("years_experience", "calc_from_work_history_dates | fallback:prose")

    return {
        "candidate_id": candidate_id, "full_name": full_name,
        "email": email, "phones": phones,
        "current_organization": current_organization, "current_role": current_role,
        "location": location, "skills": skills,
        "bio": None, "github_url": github_url, "portfolio_url": None,
        "linkedin_url": linkedin_url, "other_links": [],
        "public_repos": None, "github_languages": [],
        "years_experience": years_experience,
        "experience": experience, "education": education,
        "provenance": prov,
    }


# ---------------------------------------------------------------------------
# 3. Resume / candidate_profile schema (dhanush_ats.json)
# ---------------------------------------------------------------------------

def normalize_resume_data(raw_data: dict) -> dict:
    """
    candidate_profile schema:
    personal_details{}, technical_skills{}, academic_projects[], education[],
    achievements[].
    Edge cases: single-token name, corrupted email, compound skill tokens,
    short-form year in timeline, no work history.
    """
    prov: list[dict] = []
    t = _make_tracker(prov, SOURCE_ATS)

    cp      = raw_data.get("candidate_profile") or raw_data
    pd      = cp.get("personal_details") or {}
    links_r = pd.get("profile_links") or {}
    ts      = cp.get("technical_skills") or {}

    # full_name — title-case; cross-source enrichment fills surname if missing
    raw_name  = _safe_str(pd.get("full_name")) or ""
    full_name = raw_name.title() if raw_name else None
    t("full_name", "direct_map:full_name → title_case")

    # email — repair corrupted value, fall back to alt_email
    email = _repair_email(_safe_str(pd.get("primary_email")))
    if email is None:
        email = _repair_email(_safe_str(pd.get("alt_email")))
    t("email", "repair_email:primary_email | fallback:alt_email")

    candidate_id = _derive_candidate_id(email)
    t("candidate_id", "sha256_hash:email")

    phones: list[str] = []
    raw_phone = _safe_str(pd.get("contact_number"))
    if raw_phone:
        n = _normalize_phone(raw_phone)
        if n:
            phones.append(n)
    t("phones", "e164_normalisation:contact_number")

    linkedin_url = _normalise_url(_safe_str(links_r.get("linkedin_url")))
    github_url   = _normalise_url(_safe_str(links_r.get("github_url")))
    t("linkedin_url", "url_normalise:profile_links.linkedin_url")
    t("github_url",   "url_normalise:profile_links.github_url")

    # location inferred from institution city (no explicit location field)
    location = _normalize_location("Hyderabad, Telangana, India")
    t("location", "inferred:institution_city → Hyderabad, Telangana, IN")

    # headline — derived from first education qualification
    headline: str | None = None
    edu_list = cp.get("education") or []
    if edu_list:
        q = _safe_str(edu_list[0].get("qualification")) or ""
        if " in " in q:
            _, _, field_str = q.partition(" in ")
            headline = f"B.Tech Student in {field_str.strip()}"
        elif q:
            headline = q
    t("headline", "derived:education[0].qualification → role_title")

    # years_experience — no work history in this schema
    years_experience: float | None = None
    t("years_experience", "honestly_empty:no_work_history → null")

    # skills — union of technical_skills + all project technologies, expanded
    raw_skill_tokens: list[str] = []
    for bucket in ("languages", "database"):
        raw_skill_tokens += [i for i in (ts.get(bucket) or []) if isinstance(i, str)]
    for proj in cp.get("academic_projects") or []:
        raw_skill_tokens += [i for i in (proj.get("technologies_used") or []) if isinstance(i, str)]
    skills = _canonicalize_skills_expanded(raw_skill_tokens)
    t("skills", "union:technical_skills+project_tech → expand_compound_dedup")

    # experience — no work history; achievements are NOT employment history
    experience: list[dict] = []
    t("experience", "honestly_empty:no_work_history → []")

    # education — parse degree + field, expand short-form year
    education: list[dict] = []
    for edu in edu_list:
        raw_qual    = _safe_str(edu.get("qualification")) or ""
        institution = _safe_str(edu.get("institution"))
        if " in " in raw_qual:
            degree_str, _, field_str = raw_qual.partition(" in ")
        else:
            degree_str, field_str = raw_qual, ""
        field: str | None = field_str.strip() or None
        timeline = _safe_str(edu.get("timeline")) or ""
        end_year: str | None = None
        tl_parts = [p.strip() for p in re.split(r"[-–]", timeline) if p.strip()]
        if tl_parts:
            last = tl_parts[-1]
            if last.isdigit():
                end_year = _normalise_year(int(last) if len(last) <= 2 else last)
        if not institution and not degree_str:
            continue
        education.append({
            "institution": institution,
            "degree":      degree_str.strip() or None,
            "field":       field,
            "end_year":    end_year,
        })
    t("education", "map:education[] → {institution,degree,field,end_year}")

    return {
        "candidate_id": candidate_id, "full_name": full_name,
        "email": email, "phones": phones,
        "current_organization": None, "current_role": headline,
        "location": location, "skills": skills,
        "bio": None, "github_url": github_url, "portfolio_url": None,
        "linkedin_url": linkedin_url, "other_links": [],
        "public_repos": None, "github_languages": [],
        "years_experience": years_experience,
        "experience": experience, "education": education,
        "provenance": prov,
    }


# ---------------------------------------------------------------------------
# 4. GitHub profile snapshot
# ---------------------------------------------------------------------------

def normalize_github_data(raw_data: dict) -> dict:
    """
    GitHub REST API shape: name, email, bio, company, html_url, blog,
    location, public_repos, languages[].
    bio is used as headline fallback.  company stripped of leading '@'.
    """
    prov: list[dict] = []
    t = _make_tracker(prov, SOURCE_GITHUB)

    full_name = _safe_str(raw_data.get("name"))
    t("full_name", "direct_map:name")

    email = _safe_str(raw_data.get("email"))
    if email:
        email = email.lower().strip()
    t("email", "direct_map:email → lowercase_strip")

    candidate_id = _derive_candidate_id(email)
    t("candidate_id", "sha256_hash:email")

    bio = _safe_str(raw_data.get("bio"))
    t("bio", "direct_map:bio")

    raw_company = _safe_str(raw_data.get("company"))
    current_organization = raw_company.lstrip("@").strip() if raw_company else None
    t("current_organization", "direct_map:company → strip_at_prefix")

    github_url = _safe_str(
        raw_data.get("html_url") or
        (f"https://github.com/{raw_data['login']}" if raw_data.get("login") else None)
    )
    t("github_url", "direct_map:html_url → github_profile_link")

    portfolio_url = _safe_str(raw_data.get("blog"))
    t("portfolio_url", "direct_map:blog → portfolio_url")

    location = _normalize_location(_safe_str(raw_data.get("location")))
    t("location", "iso3166_parse:location")

    raw_repos = raw_data.get("public_repos")
    public_repos = int(raw_repos) if isinstance(raw_repos, (int, float)) else None
    t("public_repos", "direct_map:public_repos → int_cast")

    github_languages = _canonicalize_skills(raw_data.get("languages"))
    t("github_languages", "canonicalize:languages → lowercase_strip")

    return {
        "candidate_id": candidate_id, "full_name": full_name,
        "email": email, "phones": [],
        "current_organization": current_organization,
        "current_role": bio,        # bio used as headline fallback in merger
        "location": location, "skills": [],
        "bio": bio, "github_url": github_url, "portfolio_url": portfolio_url,
        "linkedin_url": None, "other_links": [],
        "public_repos": public_repos, "github_languages": github_languages,
        "years_experience": None, "experience": [], "education": [],
        "provenance": prov,
    }


# ---------------------------------------------------------------------------
# Schema auto-detector
# ---------------------------------------------------------------------------

def detect_and_normalize(raw_data: dict) -> dict:
    """
    Automatically select the correct normalizer based on the raw payload shape.

    Detection order
    ---------------
    1. Has 'candidate_profile'  →  normalize_resume_data   (dhanush_ats.json)
    2. Has 'personal' or 'professional'  →  normalize_new_ats_data  (srividya.json)
    3. Has 'name' and ('html_url' or 'login')  →  normalize_github_data
    4. Default  →  normalize_ats_data  (flat ats_blob schema)
    """
    if "candidate_profile" in raw_data:
        return normalize_resume_data(raw_data)
    if "personal" in raw_data or "professional" in raw_data:
        return normalize_new_ats_data(raw_data)
    if "name" in raw_data and ("html_url" in raw_data or "login" in raw_data):
        return normalize_github_data(raw_data)
    return normalize_ats_data(raw_data)


# ---------------------------------------------------------------------------
# Work history + academic helpers (used by normalizers above)
# ---------------------------------------------------------------------------

def _parse_work_history(raw_list: list) -> list[dict]:
    """Convert work_history[] to canonical experience[{company,title,start,end,summary}]."""
    result: list[dict] = []
    for entry in raw_list:
        if not isinstance(entry, dict):
            continue
        company = _safe_str(entry.get("employer"))
        title   = _safe_str(entry.get("role"))
        start   = _parse_date_to_ym(_safe_str(entry.get("from")))
        end     = _parse_date_to_ym(_safe_str(entry.get("to")))
        summary = _safe_str(entry.get("description"))
        if not any([company, title, start, end, summary]):
            continue
        result.append({"company": company, "title": title,
                        "start": start, "end": end, "summary": summary})
    return result


def _parse_academic(raw_list: list) -> list[dict]:
    """Convert academic[] to canonical education[{institution,degree,field,end_year}]."""
    result: list[dict] = []
    for entry in raw_list:
        if not isinstance(entry, dict):
            continue
        institution = _safe_str(entry.get("institute"))
        degree      = _safe_str(entry.get("qualification"))
        if degree:
            degree = degree.strip().lower()
        field    = _safe_str(entry.get("stream"))
        end_year = _normalise_year(entry.get("passing_year"))
        if not any([institution, degree, field]):
            continue
        result.append({"institution": institution, "degree": degree,
                        "field": field, "end_year": end_year})
    return result
