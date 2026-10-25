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
# Season
# -----------------------------

season = info["season"]

cur.execute("""
    INSERT INTO dim_seasons (season_name)
    VALUES (%s)
    ON CONFLICT (season_name)
    DO NOTHING
""", (season,))

# -----------------------------
# Venue
# -----------------------------

venue = info["venue"]
city = info.get("city")

cur.execute("""
    INSERT INTO dim_venues (venue_name, city)
    VALUES (%s, %s)
""", (venue, city))

# -----------------------------
# Teams
# -----------------------------

for team in info["teams"]:
    cur.execute("""
        INSERT INTO dim_teams (team_name)
        VALUES (%s)
        ON CONFLICT (team_name)
        DO NOTHING
    """, (team,))

conn.commit()

print("Dimensions loaded successfully!")

cur.close()
conn.close()