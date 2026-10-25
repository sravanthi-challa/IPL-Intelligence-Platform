import pytest
import psycopg2
import os

DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "database": os.environ.get("DB_NAME", "cricket_intelligence"),
    "user": os.environ.get("DB_USER", "postgres"),
    "password": os.environ.get("DB_PASSWORD", ""),
    "port": int(os.environ.get("DB_PORT", 5432)),
}

@pytest.fixture(scope="module")
def db_conn():
    conn = psycopg2.connect(**DB_CONFIG)
    yield conn
    conn.close()

def test_database_row_counts(db_conn):
    cur = db_conn.cursor()
    cur.execute("SELECT COUNT(*) FROM fact_matches;")
    assert cur.fetchone()[0] == 1241, "Must have exactly 1,241 matches"
    
    cur.execute("SELECT COUNT(*) FROM dim_players;")
    assert cur.fetchone()[0] >= 900, "Must have at least 900 distinct players"
    
    cur.execute("SELECT COUNT(*) FROM fact_deliveries;")
    count = cur.fetchone()[0]
    assert count > 290000, f"Expected > 290,000 deliveries, got {count}"
    cur.close()

def test_no_orphaned_deliveries(db_conn):
    cur = db_conn.cursor()
    cur.execute("""
        SELECT COUNT(*)
        FROM fact_deliveries d
        LEFT JOIN fact_matches m ON d.match_id = m.match_id
        WHERE m.match_id IS NULL;
    """)
    assert cur.fetchone()[0] == 0, "No delivery should be without a corresponding match"
    cur.close()

def test_bowler_wickets_integrity(db_conn):
    cur = db_conn.cursor()
    cur.execute("""
        SELECT COUNT(*)
        FROM fact_deliveries
        WHERE is_bowler_wicket = TRUE
          AND dismissal_type IN ('run out', 'retired hurt', 'retired out', 'obstructing the field');
    """)
    assert cur.fetchone()[0] == 0, "Non-bowler dismissals must NEVER be flagged as bowler wickets"
    cur.close()

def test_deliveries_mathematical_consistency(db_conn):
    cur = db_conn.cursor()
    cur.execute("""
        SELECT COUNT(*)
        FROM fact_deliveries
        WHERE runs_total != (runs_batter + runs_extras);
    """)
    assert cur.fetchone()[0] == 0, "runs_total must equal runs_batter + runs_extras for every ball"
    cur.close()
