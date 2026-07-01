"""
main.py
=======
CLI entry point for the Multi-Source Candidate Data Transformer.

Usage
-----
  # Default config  →  configs/minimal.json  (4 fields, no metadata)
  python main.py --ats sample_inputs/dhanush_ats.json

  # Recruiter view  →  configs/recruiter_api.json  (8 fields, with confidence)
  python main.py --ats sample_inputs/dhanush_ats.json --config configs/recruiter_api.json

  # Full canonical schema  →  all 16 fields
  python main.py --ats sample_inputs/dhanush_ats.json --config configs/full_schema.json

  # Explicit GitHub source
  python main.py --ats sample_inputs/dhanush_ats.json --github https://github.com/Dhanush-pagilla

  # Write to file
  python main.py --ats sample_inputs/dhanush_ats.json --out output/dhanush_canonical.json

GitHub URL auto-extraction
--------------------------
If --github is omitted, the pipeline scans the ATS file for an embedded
GitHub URL (profile_links.github_url) and fetches it automatically.

GitHub token (higher rate limits: 60 → 5 000 req/hr)
------------------------------------------------------
  $env:GITHUB_TOKEN = "ghp_yourtoken"
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from transformer import run

# Default config file when --config is not supplied.
_DEFAULT_CONFIG_PATH = "configs/minimal.json"


def load_config(path: str) -> dict:
    """Load and parse a JSON projection config file."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"[error] Config not found: '{path}'", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as exc:
        print(f"[error] Config is not valid JSON: {exc}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python main.py",
        description="Multi-Source Candidate Data Transformer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--ats",    metavar="FILE",
                        help="ATS JSON file (structured source).")
    parser.add_argument("--github", metavar="URL_OR_FILE",
                        help="GitHub profile URL or local JSON snapshot. "
                             "Auto-extracted from ATS if omitted.")
    parser.add_argument("--config", metavar="FILE",
                        default=_DEFAULT_CONFIG_PATH,
                        help=f"JSON projection config. "
                             f"Defaults to '{_DEFAULT_CONFIG_PATH}'.")
    parser.add_argument("--out",    metavar="FILE",
                        help="Write output to this file (default: stdout).")
    parser.add_argument("--quiet",  action="store_true",
                        help="Suppress informational messages.")

    args = parser.parse_args()
    if not args.ats and not args.github:
        parser.error("Provide at least one source: --ats and/or --github")

    config      = load_config(args.config)
    config_name = Path(args.config).stem   # e.g. "minimal" or "recruiter_api"

    # Print a visible banner so it's clear which config is active.
    if not args.quiet:
        print(f"\n{'─'*60}", file=sys.stderr)
        print(f"  Config : {args.config}  ({config_name})", file=sys.stderr)
        fields = [f["path"] for f in config.get("fields", [])]
        print(f"  Fields : {', '.join(fields)}", file=sys.stderr)
        print(f"{'─'*60}", file=sys.stderr)

    run(
        ats_path = args.ats,
        github   = args.github,
        config   = config,
        out_path = args.out,
        quiet    = args.quiet,
    )


if __name__ == "__main__":
    main()
