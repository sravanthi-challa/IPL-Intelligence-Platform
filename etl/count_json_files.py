from pathlib import Path

# Find the project root directory.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Location of the raw JSON files.
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw_data"

# Find every JSON file in the directory.
json_files = list(RAW_DATA_DIR.glob("*.json"))

print("Project root:", PROJECT_ROOT)
print("Raw data directory:", RAW_DATA_DIR)
print("Total JSON files found:", len(json_files))

print("\nFirst 10 files:")

for file_path in sorted(json_files)[:10]:
    print(file_path.name)