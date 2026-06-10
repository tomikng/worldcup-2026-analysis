#!/usr/bin/env python3
"""Fetch World Cup fixtures for a date -> data/fixtures/YYYY-MM-DD.json

Usage: python3 scripts/fetch_fixtures.py 2026-06-11
"""

import argparse
import sys

import fdorg


def to_fixture(m: dict) -> dict:
    return {
        "match_id": f"fd-{m['id']}",
        "kickoff_utc": m["utcDate"],
        "stage": m.get("stage", ""),
        "group": m.get("group") or "",
        "home": (m.get("homeTeam") or {}).get("name") or "TBD",
        "away": (m.get("awayTeam") or {}).get("name") or "TBD",
        "venue": m.get("venue") or "",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("date", help="UTC date YYYY-MM-DD")
    args = parser.parse_args()

    token = fdorg.require_token()
    matches = fdorg.fetch_matches(args.date, token)
    out = {
        "date": args.date,
        "source": "football-data.org",
        "fetched_at": fdorg.now_iso(),
        "matches": [to_fixture(m) for m in matches],
    }
    fdorg.write_json(fdorg.DATA_DIR / "fixtures" / f"{args.date}.json", out)
    print(f"{len(out['matches'])} fixture(s) for {args.date}")
    return fdorg.EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
