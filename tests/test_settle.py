import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import settle


def leg(market="h2h", selection="home", odds=2.0, line=None, match_id="fd-1"):
    return {"match_id": match_id, "market": market, "selection": selection,
            "line": line, "odds": odds, "model_prob": 0.5, "edge": 0.1,
            "rationale": "test"}


def result(home_goals=2, away_goals=1, status="FINISHED", match_id="fd-1"):
    return {"match_id": match_id, "home": "A", "away": "B",
            "home_goals": home_goals, "away_goals": away_goals, "status": status}


def slip(legs, stake=10.0, slip_type=None, slip_id="2026-06-11-S1"):
    if slip_type is None:
        slip_type = "single" if len(legs) == 1 else "accumulator"
    combined = 1.0
    for l in legs:
        combined *= l["odds"]
    return {"slip_id": slip_id, "type": slip_type, "stake": stake, "legs": legs,
            "combined_odds": round(combined, 4), "status": "pending",
            "payout": None, "settled_at": None, "rationale": "test"}


# --- grade_leg -------------------------------------------------------------

class TestGradeLegH2H:
    def test_home_selection_wins_on_home_victory(self):
        assert settle.grade_leg(leg(selection="home"), result(2, 1)) == "won"

    def test_home_selection_loses_on_away_victory(self):
        assert settle.grade_leg(leg(selection="home"), result(0, 1)) == "lost"

    def test_draw_selection_wins_on_draw(self):
        assert settle.grade_leg(leg(selection="draw"), result(1, 1)) == "won"

    def test_away_selection_wins_on_away_victory(self):
        assert settle.grade_leg(leg(selection="away"), result(0, 3)) == "won"


class TestGradeLegTotals:
    def test_over_wins_above_line(self):
        l = leg(market="totals", selection="over", line=2.5)
        assert settle.grade_leg(l, result(2, 1)) == "won"

    def test_over_loses_below_line(self):
        l = leg(market="totals", selection="over", line=2.5)
        assert settle.grade_leg(l, result(1, 0)) == "lost"

    def test_under_wins_below_line(self):
        l = leg(market="totals", selection="under", line=2.5)
        assert settle.grade_leg(l, result(0, 0)) == "won"

    def test_exact_whole_line_is_void_push(self):
        l = leg(market="totals", selection="over", line=2.0)
        assert settle.grade_leg(l, result(1, 1)) == "void"


class TestGradeLegBTTS:
    def test_yes_wins_when_both_score(self):
        l = leg(market="btts", selection="yes")
        assert settle.grade_leg(l, result(1, 2)) == "won"

    def test_yes_loses_on_clean_sheet(self):
        l = leg(market="btts", selection="yes")
        assert settle.grade_leg(l, result(2, 0)) == "lost"

    def test_no_wins_on_goalless_draw(self):
        l = leg(market="btts", selection="no")
        assert settle.grade_leg(l, result(0, 0)) == "won"


class TestGradeLegVoid:
    def test_postponed_match_voids_leg(self):
        assert settle.grade_leg(leg(), result(None, None, "POSTPONED")) == "void"

    def test_cancelled_match_voids_leg(self):
        assert settle.grade_leg(leg(), result(None, None, "CANCELLED")) == "void"


# --- settle_slip -----------------------------------------------------------

NOW = "2026-06-12T08:00:00Z"


class TestSettleSlip:
    def test_winning_single_pays_stake_times_odds(self):
        s = settle.settle_slip(slip([leg(odds=2.5)]), {"fd-1": result(2, 1)}, NOW)
        assert s["status"] == "won"
        assert s["payout"] == 25.0
        assert s["settled_at"] == NOW

    def test_losing_single_pays_zero(self):
        s = settle.settle_slip(slip([leg(selection="away")]), {"fd-1": result(2, 1)}, NOW)
        assert s["status"] == "lost"
        assert s["payout"] == 0.0

    def test_void_single_returns_stake(self):
        s = settle.settle_slip(slip([leg()]), {"fd-1": result(None, None, "POSTPONED")}, NOW)
        assert s["status"] == "void"
        assert s["payout"] == 10.0

    def test_missing_result_stays_pending(self):
        s = settle.settle_slip(slip([leg()]), {}, NOW)
        assert s["status"] == "pending"
        assert s["payout"] is None
        assert s["settled_at"] is None

    def test_accumulator_all_won(self):
        legs = [leg(odds=2.0, match_id="fd-1"),
                leg(odds=3.0, match_id="fd-2", selection="away")]
        results = {"fd-1": result(1, 0, match_id="fd-1"),
                   "fd-2": result(0, 2, match_id="fd-2")}
        s = settle.settle_slip(slip(legs, stake=5.0), results, NOW)
        assert s["status"] == "won"
        assert s["payout"] == 30.0  # 5 * 2.0 * 3.0

    def test_accumulator_one_lost_loses_all(self):
        legs = [leg(odds=2.0, match_id="fd-1"),
                leg(odds=3.0, match_id="fd-2")]
        results = {"fd-1": result(1, 0, match_id="fd-1"),
                   "fd-2": result(0, 2, match_id="fd-2")}  # home leg loses
        s = settle.settle_slip(slip(legs, stake=5.0), results, NOW)
        assert s["status"] == "lost"
        assert s["payout"] == 0.0

    def test_accumulator_void_leg_reduces_to_remaining_odds(self):
        legs = [leg(odds=2.0, match_id="fd-1"),
                leg(odds=3.0, match_id="fd-2")]
        results = {"fd-1": result(1, 0, match_id="fd-1"),
                   "fd-2": result(None, None, "POSTPONED", match_id="fd-2")}
        s = settle.settle_slip(slip(legs, stake=5.0), results, NOW)
        assert s["status"] == "won"
        assert s["payout"] == 10.0  # 5 * 2.0 * 1.0

    def test_accumulator_partial_results_stays_pending(self):
        legs = [leg(odds=2.0, match_id="fd-1"),
                leg(odds=3.0, match_id="fd-2")]
        results = {"fd-1": result(1, 0, match_id="fd-1")}
        s = settle.settle_slip(slip(legs, stake=5.0), results, NOW)
        assert s["status"] == "pending"

    def test_already_settled_slip_untouched(self):
        s = slip([leg()])
        s.update(status="won", payout=20.0, settled_at="2026-06-11T22:00:00Z")
        out = settle.settle_slip(s, {"fd-1": result(0, 5)}, NOW)
        assert out["status"] == "won"
        assert out["settled_at"] == "2026-06-11T22:00:00Z"


# --- rebuild_ledger ---------------------------------------------------------

class TestRebuildLedger:
    def test_bankroll_and_stats(self):
        day1 = {"date": "2026-06-11", "slips": [
            dict(slip([leg(odds=2.0)], stake=10.0, slip_id="2026-06-11-S1"),
                 status="won", payout=20.0, settled_at=NOW),
            dict(slip([leg(odds=3.0)], stake=10.0, slip_id="2026-06-11-S2"),
                 status="lost", payout=0.0, settled_at=NOW),
        ]}
        day2 = {"date": "2026-06-12", "slips": [
            slip([leg(odds=2.0)], stake=5.0, slip_id="2026-06-12-S1"),  # pending
        ]}
        ledger = settle.rebuild_ledger([day1, day2], now=NOW)

        # 1000 - 10 - 10 - 5 staked, +20 returned
        assert ledger["starting_bankroll"] == 1000.0
        assert ledger["bankroll"] == 995.0
        assert ledger["stats"]["total_staked"] == 25.0
        assert ledger["stats"]["total_returned"] == 20.0
        # profit/ROI are settled-only: 20 returned on 20 settled stakes.
        # Pending exposure shows up in bankroll, not P/L.
        assert ledger["stats"]["profit"] == 0.0
        assert ledger["stats"]["slips_won"] == 1
        assert ledger["stats"]["slips_lost"] == 1
        assert ledger["stats"]["slips_pending"] == 1
        assert ledger["stats"]["hit_rate"] == 0.5  # of settled non-void slips
        assert [h["date"] for h in ledger["history"]] == ["2026-06-11", "2026-06-12"]
        assert ledger["history"][0]["bankroll"] == 1000.0  # -20 staked +20 returned
        assert ledger["history"][1]["bankroll"] == 995.0

    def test_roi_is_profit_over_settled_stakes(self):
        day = {"date": "2026-06-11", "slips": [
            dict(slip([leg(odds=3.0)], stake=10.0), status="won", payout=30.0,
                 settled_at=NOW),
        ]}
        ledger = settle.rebuild_ledger([day], now=NOW)
        assert ledger["stats"]["roi"] == pytest.approx(2.0)  # +20 on 10 staked

    def test_by_market_breakdown(self):
        day = {"date": "2026-06-11", "slips": [
            dict(slip([leg(market="btts", selection="yes", odds=2.0)], stake=10.0),
                 status="won", payout=20.0, settled_at=NOW),
        ]}
        ledger = settle.rebuild_ledger([day], now=NOW)
        assert ledger["stats"]["by_market"]["btts"]["won"] == 1
        assert ledger["stats"]["by_market"]["btts"]["staked"] == 10.0

    def test_empty_ledger(self):
        ledger = settle.rebuild_ledger([], now=NOW)
        assert ledger["bankroll"] == 1000.0
        assert ledger["stats"]["hit_rate"] == 0.0


# --- end-to-end main --------------------------------------------------------

class TestMain:
    def test_settles_files_and_writes_ledger(self, tmp_path):
        data = tmp_path
        (data / "betslips").mkdir(parents=True)
        (data / "results").mkdir(parents=True)
        (data / "betslips" / "2026-06-11.json").write_text(json.dumps(
            {"date": "2026-06-11", "slips": [slip([leg(odds=2.0)])]}))
        (data / "results" / "2026-06-11.json").write_text(json.dumps(
            {"date": "2026-06-11", "matches": [result(2, 0)]}))

        settle.run(data_dir=data, now=NOW)

        slips = json.loads((data / "betslips" / "2026-06-11.json").read_text())
        assert slips["slips"][0]["status"] == "won"
        assert slips["slips"][0]["payout"] == 20.0

        ledger = json.loads((data / "ledger.json").read_text())
        assert ledger["bankroll"] == 1010.0
