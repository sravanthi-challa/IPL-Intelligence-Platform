import pytest
from pathlib import Path
import sys

# Ensure etl is in pythonpath
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "etl"))

from extract_matches import parse_match_json, BOWLER_WICKET_KINDS, NON_BOWLER_WICKET_KINDS

RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw_data"

def test_extract_match_json():
    first_match = RAW_DATA_DIR / "335982.json"
    assert first_match.exists(), "Sample match file 335982.json must exist"
    
    parsed = parse_match_json(first_match)
    match = parsed["match"]
    assert match["match_id"] == 335982
    assert match["season"] == "2007/08"
    assert "Kolkata Knight Riders" in match["teams"]
    assert "Royal Challengers Bangalore" in match["teams"]
    assert match["winner"] == "Kolkata Knight Riders"
    assert match["win_margin_runs"] == 140

def test_players_registry_extracted():
    first_match = RAW_DATA_DIR / "335982.json"
    parsed = parse_match_json(first_match)
    players = parsed["players"]
    assert "BB McCullum" in players
    assert "SC Ganguly" in players
    assert "V Kohli" in players
    # Verify cricsheet ID captured
    assert players["BB McCullum"] is not None

def test_deliveries_and_cricket_rules():
    first_match = RAW_DATA_DIR / "335982.json"
    parsed = parse_match_json(first_match)
    deliveries = parsed["deliveries"]
    assert len(deliveries) > 0
    
    # Check total runs by BB McCullum
    mccullum_runs = sum(d["runs_batter"] for d in deliveries if d["batter"] == "BB McCullum")
    assert mccullum_runs == 158, f"Expected 158 runs for McCullum, got {mccullum_runs}"

    # Check bowler wickets vs non-bowler wickets
    for d in deliveries:
        if d["is_wicket"]:
            kind = d["dismissal_type"]
            if kind in BOWLER_WICKET_KINDS:
                assert d["is_bowler_wicket"] is True
            elif kind in NON_BOWLER_WICKET_KINDS:
                assert d["is_bowler_wicket"] is False

def test_runs_mathematical_consistency():
    first_match = RAW_DATA_DIR / "335982.json"
    parsed = parse_match_json(first_match)
    for d in parsed["deliveries"]:
        assert d["runs_total"] == d["runs_batter"] + d["runs_extras"]
        assert d["runs_batter"] >= 0
        assert d["runs_extras"] >= 0
