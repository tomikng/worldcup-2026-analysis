#!/usr/bin/env python3
"""Regenerate data/index.json — the dashboard's directory of available data.

Usage: python3 scripts/build_index.py
"""

import json
import sys
from pathlib import Path

from fdorg import DATA_DIR, EXIT_OK, now_iso, write_json


def dates_in(folder: Path) -> list[str]:
    if not folder.exists():
        return []
    return sorted(p.stem for p in folder.glob("*.json"))


def ticket_index() -> dict[str, list[str]]:
    """date -> list of match_ids that have analysis tickets."""
    tickets_dir = DATA_DIR / "tickets"
    if not tickets_dir.exists():
        return {}
    return {
        day.name: sorted(p.stem for p in day.glob("*.json"))
        for day in sorted(tickets_dir.iterdir())
        if day.is_dir()
    }


def main() -> int:
    index = {
        "generated_at": now_iso(),
        "fixtures": dates_in(DATA_DIR / "fixtures"),
        "results": dates_in(DATA_DIR / "results"),
        "odds": dates_in(DATA_DIR / "odds"),
        "betslips": dates_in(DATA_DIR / "betslips"),
        "polymarket": [d for d in dates_in(DATA_DIR / "polymarket") if d != "futures"],
        "tickets": ticket_index(),
        "has_ledger": (DATA_DIR / "ledger.json").exists(),
        "has_futures": (DATA_DIR / "futures.json").exists(),
    }
    write_json(DATA_DIR / "index.json", index)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
