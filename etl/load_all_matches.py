import os
import sys
import time
from pathlib import Path
from typing import Dict, Optional, Tuple, Set, List
import psycopg2
from psycopg2.extras import execute_batch

from extract_matches import parse_match_json

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw_data"

DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "database": os.environ.get("DB_NAME", "cricket_intelligence"),
    "user": os.environ.get("DB_USER", "postgres"),
    "password": os.environ.get("DB_PASSWORD", ""),
    "port": int(os.environ.get("DB_PORT", 5432)),
}

def get_connection():
    return psycopg2.connect(**DB_CONFIG)

class DimensionCache:
    def __init__(self, conn):
        self.conn = conn
        self.seasons: Dict[str, int] = {}
        self.teams: Dict[str, int] = {}
        self.venues: Dict[Tuple[str, Optional[str]], int] = {}
        # player_name -> player_id, and cricsheet_id -> player_id
        self.players_by_cricsheet: Dict[str, int] = {}
        self.players_by_name: Dict[str, int] = {}
        self._preload()

    def _preload(self):
        with self.conn.cursor() as cur:
            # Seasons
            cur.execute("SELECT season_id, season_name FROM dim_seasons;")
            for s_id, s_name in cur.fetchall():
                self.seasons[s_name] = s_id
                
            # Teams
            cur.execute("SELECT team_id, team_name FROM dim_teams;")
            for t_id, t_name in cur.fetchall():
                self.teams[t_name] = t_id
                
            # Venues
            cur.execute("SELECT venue_id, venue_name, city FROM dim_venues;")
            for v_id, v_name, v_city in cur.fetchall():
                self.venues[(v_name, v_city)] = v_id
                # fallback for matching by venue_name alone if city is null
                self.venues[(v_name, None)] = v_id

            # Players
            cur.execute("SELECT player_id, cricsheet_player_id, player_name FROM dim_players;")
            for p_id, c_id, p_name in cur.fetchall():
                if c_id:
                    self.players_by_cricsheet[c_id] = p_id
                self.players_by_name[p_name] = p_id

    def get_season_id(self, cur, season_name: str) -> int:
        season_name = str(season_name)
        if season_name in self.seasons:
            return self.seasons[season_name]
        cur.execute("""
            INSERT INTO dim_seasons (season_name)
            VALUES (%s)
            ON CONFLICT (season_name) DO UPDATE SET season_name = EXCLUDED.season_name
            RETURNING season_id;
        """, (season_name,))
        s_id = cur.fetchone()[0]
        self.seasons[season_name] = s_id
        return s_id

    def get_team_id(self, cur, team_name: Optional[str]) -> Optional[int]:
        if not team_name:
            return None
        if team_name in self.teams:
            return self.teams[team_name]
        cur.execute("""
            INSERT INTO dim_teams (team_name)
            VALUES (%s)
            ON CONFLICT (team_name) DO UPDATE SET team_name = EXCLUDED.team_name
            RETURNING team_id;
        """, (team_name,))
        t_id = cur.fetchone()[0]
        self.teams[team_name] = t_id
        return t_id

    def get_venue_id(self, cur, venue_name: str, city: Optional[str]) -> int:
        key = (venue_name, city)
        if key in self.venues:
            return self.venues[key]
        if (venue_name, None) in self.venues:
            return self.venues[(venue_name, None)]
            
        cur.execute("""
            SELECT venue_id FROM dim_venues 
            WHERE venue_name = %s AND city IS NOT DISTINCT FROM %s
            LIMIT 1;
        """, (venue_name, city))
        row = cur.fetchone()
        if row:
            v_id = row[0]
        else:
            cur.execute("""
                INSERT INTO dim_venues (venue_name, city)
                VALUES (%s, %s)
                RETURNING venue_id;
            """, (venue_name, city))
            v_id = cur.fetchone()[0]
            
        self.venues[key] = v_id
        self.venues[(venue_name, None)] = v_id
        return v_id

    def register_players(self, cur, players_dict: Dict[str, Optional[str]]):
        """
        Registers all players from the match registry in bulk.
        players_dict: {player_name: cricsheet_id}
        """
        to_insert = []
        for name, c_id in players_dict.items():
            if c_id and c_id in self.players_by_cricsheet:
                continue
            if name in self.players_by_name:
                continue
            to_insert.append((c_id, name))
            
        if to_insert:
            execute_batch(cur, """
                INSERT INTO dim_players (cricsheet_player_id, player_name)
                VALUES (%s, %s)
                ON CONFLICT (cricsheet_player_id) DO NOTHING;
            """, to_insert, page_size=500)
            
            # Fetch newly assigned IDs
            cur.execute("""
                SELECT player_id, cricsheet_player_id, player_name 
                FROM dim_players 
                WHERE player_name = ANY(%s) OR (cricsheet_player_id IS NOT NULL AND cricsheet_player_id = ANY(%s));
            """, ([x[1] for x in to_insert], [x[0] for x in to_insert if x[0]]))
            for p_id, c_id, p_name in cur.fetchall():
                if c_id:
                    self.players_by_cricsheet[c_id] = p_id
                self.players_by_name[p_name] = p_id

    def get_player_id(self, cur, player_name: Optional[str]) -> Optional[int]:
        if not player_name:
            return None
        if player_name in self.players_by_name:
            return self.players_by_name[player_name]
        # Insert ad-hoc if not present
        cur.execute("""
            INSERT INTO dim_players (cricsheet_player_id, player_name)
            VALUES (NULL, %s)
            RETURNING player_id;
        """, (player_name,))
        p_id = cur.fetchone()[0]
        self.players_by_name[player_name] = p_id
        return p_id


def load_all_matches():
    start_time = time.time()
    json_files = sorted(RAW_DATA_DIR.glob("*.json"))
    total_files = len(json_files)
    if not total_files:
        print(f"No JSON files found in {RAW_DATA_DIR}")
        return

    print(f"Starting ingestion for {total_files} match files...")
    conn = get_connection()
    conn.autocommit = False

    # Start ingestion run log
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO ingestion_log (total_files, processed_files, failed_files, status)
            VALUES (%s, 0, 0, 'RUNNING')
            RETURNING run_id;
        """, (total_files,))
        run_id = cur.fetchone()[0]
    conn.commit()

    dim_cache = DimensionCache(conn)
    processed_count = 0
    failed_matches: List[Tuple[str, str]] = []
    total_deliveries_inserted = 0

    delivery_insert_sql = """
        INSERT INTO fact_deliveries (
            match_id, innings_no, over_no, ball_no,
            batter_id, bowler_id, non_striker_id,
            runs_batter, runs_extras, runs_total,
            is_wicket, dismissal_type, extra_type, extra_runs,
            batting_team_id, bowling_team_id, player_out_id,
            is_bowler_wicket, is_legal_ball,
            wides, noballs, byes, legbyes, penalty
        )
        VALUES (
            %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s,
            %s, %s, %s, %s, %s
        )
        ON CONFLICT (match_id, innings_no, over_no, ball_no) DO NOTHING;
    """

    match_upsert_sql = """
        INSERT INTO fact_matches (
            match_id, match_date, season_id, venue_id,
            team1_id, team2_id, toss_winner_id, toss_decision,
            winner_team_id, win_margin_runs, win_margin_wickets,
            result_type, player_of_match
        )
        VALUES (
            %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s
        )
        ON CONFLICT (match_id) DO UPDATE SET
            result_type = EXCLUDED.result_type,
            player_of_match = EXCLUDED.player_of_match,
            winner_team_id = EXCLUDED.winner_team_id,
            win_margin_runs = EXCLUDED.win_margin_runs,
            win_margin_wickets = EXCLUDED.win_margin_wickets;
    """

    delivery_buffer = []
    BUFFER_SIZE = 5000

    try:
        cur = conn.cursor()
        for idx, file_path in enumerate(json_files, start=1):
            try:
                parsed = parse_match_json(file_path)
                m = parsed["match"]
                
                # 1. Resolve dimensions
                season_id = dim_cache.get_season_id(cur, m["season"])
                venue_id = dim_cache.get_venue_id(cur, m["venue"], m["city"])
                
                teams = m["teams"]
                t1_id = dim_cache.get_team_id(cur, teams[0]) if len(teams) > 0 else None
                t2_id = dim_cache.get_team_id(cur, teams[1]) if len(teams) > 1 else None
                toss_winner_id = dim_cache.get_team_id(cur, m["toss_winner"])
                winner_team_id = dim_cache.get_team_id(cur, m["winner"])
                
                # 2. Register all players in this match
                dim_cache.register_players(cur, parsed["players"])
                
                # 3. Upsert fact_matches
                cur.execute(match_upsert_sql, (
                    m["match_id"], m["match_date"], season_id, venue_id,
                    t1_id, t2_id, toss_winner_id, m["toss_decision"],
                    winner_team_id, m["win_margin_runs"], m["win_margin_wickets"],
                    m["result_type"], m["player_of_match"]
                ))

                # 4. Prepare delivery rows
                for d in parsed["deliveries"]:
                    batter_id = dim_cache.get_player_id(cur, d["batter"])
                    bowler_id = dim_cache.get_player_id(cur, d["bowler"])
                    non_striker_id = dim_cache.get_player_id(cur, d["non_striker"])
                    player_out_id = dim_cache.get_player_id(cur, d["player_out"]) if d["player_out"] else None
                    batting_team_id = dim_cache.get_team_id(cur, d["batting_team"])
                    bowling_team_id = dim_cache.get_team_id(cur, d["bowling_team"])

                    delivery_buffer.append((
                        d["match_id"], d["innings_no"], d["over_no"], d["ball_no"],
                        batter_id, bowler_id, non_striker_id,
                        d["runs_batter"], d["runs_extras"], d["runs_total"],
                        d["is_wicket"], d["dismissal_type"], d["extra_type"], d["extra_runs"],
                        batting_team_id, bowling_team_id, player_out_id,
                        d["is_bowler_wicket"], d["is_legal_ball"],
                        d["wides"], d["noballs"], d["byes"], d["legbyes"], d["penalty"]
                    ))

                if len(delivery_buffer) >= BUFFER_SIZE:
                    execute_batch(cur, delivery_insert_sql, delivery_buffer, page_size=2000)
                    total_deliveries_inserted += len(delivery_buffer)
                    delivery_buffer.clear()
                    conn.commit()

                processed_count += 1
                if processed_count % 100 == 0 or processed_count == total_files:
                    conn.commit()
                    elapsed = time.time() - start_time
                    print(f"[{processed_count}/{total_files}] matches processed. Inserted ~{total_deliveries_inserted + len(delivery_buffer):,} deliveries ({elapsed:.1f}s)")

            except Exception as e:
                conn.rollback()
                failed_matches.append((file_path.name, str(e)))
                print(f"FAILED on {file_path.name}: {e}")

        # Flush remaining buffer
        if delivery_buffer:
            execute_batch(cur, delivery_insert_sql, delivery_buffer, page_size=2000)
            total_deliveries_inserted += len(delivery_buffer)
            delivery_buffer.clear()
            conn.commit()

        # Update log
        status = "COMPLETED" if len(failed_matches) == 0 else "COMPLETED_WITH_ERRORS"
        cur.execute("""
            UPDATE ingestion_log
            SET completed_at = CURRENT_TIMESTAMP,
                processed_files = %s,
                failed_files = %s,
                total_deliveries = %s,
                status = %s,
                error_details = %s
            WHERE run_id = %s;
        """, (
            processed_count,
            len(failed_matches),
            total_deliveries_inserted,
            status,
            "\n".join([f"{f}: {err}" for f, err in failed_matches[:20]]) if failed_matches else None,
            run_id
        ))
        conn.commit()
        cur.close()

    finally:
        conn.close()

    total_time = time.time() - start_time
    print("\n================= ETL SUMMARY =================")
    print(f"Total files discovered : {total_files}")
    print(f"Successfully processed : {processed_count}")
    print(f"Failed files           : {len(failed_matches)}")
    print(f"Total deliveries loaded: {total_deliveries_inserted:,}")
    print(f"Execution time         : {total_time:.2f} seconds")
    print("===============================================")


if __name__ == "__main__":
    load_all_matches()