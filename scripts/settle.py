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
MARKETS = ("h2h", "totals", "btts")


def grade_leg(leg: dict, result: dict) -> str:
    """Grade one leg against a match result -> 'won' | 'lost' | 'void'."""
    if result["status"] in ("POSTPONED", "CANCELLED"):
        return "void"

    home, away = result["home_goals"], result["away_goals"]
    market, selection = leg["market"], leg["selection"]

    if market == "h2h":
        outcome = "home" if home > away else "away" if away > home else "draw"
        return "won" if selection == outcome else "lost"

    if market == "totals":
        total = home + away
        line = leg["line"]
        if total == line:
            return "void"  # push on whole-number line
        over = total > line
        return "won" if (selection == "over") == over else "lost"

    if market == "btts":
        both = home > 0 and away > 0
        return "won" if (selection == "yes") == both else "lost"

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


def rebuild_ledger(betslip_days: list[dict], now: str = "") -> dict:
    """Rebuild the full ledger from all betslip day-files (sorted by date)."""
    stats = {"total_staked": 0.0, "total_returned": 0.0, "profit": 0.0,
             "roi": 0.0, "slips_won": 0, "slips_lost": 0, "slips_void": 0,
             "slips_pending": 0, "hit_rate": 0.0,
             "by_market": {m: _empty_market_stats() for m in MARKETS}}
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
            if market in stats["by_market"]:
                m = stats["by_market"][market]
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
            "stats": stats, "history": history}


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

    ledger = rebuild_ledger(betslip_days, now=now)
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
