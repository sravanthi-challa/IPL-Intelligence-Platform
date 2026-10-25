import json
from pathlib import Path

# Change this path to one of your JSON files
file_path = Path(
    r"data/raw_data/335982.json"
)

with open(file_path, "r", encoding="utf-8") as f:
    match_data = json.load(f)

info = match_data["info"]

print("=" * 50)

print("MATCH DETAILS")

print("=" * 50)

print("Venue :", info.get("venue"))

print("City :", info.get("city"))

print("Date :", info["dates"][0])

print("Season :", info.get("season"))

print("Teams :", info["teams"])

print("Toss Winner :", info["toss"]["winner"])

print("Toss Decision :", info["toss"]["decision"])

print("Winner :", info["outcome"].get("winner"))

print("=" * 50)