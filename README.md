# Candidate Data Transformer

A highly configurable multi-source candidate data transformation pipeline that converts noisy information from disparate source systems into a clean, canonical JSON profile.

This project normalizes, merges, validates, and projects candidate data while preserving provenance information and evaluating profile confidence.

---

# Features

- Supports multiple candidate data sources
  - ATS JSON (Structured Source)
  - GitHub Profile URL (Unstructured Source)

- Normalizes candidate information
  - Phone numbers → E.164 format
  - Dates → ISO `YYYY-MM`
  - Country → ISO-3166 Alpha-2
  - Skills → Canonical names

- Deterministic candidate merging
- Duplicate removal across sources
- Provenance tracking for every field
- Overall confidence scoring
- Runtime configurable output projection
- Output schema validation

---

# Project Structure

```text
candidate-data-transformer/
│
├── configs/
│   ├── minimal.json
│   └── recruiter_api.json
│
├── sample_inputs/
│   ├── dhanush_ats.json
│   └── srividya.json
│
├── output/
│   ├── dhanush_canonical.json
│   └── srividya_canonical.json
│
├── transformer/
│   ├── ingestion.py
│   ├── merger.py
│   ├── normalizers.py
│   ├── projection.py
│   ├── constants.py
│   └── utils/
│       ├── dates.py
│       ├── phone.py
│       ├── identity.py
│       ├── location.py
│       ├── skills.py
│       └── text.py
│
├── main.py
├── verify.py
├── requirements.txt
├── .gitignore
└── README.md
```

---

# Pipeline

```text
ATS JSON
      │
      ▼
Extract GitHub Profile URL
      │
      ▼
Fetch GitHub Profile using REST API
      │
      ▼
Normalize Candidate Data
      │
      ▼
Merge ATS + GitHub Data
      │
      ▼
Calculate Provenance & Confidence
      │
      ▼
Apply Runtime Configuration
      │
      ▼
Validate Output Schema
      │
      ▼
Canonical Candidate JSON
```

---

# Canonical Output Schema

| Field | Description |
|--------|-------------|
| `candidate_id` | Deterministic SHA-256 hash generated from normalized email |
| `full_name` | Candidate full name |
| `emails` | List of unique email addresses |
| `phones` | Phone numbers in E.164 format |
| `location` | `{city, region, country}` |
| `links` | `{linkedin, github, portfolio, other[]}` |
| `headline` | Professional headline |
| `years_experience` | Total years of experience |
| `skills` | `[{name, confidence, sources[]}]` |
| `experience` | Work experience |
| `education` | Education details |
| `provenance` | Source information for every field |
| `overall_confidence` | Overall confidence score (0–1) |

---

# Runtime Configuration

The pipeline supports configurable output using runtime JSON configuration.

Supported capabilities include:

- Select output fields
- Rename output fields
- Apply field-specific normalizers
- Enable/Disable provenance
- Enable/Disable confidence score
- Configure missing-value behavior (`null`, `omit`, `error`)

Example:

```bash
python main.py --ats sample_inputs/dhanush_ats.json --config configs/recruiter_api.json
```

---

# Requirements

- Python 3.10+
- pycountry
- phonenumbers
- requests

Install dependencies:

```bash
pip install -r requirements.txt
```

---

# Running the Project

Process candidate data:

```bash
python main.py --ats sample_inputs/dhanush_ats.json
```

Run verification:

```bash
python verify.py
```

---

# Design Decisions

### Modular Pipeline

Each pipeline stage performs one responsibility:

- Data ingestion
- Extraction
- Normalization
- Merge
- Projection
- Validation

---

### Deterministic Identity

Candidates are identified using a SHA-256 hash of the normalized email to ensure consistent merging.

---

### Source Priority

Conflicts are resolved using source priority.

| Source | Priority |
|---------|----------|
| ATS | High |
| GitHub | Medium |

---

### Pure Projection Layer

Projection reshapes the final JSON without modifying the internal canonical record.

---

### Confidence Scoring

Confidence is calculated based on:

- Source reliability
- Field completeness
- Data consistency

---

# Edge Cases Handled

- Missing GitHub profile
- Invalid GitHub URL
- Invalid phone numbers
- Duplicate skills
- Duplicate emails
- Missing optional fields
- Empty ATS JSON
- Invalid country names
- Conflicting values between ATS and GitHub
- Network/API failures
- GitHub rate limiting
- Candidate with no work experience

---

# Future Improvements

- Resume (PDF/DOCX) parsing
- LinkedIn integration
- OCR support
- AI-based confidence scoring
- Additional ATS connectors
- Multi-language normalization

---

# Technologies Used

- Python 3
- GitHub REST API
- Requests
- PyCountry
- PhoneNumbers
- JSON
- SHA-256
- Git

---

# Author

**Pagilla Dhanush**

Email: **pagilladhanush.151@gmail.com**

GitHub: **https://github.com/Dhanush-pagilla**

---

# Assignment

Developed as part of the **Eightfold Engineering Internship Assignment (Jul–Dec 2026)**

**Project:** Multi-Source Candidate Data Transformer
