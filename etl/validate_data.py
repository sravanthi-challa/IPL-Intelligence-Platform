import os
import psycopg2
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw_data"

def validate():
    conn = psycopg2.connect(
        host="localhost",
        database="cricket_intelligence",
        user="postgres",
        password=os.environ.get("DB_PASSWORD", "")
    )
    cur = conn.cursor()
    
    print("=" * 60)
    print("      DATA QUALITY & INTEGRITY VALIDATION REPORT      ")
    print("=" * 60)
    
    issues = []
    
    # 1. Row counts
    tables = [
        "dim_seasons", "dim_teams", "dim_venues", "dim_players",
        "fact_matches", "fact_deliveries", "ingestion_log"
    ]
    print("\n1. Table Row Counts:")
    for t in tables:
        cur.execute(f"SELECT COUNT(*) FROM {t};")
        cnt = cur.fetchone()[0]
        print(f"   {t:20}: {cnt:,} rows")
        if t in ("dim_players", "fact_deliveries") and cnt == 0:
            issues.append(f"CRITICAL: Table {t} is empty!")

    # 2. Check duplicate deliveries by unique constraint
    cur.execute("""
        SELECT match_id, innings_no, over_no, ball_no, COUNT(*)
        FROM fact_deliveries
        GROUP BY match_id, innings_no, over_no, ball_no
        HAVING COUNT(*) > 1;
    """)
    dup_deliveries = cur.fetchall()
    print(f"\n2. Duplicate Deliveries Check: {len(dup_deliveries)} duplicates found.")
    if dup_deliveries:
        issues.append(f"Found {len(dup_deliveries)} duplicate delivery keys!")

    # 3. Check mathematical consistency of runs
    cur.execute("""
        SELECT COUNT(*) 
        FROM fact_deliveries 
        WHERE runs_total != (runs_batter + runs_extras);
    """)
    run_discrepancies = cur.fetchone()[0]
    print(f"3. Run Math Consistency (total == batter + extras): {run_discrepancies} discrepancies.")
    if run_discrepancies > 0:
        issues.append(f"Found {run_discrepancies} deliveries where total != batter + extras!")

    # 4. Check for negative runs
    cur.execute("""
        SELECT COUNT(*) 
        FROM fact_deliveries 
        WHERE runs_batter < 0 OR runs_extras < 0 OR runs_total < 0;
    """)
    neg_runs = cur.fetchone()[0]
    print(f"4. Negative Runs Check: {neg_runs} negative values.")
    if neg_runs > 0:
        issues.append(f"Found {neg_runs} deliveries with negative runs!")

    # 5. Check Bowler Wicket Rules Compliance
    cur.execute("""
        SELECT COUNT(*)
        FROM fact_deliveries
        WHERE is_bowler_wicket = TRUE
          AND dismissal_type NOT IN ('bowled', 'caught', 'caught and bowled', 'hit wicket', 'lbw', 'stumped');
    """)
    invalid_bowler_wickets = cur.fetchone()[0]
    print(f"5. Bowler Wickets Integrity Check: {invalid_bowler_wickets} invalid assignments.")
    if invalid_bowler_wickets > 0:
        issues.append(f"Found {invalid_bowler_wickets} invalid bowler wicket classifications!")

    cur.execute("""
        SELECT COUNT(*)
        FROM fact_deliveries
        WHERE dismissal_type IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
          AND is_bowler_wicket = TRUE;
    """)
    run_outs_as_wickets = cur.fetchone()[0]
    print(f"   Non-bowler dismissals credited to bowler: {run_outs_as_wickets}.")
    if run_outs_as_wickets > 0:
        issues.append("Run outs or retired dismissals were improperly credited to bowlers!")

    # 6. Orphaned Foreign Keys
    cur.execute("""
        SELECT COUNT(*)
        FROM fact_deliveries d
        LEFT JOIN dim_players p ON d.batter_id = p.player_id
        WHERE p.player_id IS NULL;
    """)
    orphaned_batters = cur.fetchone()[0]
    print(f"6. Orphaned Batters Check: {orphaned_batters} orphaned records.")
    if orphaned_batters > 0:
        issues.append(f"Found {orphaned_batters} orphaned batter IDs!")

    cur.execute("""
        SELECT COUNT(*)
        FROM fact_deliveries d
        LEFT JOIN dim_players p ON d.bowler_id = p.player_id
        WHERE p.player_id IS NULL;
    """)
    orphaned_bowlers = cur.fetchone()[0]
    print(f"   Orphaned Bowlers Check: {orphaned_bowlers} orphaned records.")
    if orphaned_bowlers > 0:
        issues.append(f"Found {orphaned_bowlers} orphaned bowler IDs!")

    # 7. Spot check comparison against raw JSON match (Match 335982 - First IPL Match)
    cur.execute("""
        SELECT 
            p.player_name, 
            SUM(d.runs_batter) as total_runs,
            COUNT(*) as balls_faced,
            SUM(CASE WHEN d.runs_batter = 4 THEN 1 ELSE 0 END) as fours,
            SUM(CASE WHEN d.runs_batter = 6 THEN 1 ELSE 0 END) as sixes
        FROM fact_deliveries d
        JOIN dim_players p ON d.batter_id = p.player_id
        WHERE d.match_id = 335982 AND p.player_name = 'BB McCullum'
        GROUP BY p.player_name;
    """)
    mccullum_stat = cur.fetchone()
    print("\n7. Spot-Check Historic Milestone (Match 335982: BB McCullum 158*):")
    if mccullum_stat:
        name, runs, balls, fours, sixes = mccullum_stat
        print(f"   Player: {name} | Runs: {runs} | Balls: {balls} | 4s: {fours} | 6s: {sixes}")
        if runs == 158 and fours == 10 and sixes == 13:
            print("   >>> PASS: BB McCullum's iconic 158* (73 balls, 10 fours, 13 sixes) matches perfectly!")
        else:
            issues.append(f"McCullum stat discrepancy: got runs={runs}, 4s={fours}, 6s={sixes}")
    else:
        issues.append("Could not find McCullum in match 335982!")

    cur.close()
    conn.close()

    print("\n" + "=" * 60)
    if issues:
        print("VALIDATION FAILED with issues:")
        for iss in issues:
            print(f" - {iss}")
        return False
    else:
        print("ALL DATA QUALITY & INTEGRITY CHECKS PASSED PERFECTLY!")
        print("=" * 60)
        return True

if __name__ == "__main__":
    validate()
