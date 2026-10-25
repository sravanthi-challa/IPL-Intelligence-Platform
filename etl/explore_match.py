import json
from pathlib import Path

file_path = Path("data/raw_data/335982.json")

with open(file_path, "r", encoding="utf-8") as f:
    match_data = json.load(f)

info = match_data["info"]

print("Season:", info.get("season"))
print("Venue:", info.get("venue"))
print("City:", info.get("city"))
print("Teams:", info.get("teams"))
print("Toss:", info.get("toss"))
print("Outcome:", info.get("outcome"))

print(info["dates"])