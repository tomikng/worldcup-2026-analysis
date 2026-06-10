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


# --- new markets (goal-derived) ----------------------------------------------

def stats_result(home_goals=2, away_goals=1, match_id="fd-1", **stats):
    r = result(home_goals, away_goals, match_id=match_id)
    r.update({"home_cards": None, "away_cards": None, "home_reds": None,
              "away_reds": None, "home_corners": None, "away_corners": None})
    r.update(stats)
    return r


class TestGradeLegDoubleChance:
    def test_1x_wins_on_home_win(self):
        l = leg(market="double_chance", selection="1x")
        assert settle.grade_leg(l, result(2, 0)) == "won"

    def test_1x_wins_on_draw(self):
        l = leg(market="double_chance", selection="1x")
        assert settle.grade_leg(l, result(1, 1)) == "won"

    def test_1x_loses_on_away_win(self):
        l = leg(market="double_chance", selection="1x")
        assert settle.grade_leg(l, result(0, 1)) == "lost"

    def test_12_loses_on_draw(self):
        l = leg(market="double_chance", selection="12")
        assert settle.grade_leg(l, result(0, 0)) == "lost"

    def test_x2_wins_on_away_win(self):
        l = leg(market="double_chance", selection="x2")
        assert settle.grade_leg(l, result(0, 3)) == "won"


class TestGradeLegDNB:
    def test_home_wins(self):
        assert settle.grade_leg(leg(market="dnb", selection="home"), result(1, 0)) == "won"

    def test_draw_is_void(self):
        assert settle.grade_leg(leg(market="dnb", selection="home"), result(1, 1)) == "void"

    def test_home_loses_on_away_win(self):
        assert settle.grade_leg(leg(market="dnb", selection="home"), result(0, 2)) == "lost"


class TestGradeLegTeamTotals:
    def test_home_over_wins(self):
        l = leg(market="team_totals", selection="over", line=1.5)
        l["side"] = "home"
        assert settle.grade_leg(l, result(2, 0)) == "won"

    def test_away_under_wins(self):
        l = leg(market="team_totals", selection="under", line=1.5)
        l["side"] = "away"
        assert settle.grade_leg(l, result(3, 1)) == "won"

    def test_exact_whole_line_void(self):
        l = leg(market="team_totals", selection="over", line=2.0)
        l["side"] = "home"
        assert settle.grade_leg(l, result(2, 1)) == "void"


class TestGradeLegCorrectScore:
    def test_exact_score_wins(self):
        l = leg(market="correct_score", selection="2-1")
        assert settle.grade_leg(l, result(2, 1)) == "won"

    def test_reversed_score_loses(self):
        l = leg(market="correct_score", selection="2-1")
        assert settle.grade_leg(l, result(1, 2)) == "lost"


# --- new markets (stat-dependent, void on missing stats) ---------------------

class TestGradeLegCards:
    def test_over_wins(self):
        l = leg(market="cards", selection="over", line=4.5)
        assert settle.grade_leg(l, stats_result(home_cards=3, away_cards=2)) == "won"

    def test_under_wins(self):
        l = leg(market="cards", selection="under", line=4.5)
        assert settle.grade_leg(l, stats_result(home_cards=1, away_cards=2)) == "won"

    def test_missing_stats_void(self):
        l = leg(market="cards", selection="over", line=4.5)
        assert settle.grade_leg(l, stats_result()) == "void"

    def test_missing_stats_in_plain_result_void(self):
        # results written before the stats fields existed have no keys at all
        l = leg(market="cards", selection="over", line=4.5)
        assert settle.grade_leg(l, result(2, 1)) == "void"


class TestGradeLegRedCard:
    def test_yes_wins_when_red_shown(self):
        l = leg(market="red_card", selection="yes")
        assert settle.grade_leg(l, stats_result(home_reds=1, away_reds=0)) == "won"

    def test_no_wins_when_clean(self):
        l = leg(market="red_card", selection="no")
        assert settle.grade_leg(l, stats_result(home_reds=0, away_reds=0)) == "won"

    def test_missing_stats_void(self):
        l = leg(market="red_card", selection="yes")
        assert settle.grade_leg(l, stats_result()) == "void"


class TestGradeLegCorners:
    def test_over_wins(self):
        l = leg(market="corners", selection="over", line=9.5)
        assert settle.grade_leg(l, stats_result(home_corners=7, away_corners=4)) == "won"

    def test_missing_stats_void(self):
        l = leg(market="corners", selection="under", line=9.5)
        assert settle.grade_leg(l, stats_result(home_corners=7)) == "void"


# --- futures ledger ----------------------------------------------------------

def position(pid="FUT-1", outcome="Mexico", entry_price=0.25, stake=20.0,
             status="open"):
    return {"position_id": pid, "market_title": "World Cup Winner",
            "outcome": outcome, "entry_price": entry_price, "stake": stake,
            "url": "https://polymarket.com/event/world-cup-winner",
            "opened": "2026-06-11", "status": status, "resolved_at": None}


class TestFuturesLedger:
    def test_futures_section_math(self):
        futures = {"budget": 100.0, "positions": [
            position(status="won"),                       # 20u at 0.25 -> 80u back
            position(pid="FUT-2", stake=10.0, status="lost"),
            position(pid="FUT-3", stake=15.0, status="open"),
        ]}
        ledger = settle.rebuild_ledger([], futures=futures, now=NOW)
        f = ledger["futures"]
        assert f["budget"] == 100.0
        assert f["staked"] == 45.0
        assert f["remaining"] == 55.0
        assert f["returned"] == 80.0
        assert f["profit"] == 50.0  # 80 returned on 30 settled stakes
        assert f["open"] == 1 and f["won"] == 1 and f["lost"] == 1

    def test_no_futures_file_gives_default_section(self):
        ledger = settle.rebuild_ledger([], now=NOW)
        assert ledger["futures"]["staked"] == 0.0
        assert ledger["futures"]["budget"] == 100.0


class TestDynamicByMarket:
    def test_new_market_appears_in_by_market(self):
        day = {"date": "2026-06-11", "slips": [
            dict(slip([leg(market="dnb", selection="home", odds=1.5)], stake=10.0),
                 status="won", payout=15.0, settled_at=NOW)]}
        ledger = settle.rebuild_ledger([day], now=NOW)
        assert ledger["stats"]["by_market"]["dnb"]["won"] == 1
