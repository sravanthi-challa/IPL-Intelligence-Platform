import os
import psycopg2
import sys

def migrate():
    conn = psycopg2.connect(
        host="localhost",
        database="cricket_intelligence",
        user="postgres",
        password=os.environ.get("DB_PASSWORD", "")
    )
    conn.autocommit = False
    cur = conn.cursor()
    
    try:
        print("Applying schema enhancements...")
        
        # 1. Update fact_matches with result_type and player_of_match
        cur.execute("""
            ALTER TABLE fact_matches ADD COLUMN IF NOT EXISTS result_type VARCHAR(50);
            ALTER TABLE fact_matches ADD COLUMN IF NOT EXISTS player_of_match VARCHAR(100);
        """)
        
        # 2. Update dim_players
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_dim_players_name ON dim_players(player_name);
            CREATE INDEX IF NOT EXISTS idx_dim_players_cricsheet ON dim_players(cricsheet_player_id);
        """)
        
        # 3. Update fact_deliveries
        cur.execute("""
            ALTER TABLE fact_deliveries ADD COLUMN IF NOT EXISTS batting_team_id INT REFERENCES dim_teams(team_id);
            ALTER TABLE fact_deliveries ADD COLUMN IF NOT EXISTS bowling_team_id INT REFERENCES dim_teams(team_id);
            ALTER TABLE fact_deliveries ADD COLUMN IF NOT EXISTS player_out_id INT REFERENCES dim_players(player_id);
            ALTER TABLE fact_deliveries ADD COLUMN IF NOT EXISTS is_bowler_wicket BOOLEAN DEFAULT FALSE;
            ALTER TABLE fact_deliveries ADD COLUMN IF NOT EXISTS is_legal_ball BOOLEAN DEFAULT TRUE;
            ALTER TABLE fact_deliveries ADD COLUMN IF NOT EXISTS wides SMALLINT DEFAULT 0;
            ALTER TABLE fact_deliveries ADD COLUMN IF NOT EXISTS noballs SMALLINT DEFAULT 0;
            ALTER TABLE fact_deliveries ADD COLUMN IF NOT EXISTS byes SMALLINT DEFAULT 0;
            ALTER TABLE fact_deliveries ADD COLUMN IF NOT EXISTS legbyes SMALLINT DEFAULT 0;
            ALTER TABLE fact_deliveries ADD COLUMN IF NOT EXISTS penalty SMALLINT DEFAULT 0;
        """)
        
        # Drop constraint if exists to avoid collision, then re-add
        cur.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'uq_match_inning_over_ball'
                ) THEN
                    ALTER TABLE fact_deliveries ADD CONSTRAINT uq_match_inning_over_ball UNIQUE (match_id, innings_no, over_no, ball_no);
                END IF;
            END $$;
        """)
        
        # Performance indexes
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_deliveries_match ON fact_deliveries(match_id);
            CREATE INDEX IF NOT EXISTS idx_deliveries_batter ON fact_deliveries(batter_id);
            CREATE INDEX IF NOT EXISTS idx_deliveries_bowler ON fact_deliveries(bowler_id);
            CREATE INDEX IF NOT EXISTS idx_deliveries_match_over ON fact_deliveries(match_id, over_no);
        """)
        
        # 4. Ingestion log table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS ingestion_log (
                run_id SERIAL PRIMARY KEY,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                total_files INT,
                processed_files INT,
                failed_files INT,
                total_deliveries INT,
                status VARCHAR(20),
                error_details TEXT
            );
        """)
        
        conn.commit()
        print("Schema enhancements committed successfully!")
        
    except Exception as e:
        conn.rollback()
        print(f"Migration error: {e}", file=sys.stderr)
        raise
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    migrate()
