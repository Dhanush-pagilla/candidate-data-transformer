"""
main.py
=======
CLI entry point for the Multi-Source Candidate Data Transformer.

Usage
-----
  python main.py --ats sample_inputs/dhanush_ats.json
  python main.py --ats sample_inputs/srividya.json
  python main.py --ats sample_inputs/dhanush_ats.json --github sample_inputs/dhanush_github.json
  python main.py --ats sample_inputs/dhanush_ats.json --github https://github.com/Dhanush-pagilla
  python main.py --ats sample_inputs/dhanush_ats.json --config configs/recruiter_api.json
  python main.py --ats sample_inputs/dhanush_ats.json --out output/dhanush_canonical.json

GitHub URL auto-extraction
--------------------------
If --github is omitted, the pipeline scans the ATS file for an embedded
GitHub URL (profile_links.github_url) and fetches it automatically.

GitHub token (for higher rate limits: 60 → 5000 req/hr)
---------------------------------------------------------
  Windows PowerShell:  $env:GITHUB_TOKEN = "ghp_yourtoken"
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from transformer import run, DEFAULT_CONFIG


def load_config(path: str) -> dict:
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
                        help="GitHub profile URL or local JSON. "
                             "Auto-extracted from ATS if omitted.")
    parser.add_argument("--config", metavar="FILE",
                        help="JSON projection config. Defaults to canonical schema.")
    parser.add_argument("--out",    metavar="FILE",
                        help="Write output to this file (default: stdout).")
    parser.add_argument("--quiet",  action="store_true",
                        help="Suppress informational messages.")

    args = parser.parse_args()
    if not args.ats and not args.github:
        parser.error("Provide at least one source: --ats and/or --github")

    config = load_config(args.config) if args.config else DEFAULT_CONFIG

    run(
        ats_path = args.ats,
        github   = args.github,
        config   = config,
        out_path = args.out,
        quiet    = args.quiet,
    )


if __name__ == "__main__":
    main()
