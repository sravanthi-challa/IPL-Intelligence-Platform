import os
import psycopg2
import json
from pathlib import Path

def check_postgres_and_sample_json():
    # 1. Check pgvector extension in PostgreSQL
    try:
        conn = psycopg2.connect(
            host="localhost",
            database="cricket_intelligence",
            user="postgres",
            password=os.environ.get("DB_PASSWORD", "")
        )
        cur = conn.cursor()
        cur.execute("SELECT name, default_version, installed_version, comment FROM pg_available_extensions WHERE name = 'vector';")
        res = cur.fetchall()
        print("pgvector in pg_available_extensions:")
        if res:
            for r in res:
                print(" ", r)
        else:
            print("  pgvector is NOT in pg_available_extensions.")
            
        cur.close()
        conn.close()
    except Exception as e:
        print("Postgres check error:", e)

    # 2. Inspect sample JSON files from 2008 and recent (e.g. 2023/2024)
    raw_dir = Path(r"C:\Users\sravanthi\Documents\cricket-intelligence-platform\data\raw_data")
    sample_files = ["335982.json"] # The very first IPL match (2008)
    
    # Also find the latest json file
    all_json = sorted(raw_dir.glob("*.json"))
    if all_json:
        sample_files.append(all_json[-1].name)
        
    for sf in sample_files:
        p = raw_dir / sf
        if not p.exists():
            continue
        print(f"\n================ Sample JSON: {sf} ================")
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        info = data.get("info", {})
        print("Info keys:", list(info.keys()))
        print("Season:", info.get("season"))
        print("Event:", info.get("event"))
        print("Match type:", info.get("match_type"))
        print("Teams:", info.get("teams"))
        print("Outcome:", info.get("outcome"))
        if "registry" in info and "people" in info["registry"]:
            people_sample = list(info["registry"]["people"].items())[:5]
            print("Registry people sample (name -> id):", people_sample)
        if "players" in info:
            print("Players teams:", list(info["players"].keys()))
            for t, plist in info["players"].items():
                print(f"  {t} ({len(plist)} players): {plist[:3]}...")
                
        innings = data.get("innings", [])
        print(f"Total innings: {len(innings)}")
        for idx, inn in enumerate(innings):
            team = inn.get("team")
            overs = inn.get("overs", [])
            print(f"  Innings {idx+1}: Team '{team}', {len(overs)} overs")
            if overs:
                first_over = overs[0]
                print(f"    Over {first_over.get('over')} has {len(first_over.get('deliveries', []))} deliveries")
                if first_over.get("deliveries"):
                    print("    Sample delivery:", first_over["deliveries"][0])
            
            # Find a delivery with a wicket or extras
            sample_wicket = None
            sample_extra = None
            for ov in overs:
                for deliv in ov.get("deliveries", []):
                    if "wickets" in deliv and not sample_wicket:
                        sample_wicket = deliv
                    if "extras" in deliv and not sample_extra:
                        sample_extra = deliv
            if sample_wicket:
                print("    Sample wicket delivery:", sample_wicket)
            if sample_extra:
                print("    Sample extras delivery:", sample_extra)

if __name__ == "__main__":
    check_postgres_and_sample_json()
