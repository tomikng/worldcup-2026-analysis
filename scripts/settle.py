#!/usr/bin/env python3
"""Settle pending betslips against results and rebuild data/ledger.json.

The only authority on slip status, payouts, and the ledger (see CLAUDE.md).
Idempotent: re-running never changes already-settled slips, and the ledger
is rebuilt from scratch from all betslip files.

Usage: python3 scripts/settle.py
"""

import json
import sys
from pathlib import Path

STARTING_BANKROLL = 1000.0
FUTURES_BUDGET = 100.0


def _grade_total(value: float, line: float, selection: str) -> str:
    if value == line:
        return "void"  # push on whole-number line
    return "won" if (selection == "over") == (value > line) else "lost"


def grade_leg(leg: dict, result: dict) -> str:
    """Grade one leg against a match result -> 'won' | 'lost' | 'void'.

    Stat-dependent markets (cards, red_card, corners) void when the result
    lacks verified stats — a missing match report must never corrupt the
    ledger.
    """
    if result["status"] in ("POSTPONED", "CANCELLED"):
        return "void"

    home, away = result["home_goals"], result["away_goals"]
    market, selection = leg["market"], leg["selection"]

    if market == "h2h":
        outcome = "home" if home > away else "away" if away > home else "draw"
        return "won" if selection == outcome else "lost"

    if market == "double_chance":
        outcome = "home" if home > away else "away" if away > home else "draw"
        covers = {"1x": ("home", "draw"), "12": ("home", "away"),
                  "x2": ("draw", "away")}[selection]
        return "won" if outcome in covers else "lost"

    if market == "dnb":
        if home == away:
            return "void"
        outcome = "home" if home > away else "away"
        return "won" if selection == outcome else "lost"

    if market == "totals":
        return _grade_total(home + away, leg["line"], selection)

    if market == "team_totals":
        goals = home if leg["side"] == "home" else away
        return _grade_total(goals, leg["line"], selection)

    if market == "correct_score":
        return "won" if selection == f"{home}-{away}" else "lost"

    if market == "btts":
        both = home > 0 and away > 0
        return "won" if (selection == "yes") == both else "lost"

    if market == "cards":
        hc, ac = result.get("home_cards"), result.get("away_cards")
        if hc is None or ac is None:
            return "void"
        return _grade_total(hc + ac, leg["line"], selection)

    if market == "red_card":
        hr, ar = result.get("home_reds"), result.get("away_reds")
        if hr is None or ar is None:
            return "void"
        red_shown = hr + ar > 0
        return "won" if (selection == "yes") == red_shown else "lost"

    if market == "corners":
        hc, ac = result.get("home_corners"), result.get("away_corners")
        if hc is None or ac is None:
            return "void"
        return _grade_total(hc + ac, leg["line"], selection)

    raise ValueError(f"unknown market: {market!r}")


def settle_slip(slip: dict, results_by_match: dict, now: str) -> dict:
    """Settle a slip if every leg has a result. Already-settled slips and
    slips with missing results are returned unchanged."""
    if slip["status"] != "pending":
        return slip
    if any(leg["match_id"] not in results_by_match for leg in slip["legs"]):
        return slip

    grades = [grade_leg(leg, results_by_match[leg["match_id"]])
              for leg in slip["legs"]]

    if "lost" in grades:
        status, payout = "lost", 0.0
    elif all(g == "void" for g in grades):
        status, payout = "void", slip["stake"]
    else:
        odds = 1.0
        for leg, grade in zip(slip["legs"], grades):
            if grade == "won":
                odds *= leg["odds"]
        status, payout = "won", round(slip["stake"] * odds, 2)

    slip.update(status=status, payout=payout, settled_at=now)
    return slip


def _empty_market_stats() -> dict:
    return {"staked": 0.0, "returned": 0.0, "won": 0, "lost": 0}


def _futures_section(futures: dict | None) -> dict:
    """Settled-only futures math; positions' statuses are set by the /settle
    agent after verifying official resolutions."""
    budget = (futures or {}).get("budget", FUTURES_BUDGET)
    section = {"budget": budget, "staked": 0.0, "remaining": budget,
               "returned": 0.0, "profit": 0.0, "open": 0, "won": 0, "lost": 0}
    settled_staked = 0.0
    for pos in (futures or {}).get("positions", []):
        section["staked"] += pos["stake"]
        section[pos["status"]] += 1
        if pos["status"] == "won":
            section["returned"] += pos["stake"] / pos["entry_price"]
        if pos["status"] in ("won", "lost"):
            settled_staked += pos["stake"]
    section["remaining"] = round(budget - section["staked"], 2)
    section["profit"] = round(section["returned"] - settled_staked, 2)
    section["staked"] = round(section["staked"], 2)
    section["returned"] = round(section["returned"], 2)
    return section


def rebuild_ledger(betslip_days: list[dict], futures: dict | None = None,
                   now: str = "") -> dict:
    """Rebuild the full ledger from all betslip day-files (sorted by date)."""
    stats = {"total_staked": 0.0, "total_returned": 0.0, "profit": 0.0,
             "roi": 0.0, "slips_won": 0, "slips_lost": 0, "slips_void": 0,
             "slips_pending": 0, "hit_rate": 0.0, "by_market": {}}
    settled_staked = 0.0
    history = []
    bankroll = STARTING_BANKROLL

    for day in sorted(betslip_days, key=lambda d: d["date"]):
        for slip in day["slips"]:
            stake, status = slip["stake"], slip["status"]
            stats["total_staked"] += stake
            bankroll -= stake
            if status != "pending":
                stats["total_returned"] += slip["payout"]
                bankroll += slip["payout"]
                settled_staked += stake
            stats[f"slips_{status}"] += 1

            market = slip["legs"][0]["market"] if slip["type"] == "single" else None
            if market is not None:
                m = stats["by_market"].setdefault(market, _empty_market_stats())
                m["staked"] += stake
                if status != "pending":
                    m["returned"] += slip["payout"]
                if status in ("won", "lost"):
                    m[status] += 1
        history.append({"date": day["date"], "bankroll": round(bankroll, 2)})

    # Settled-only P/L: pending stakes are exposure (visible in bankroll),
    # not yet profit or loss.
    stats["profit"] = round(stats["total_returned"] - settled_staked, 2)
    decided = stats["slips_won"] + stats["slips_lost"]
    stats["hit_rate"] = round(stats["slips_won"] / decided, 4) if decided else 0.0
    stats["roi"] = round(stats["profit"] / settled_staked, 4) if settled_staked else 0.0
    for m in stats["by_market"].values():
        m["staked"], m["returned"] = round(m["staked"], 2), round(m["returned"], 2)
    stats["total_staked"] = round(stats["total_staked"], 2)
    stats["total_returned"] = round(stats["total_returned"], 2)

    return {"starting_bankroll": STARTING_BANKROLL,
            "bankroll": round(bankroll, 2), "updated_at": now,
            "stats": stats, "futures": _futures_section(futures),
            "history": history}


def run(data_dir: Path, now: str) -> None:
    """Settle every pending slip that has results, then rebuild the ledger."""
    betslips_dir = data_dir / "betslips"
    results_by_match: dict[str, dict] = {}
    for f in sorted((data_dir / "results").glob("*.json")):
        for match in json.loads(f.read_text())["matches"]:
            results_by_match[match["match_id"]] = match

    betslip_days = []
    for f in sorted(betslips_dir.glob("*.json")) if betslips_dir.exists() else []:
        day = json.loads(f.read_text())
        before = json.dumps(day, sort_keys=True)
        day["slips"] = [settle_slip(s, results_by_match, now) for s in day["slips"]]
        if json.dumps(day, sort_keys=True) != before:
            f.write_text(json.dumps(day, indent=2, ensure_ascii=False) + "\n")
            print(f"settled {f.name}")
        betslip_days.append(day)

    futures_file = data_dir / "futures.json"
    futures = json.loads(futures_file.read_text()) if futures_file.exists() else None
    ledger = rebuild_ledger(betslip_days, futures=futures, now=now)
    (data_dir / "ledger.json").write_text(
        json.dumps(ledger, indent=2, ensure_ascii=False) + "\n")
    print(f"ledger: bankroll {ledger['bankroll']} "
          f"({ledger['stats']['slips_pending']} pending slips)")


def main() -> int:
    from fdorg import DATA_DIR, now_iso
    run(data_dir=DATA_DIR, now=now_iso())
    return 0


if __name__ == "__main__":
    sys.exit(main())
