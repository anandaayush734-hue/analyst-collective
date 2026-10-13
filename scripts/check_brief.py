#!/usr/bin/env python3
"""Validate a brief written by the scheduled Claude task (no API key needed).

Usage:  python3 scripts/check_brief.py 2026-10-14 [--pr-body /tmp/pr.md]

- Reads src/data/briefs/<DATE>.json
- Fixes/drops invalid items and flags advice-like wording
- Moves any "deals" in the brief into src/data/deals.json (de-duplicated)
- Optionally writes a review checklist (used as the pull-request description)
Exit code 1 if the file is missing or not valid JSON.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from daily_brief import BRIEFS, finalize  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    date = sys.argv[1]
    body = sys.argv[sys.argv.index("--pr-body") + 1] if "--pr-body" in sys.argv else None
    path = BRIEFS / f"{date}.json"
    try:
        brief = json.loads(path.read_text())
    except FileNotFoundError:
        print(f"ERROR: {path} not found")
        return 1
    except json.JSONDecodeError as e:
        print(f"ERROR: {path} is not valid JSON: {e}")
        return 1
    finalize(brief, date, body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
