import os
import json
from pathlib import Path
import psycopg2

# -----------------------------
# Database Connection
# -----------------------------

conn = psycopg2.connect(
    host="localhost",
    database="cricket_intelligence",
    user="postgres",
    password=os.environ.get("DB_PASSWORD", "")
)

cur = conn.cursor()

# -----------------------------
# Read JSON
# -----------------------------

file_path = Path("data/raw_data/335982.json")

with open(file_path, "r", encoding="utf-8") as f:
    match_data = json.load(f)

info = match_data["info"]

# -----------------------------
# Extract Data
# -----------------------------

match_id = 335982

match_date = info["dates"][0]

season_name = info["season"]

venue_name = info["venue"]

team1 = info["teams"][0]
team2 = info["teams"][1]

toss_winner = info["toss"]["winner"]
toss_decision = info["toss"]["decision"]

winner = info["outcome"]["winner"]

win_margin_runs = info["outcome"]["by"].get("runs")
win_margin_wickets = info["outcome"]["by"].get("wickets")

# -----------------------------
# Lookup IDs
# -----------------------------

cur.execute(
    "SELECT season_id FROM dim_seasons WHERE season_name=%s",
    (season_name,)
)
season_id = cur.fetchone()[0]

cur.execute(
    "SELECT venue_id FROM dim_venues WHERE venue_name=%s",
    (venue_name,)
)
venue_id = cur.fetchone()[0]

cur.execute(
    "SELECT team_id FROM dim_teams WHERE team_name=%s",
    (team1,)
)
team1_id = cur.fetchone()[0]

cur.execute(
    "SELECT team_id FROM dim_teams WHERE team_name=%s",
    (team2,)
)
team2_id = cur.fetchone()[0]

cur.execute(
    "SELECT team_id FROM dim_teams WHERE team_name=%s",
    (toss_winner,)
)
toss_winner_id = cur.fetchone()[0]

cur.execute(
    "SELECT team_id FROM dim_teams WHERE team_name=%s",
    (winner,)
)
winner_team_id = cur.fetchone()[0]

# -----------------------------
# Insert Fact Record
# -----------------------------

cur.execute("""
INSERT INTO fact_matches (
    match_id,
    match_date,
    season_id,
    venue_id,
    team1_id,
    team2_id,
    toss_winner_id,
    winner_team_id,
    toss_decision,
    win_margin_runs,
    win_margin_wickets
)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
""",
(
    match_id,
    match_date,
    season_id,
    venue_id,
    team1_id,
    team2_id,
    toss_winner_id,
    winner_team_id,
    toss_decision,
    win_margin_runs,
    win_margin_wickets
))

conn.commit()

print("Fact match loaded successfully!")

cur.close()
conn.close()