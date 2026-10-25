import pytest
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "analytics"))

from metrics import CricketAnalytics

def test_matches_per_season():
    seasons = CricketAnalytics.get_matches_per_season()
    assert len(seasons) >= 17, "Should have at least 17 IPL seasons"
    total_matches = sum(s["total_matches"] for s in seasons)
    assert total_matches == 1241, f"Expected 1,241 total matches across seasons, got {total_matches}"

def test_top_run_scorers_all_time():
    top_batters = CricketAnalytics.get_top_run_scorers(limit=5)
    assert len(top_batters) == 5
    top_scorer = top_batters[0]
    # Virat Kohli is the historic top run-scorer in IPL history
    assert "Kohli" in top_scorer["player_name"], f"Expected Virat Kohli as top scorer, got {top_scorer['player_name']}"
    assert top_scorer["total_runs"] > 7000, f"Expected >7000 runs, got {top_scorer['total_runs']}"
    assert top_scorer["strike_rate"] > 100

def test_top_run_scorers_season_2016():
    # 2016 is Virat Kohli's record-breaking 973-run season
    top_2016 = CricketAnalytics.get_top_run_scorers(season="2016", limit=3)
    assert len(top_2016) > 0
    leader = top_2016[0]
    assert "Kohli" in leader["player_name"]
    assert leader["total_runs"] >= 900, f"Expected >= 900 runs in 2016 for Kohli, got {leader['total_runs']}"

def test_top_wicket_takers():
    top_bowlers = CricketAnalytics.get_top_wicket_takers(limit=5)
    assert len(top_bowlers) == 5
    # The top bowler should have over 170 wickets
    assert top_bowlers[0]["wickets"] > 170
    for b in top_bowlers:
        assert b["economy_rate"] > 0
        assert b["wickets"] > 0

def test_head_to_head_csk_vs_mi():
    h2h = CricketAnalytics.get_head_to_head("Chennai Super Kings", "Mumbai Indians")
    assert h2h["total_matches"] >= 35, f"CSK vs MI should have >= 35 matches, got {h2h['total_matches']}"
    assert h2h["team1_wins"] + h2h["team2_wins"] + h2h["ties_or_no_result"] == h2h["total_matches"]
    assert len(h2h["recent_matches"]) > 0

def test_player_batter_profile():
    profile = CricketAnalytics.get_batter_profile("MS Dhoni")
    assert profile is not None
    assert profile["player_name"] == "MS Dhoni"
    assert profile["total_runs"] > 4000
    assert len(profile["seasons"]) > 10
    assert len(profile["phases"]) > 0

def test_death_overs_rankings():
    death_hitters = CricketAnalytics.get_death_overs_rankings(min_balls=100, limit=5)
    assert len(death_hitters) == 5
    for hitter in death_hitters:
        # Death overs strike rates are typically very high
        assert hitter["phase_strike_rate"] > 150

def test_match_details_match_1():
    match = CricketAnalytics.get_match_details(335982)
    assert match is not None
    assert match["match_id"] == 335982
    assert match["winner"] == "Kolkata Knight Riders"
    assert match["win_margin_runs"] == 140
    assert len(match["innings"]) == 2
    # Innings 1 KKR scored 222
    assert match["innings"][0]["total_runs"] == 222
