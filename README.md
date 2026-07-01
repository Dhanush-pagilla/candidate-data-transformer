# Multi-Source Candidate Data Transformer

Eightfold Engineering Intern Assessment — Jul–Dec 2026.

Ingests candidate data from two source types (ATS JSON blob + GitHub profile snapshot), merges them into one clean canonical profile, and projects it to any consumer shape via a runtime config.

---

## Setup

```bash
pip install pycountry phonenumbers
```

No other dependencies. Python 3.10+ required.

---

## How to run

### Live GitHub profile URL (recommended)

```bash
python main.py --ats data/ats_blob.json --github https://github.com/priya-sharma-dev
```

The pipeline fetches the real profile from the GitHub API and aggregates languages from the candidate's public repos automatically.

### With a custom config

```bash
python main.py --ats data/ats_blob.json --github https://github.com/priya-sharma-dev --config configs/recruiter_api.json
```

### Save output to a file

```bash
python main.py --ats data/ats_blob.json --github https://github.com/priya-sharma-dev --out output/profile.json
```

### Offline fallback (local JSON snapshot)

```bash
python main.py --ats data/ats_blob.json --github data/github_profile.json
```

### ATS only

```bash
python main.py --ats data/ats_blob.json
```

### Higher GitHub API rate limits

The unauthenticated GitHub API allows 60 requests/hour. To raise it to 5000/hour, set your token before running:

```bash
# Windows PowerShell
$env:GITHUB_TOKEN = "ghp_yourtoken"
python main.py --ats data/ats_blob.json --github https://github.com/priya-sharma-dev
```

---

## Project structure

```
candidate-data-transformer/
│
├── main.py                    ← CLI entry point (run this)
├── candidate_transformer.py   ← Full pipeline: all 3 phases
│
├── data/
│   ├── ats_blob.json          ← Structured source (ATS)
│   ├── github_profile.json    ← Unstructured source (GitHub)
│   ├── empty.json             ← Edge-case fixture: empty file
│   └── corrupt.json           ← Edge-case fixture: invalid JSON
│
├── configs/
│   ├── recruiter_api.json     ← Custom config: recruiter view
│   └── minimal.json           ← Custom config: minimal / no metadata
│
├── output/                    ← Written output files land here
│
├── run_phase1.py              ← Phase 1 smoke tests
├── run_phase2.py              ← Phase 2 smoke tests
└── run_phase3.py              ← Phase 3 smoke tests
```

---

## Pipeline overview

```
ingest_source()          reads + validates JSON, isolates broken files
      ↓
normalize_ats_data()     maps ATS field names → canonical schema
normalize_github_data()  maps GitHub fields   → canonical schema
      ↓
merge_and_deduplicate()  SHA-256 candidate_id as match key
                         ATS=0.9 authority beats GitHub=0.7 for identity fields
                         GitHub wins for portfolio links
                         skills unified into {name, confidence, sources[]}
      ↓
calculate_confidence()   field-importance × source-authority scoring
                         honestly-empty fields excluded from denominator
      ↓
project_to_output()      config-driven field selection, renaming,
                         path expressions (field[0], field[].prop),
                         E164 / canonical normalisation switches,
                         on_missing: null | omit | error
      ↓
validate_schema()        type checks + required-field enforcement
```

---

## Canonical output schema

| Field                | Type                              | Notes                      |
|----------------------|-----------------------------------|----------------------------|
| candidate_id         | string                            | SHA-256 of email           |
| full_name            | string                            |                            |
| emails               | string[]                          |                            |
| phones               | string[]                          | E.164 format               |
| location             | {city, region, country}           | country: ISO-3166 alpha-2  |
| links                | {linkedin, github, portfolio, other[]} |                       |
| headline             | string \| null                    |                            |
| current_organization | string \| null                    |                            |
| years_experience     | number \| null                    |                            |
| skills               | [{name, confidence, sources[]}]   | canonical skill names      |
| experience           | [{company, title, start, end, summary}] | dates as YYYY-MM     |
| education            | [{institution, degree, field, end_year}] |                   |
| provenance           | [{field, source, method}]         | full data lineage          |
| overall_confidence   | number                            | 0.0 – 1.0                  |

---

## Running the test suite

```bash
python run_phase1.py
python run_phase2.py
python run_phase3.py
```

All three should end with a `PASSED` banner.

---

## Key design decisions

**Wrong-but-confident is worse than honestly-empty.**
If a field is missing or corrupt, it is stored as `None` / `[]` — never guessed. This prevents bad values from silently polluting downstream hiring decisions.

**Deterministic candidate_id.**
SHA-256 of the normalised email address. Same email from any source always produces the same hash, enabling cross-source deduplication without a database.

**Source authority hierarchy.**
ATS (0.9) beats GitHub (0.7) for identity and professional history. GitHub wins for portfolio links and technical skills. The hierarchy is a single class-level constant — easy to extend.

**Projection is pure.**
`project_to_output` never mutates the canonical record. The internal store is always intact for additional downstream consumers.

**Confidence is honest.**
The scoring formula is `Σ(field_importance × source_authority) / Σ(field_importance)`. Fields that are honestly-empty contribute 0 to the numerator but their full importance weight to the denominator — they create a proportional penalty without crashing anything.
