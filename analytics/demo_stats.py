import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "analytics"))
from metrics import CricketAnalytics

def show():
    print("=== TOP 5 ALL-TIME RUN SCORERS ===")
    for idx, b in enumerate(CricketAnalytics.get_top_run_scorers(limit=5), 1):
        print(f"{idx}. {b['player_name']:<18} | Runs: {b['total_runs']} | SR: {b['strike_rate']} | Avg: {b['batting_average']} | 100s: {b['hundreds']} | 50s: {b['fifties']}")

    print("\n=== TOP 5 ALL-TIME WICKET TAKERS ===")
    for idx, b in enumerate(CricketAnalytics.get_top_wicket_takers(limit=5), 1):
        print(f"{idx}. {b['player_name']:<18} | Wkts: {b['wickets']} | Overs: {b['overs_bowled']} | Econ: {b['economy_rate']} | Avg: {b['bowling_average']}")

    print("\n=== CSK vs MI HEAD TO HEAD ===")
    h2h = CricketAnalytics.get_head_to_head("Chennai Super Kings", "Mumbai Indians")
    print(f"Total Matches: {h2h['total_matches']} | CSK Wins: {h2h['team1_wins']} | MI Wins: {h2h['team2_wins']} | Ties/NR: {h2h['ties_or_no_result']}")

    print("\n=== TOP DEATH-OVER HITTERS (Min 100 balls) ===")
    for idx, b in enumerate(CricketAnalytics.get_death_overs_rankings(min_balls=100, limit=5), 1):
        print(f"{idx}. {b['player_name']:<18} | Runs: {b['phase_runs']} | Balls: {b['phase_balls']} | Death SR: {b['phase_strike_rate']}")

if __name__ == "__main__":
    show()
