#!/usr/bin/env python3
"""Fetch finished World Cup results for a date -> data/results/YYYY-MM-DD.json

Usage: python3 scripts/fetch_results.py 2026-06-11
"""

import argparse
import sys

import fdorg

# football-data statuses mapped to our schema; anything else (SCHEDULED,
# TIMED, IN_PLAY, PAUSED) is not yet settleable and gets skipped.
STATUS_MAP = {
    "FINISHED": "FINISHED",
    "AWARDED": "FINISHED",
    "POSTPONED": "POSTPONED",
    "CANCELLED": "CANCELLED",
}


def to_result(m: dict) -> dict | None:
    status = STATUS_MAP.get(m.get("status", ""))
    if status is None:
        return None
    full_time = (m.get("score") or {}).get("fullTime") or {}
    result = {
        "match_id": f"fd-{m['id']}",
        "home": (m.get("homeTeam") or {}).get("name") or "TBD",
        "away": (m.get("awayTeam") or {}).get("name") or "TBD",
        "home_goals": full_time.get("home"),
        "away_goals": full_time.get("away"),
        "status": status,
    }
    duration = (m.get("score") or {}).get("duration", "")
    if duration == "PENALTY_SHOOTOUT":
        winner = (m.get("score") or {}).get("winner", "")
        result["notes"] = f"decided on penalties (winner: {winner})"
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("date", help="UTC date YYYY-MM-DD")
    args = parser.parse_args()

    token = fdorg.require_token()
    matches = fdorg.fetch_matches(args.date, token)
    results = [r for r in (to_result(m) for m in matches) if r is not None]
    out = {
        "date": args.date,
        "source": "football-data.org",
        "fetched_at": fdorg.now_iso(),
        "matches": results,
    }
    fdorg.write_json(fdorg.DATA_DIR / "results" / f"{args.date}.json", out)
    print(f"{len(results)} settleable result(s) for {args.date}")
    return fdorg.EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
