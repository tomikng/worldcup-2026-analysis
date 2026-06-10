import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import fdorg


class TestMatchdayWindow:
    def test_evening_utc_kickoff_belongs_to_previous_local_matchday(self):
        # 02:00 UTC Jun 12 = evening of Jun 11 in North America
        assert fdorg.in_matchday_window("2026-06-12T02:00:00Z", "2026-06-11")

    def test_afternoon_kickoff_belongs_to_same_day(self):
        assert fdorg.in_matchday_window("2026-06-11T19:00:00Z", "2026-06-11")

    def test_early_morning_kickoff_belongs_to_previous_matchday(self):
        assert not fdorg.in_matchday_window("2026-06-11T03:00:00Z", "2026-06-11")

    def test_next_day_afternoon_excluded(self):
        assert not fdorg.in_matchday_window("2026-06-12T18:00:00Z", "2026-06-11")

    def test_window_starts_at_0600_utc(self):
        assert fdorg.in_matchday_window("2026-06-11T06:00:00Z", "2026-06-11")
        assert not fdorg.in_matchday_window("2026-06-12T05:59:00Z", "2026-06-12")
