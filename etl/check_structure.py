
import json
from pathlib import Path

file_path = Path("data/raw_data/335982.json")

with open(file_path, "r", encoding="utf-8") as f:
    match_data = json.load(f)

print(match_data.keys())



#remove first and run second(just for cheking data)


import json
from pathlib import Path

file_path = Path("data/raw_data/335982.json")

with open(file_path, "r", encoding="utf-8") as f:
    match_data = json.load(f)

print("\nINFO KEYS:")
print(match_data["info"].keys())