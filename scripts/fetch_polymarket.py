#!/usr/bin/env python3
"""Fetch Polymarket prices (free public Gamma API, no key required).

Match mode:   python3 scripts/fetch_polymarket.py 2026-06-11
              -> data/polymarket/2026-06-11.json (per-fixture markets/prices)
Futures mode: python3 scripts/fetch_polymarket.py --futures
              -> data/polymarket/futures.json (tournament/group winner prices)

Exit 0 even if some matches aren't listed (recorded as listed=false);
exit 1 only when the API itself is unreachable.
"""

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

from fdorg import DATA_DIR, EXIT_ERROR, EXIT_OK, now_iso, write_json

GAMMA = "https://gamma-api.polymarket.com"


def get_json(path: str, params: dict) -> dict | list:
    url = f"{GAMMA}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "wc26-desk/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)
    except (urllib.error.URLError, json.JSONDecodeError) as e:
        print(f"polymarket API error on {path}: {e}", file=sys.stderr)
        sys.exit(EXIT_ERROR)


def parse_listish(value) -> list:
    """Gamma encodes outcomes/prices as JSON strings ('["Yes","No"]')."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return []
    return value or []


def normalize_markets(event: dict) -> list[dict]:
    markets = []
    for m in event.get("markets", []):
        outcomes = parse_listish(m.get("outcomes"))
        prices = [float(p) for p in parse_listish(m.get("outcomePrices"))]
        if not outcomes or len(outcomes) != len(prices):
            continue
        markets.append({
            "question": m.get("question") or m.get("groupItemTitle") or "",
            "group_item": m.get("groupItemTitle") or "",
            "outcomes": outcomes,
            "prices": prices,
        })
    return markets


# Polymarket titles use FIFA naming; map common names to accepted variants.
ALIASES = {
    "south korea": ["south korea", "korea republic"],
    "iran": ["iran", "ir iran"],
    "usa": ["usa", "united states"],
    "ivory coast": ["ivory coast", "côte d'ivoire", "cote d'ivoire"],
    "cape verde": ["cape verde", "cabo verde"],
}


def _variants(team: str) -> list[str]:
    return ALIASES.get(team.lower(), [team.lower()])


def find_match_event(fixture: dict) -> dict | None:
    """Search for the event covering this fixture, matched by both team
    names (any FIFA-naming variant) in the title and endDate within 3 days
    of kickoff."""
    kickoff = datetime.fromisoformat(fixture["kickoff_utc"].replace("Z", "+00:00"))
    queries = [f"{h} {a}" for h in _variants(fixture["home"])
               for a in _variants(fixture["away"])]
    for query in queries:
        found = get_json("/public-search", {"q": query, "limit_per_type": 10})
        for event in found.get("events", []):
            title = (event.get("title") or "").lower()
            if not (any(h in title for h in _variants(fixture["home"]))
                    and any(a in title for a in _variants(fixture["away"]))):
                continue
            end = event.get("endDate")
            if end:
                end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
                if abs((end_dt - kickoff).days) > 3:
                    continue
            return event
    return None


def run_match_mode(date: str) -> None:
    fixtures_file = DATA_DIR / "fixtures" / f"{date}.json"
    if not fixtures_file.exists():
        print(f"no fixtures file for {date}; run fetch_fixtures.py first",
              file=sys.stderr)
        sys.exit(EXIT_ERROR)
    fixtures = json.loads(fixtures_file.read_text())["matches"]

    matches = []
    for fixture in fixtures:
        event = find_match_event(fixture)
        entry = {"match_id": fixture["match_id"], "home": fixture["home"],
                 "away": fixture["away"], "listed": event is not None}
        if event:
            entry["event_slug"] = event["slug"]
            entry["url"] = f"https://polymarket.com/event/{event['slug']}"
            entry["markets"] = normalize_markets(event)
        else:
            print(f"not listed on Polymarket: {fixture['home']} v {fixture['away']}")
        matches.append(entry)

    write_json(DATA_DIR / "polymarket" / f"{date}.json",
               {"date": date, "source": "polymarket gamma API",
                "collected_at": now_iso(), "matches": matches})
    listed = sum(1 for m in matches if m["listed"])
    print(f"{listed}/{len(matches)} match(es) listed on Polymarket")


FUTURES_KEYWORDS = ("world cup winner", "group", "golden boot", "to reach")


def run_futures_mode() -> None:
    # Polymarket tags WC events inconsistently (the tournament-winner event
    # carries fifa-world-cup but not world-cup) — query both and dedupe.
    events_by_slug: dict[str, dict] = {}
    for tag in ("world-cup", "fifa-world-cup"):
        for event in get_json("/events", {"tag_slug": tag, "closed": "false",
                                          "limit": 100, "order": "volume",
                                          "ascending": "false"}):
            events_by_slug.setdefault(event["slug"], event)
    snapshot = []
    for event in events_by_slug.values():
        title = (event.get("title") or "").strip()
        if not any(k in title.lower() for k in FUTURES_KEYWORDS):
            continue
        outcomes = []
        for m in normalize_markets(event):
            name = m["group_item"] or m["question"]
            # binary team markets: price of the "Yes" outcome
            try:
                yes_idx = [o.lower() for o in m["outcomes"]].index("yes")
            except ValueError:
                yes_idx = 0
            outcomes.append({"name": name, "price": m["prices"][yes_idx]})
        outcomes.sort(key=lambda o: -o["price"])
        snapshot.append({"title": title, "slug": event["slug"],
                         "url": f"https://polymarket.com/event/{event['slug']}",
                         "volume": event.get("volume"),
                         "outcomes": outcomes[:12]})

    write_json(DATA_DIR / "polymarket" / "futures.json",
               {"source": "polymarket gamma API", "collected_at": now_iso(),
                "events": snapshot})
    print(f"{len(snapshot)} futures event(s) captured")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("date", nargs="?", help="matchday YYYY-MM-DD")
    parser.add_argument("--futures", action="store_true")
    args = parser.parse_args()

    if args.futures:
        run_futures_mode()
    elif args.date:
        run_match_mode(args.date)
    else:
        parser.error("provide a date or --futures")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
