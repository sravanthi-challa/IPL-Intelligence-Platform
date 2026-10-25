import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any
import psycopg2
from psycopg2.extras import RealDictCursor

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "database"))
sys.path.insert(0, str(PROJECT_ROOT / "utils"))

try:
    from connection import get_db_cursor
except ImportError:
    DB_CONFIG = {
        "host": os.environ.get("DB_HOST", "localhost"),
        "database": os.environ.get("DB_NAME", "cricket_intelligence"),
        "user": os.environ.get("DB_USER", "postgres"),
        "password": os.environ.get("DB_PASSWORD", ""),
        "port": int(os.environ.get("DB_PORT", 5432)),
    }
    def get_db_cursor():
        conn = psycopg2.connect(**DB_CONFIG)
        return conn, conn.cursor(cursor_factory=RealDictCursor)

class CricketAnalytics:
    """
    Production-grade analytical query layer executing parameterized,
    evidence-grounded SQL calculations against IPL database.
    """

    # ----------------------------------------------------
    # MATCHES & SEASONS
    # ----------------------------------------------------
    @staticmethod
    def get_matches_per_season() -> List[Dict[str, Any]]:
        conn, cur = get_db_cursor()
        try:
            cur.execute("""
                SELECT 
                    s.season_name,
                    COUNT(m.match_id) AS total_matches,
                    MIN(m.match_date) AS season_start,
                    MAX(m.match_date) AS season_end
                FROM dim_seasons s
                JOIN fact_matches m ON s.season_id = m.season_id
                GROUP BY s.season_name
                ORDER BY s.season_name;
            """)
            return [dict(r) for r in cur.fetchall()]
        finally:
            cur.close()
            conn.close()

    @staticmethod
    def get_match_details(match_id: int) -> Optional[Dict[str, Any]]:
        conn, cur = get_db_cursor()
        try:
            cur.execute("""
                SELECT 
                    m.match_id,
                    m.match_date,
                    s.season_name,
                    v.venue_name,
                    v.city,
                    t1.team_name AS team1,
                    t2.team_name AS team2,
                    tw.team_name AS toss_winner,
                    m.toss_decision,
                    w.team_name AS winner,
                    m.win_margin_runs,
                    m.win_margin_wickets,
                    m.result_type,
                    m.player_of_match
                FROM fact_matches m
                JOIN dim_seasons s ON m.season_id = s.season_id
                JOIN dim_venues v ON m.venue_id = v.venue_id
                JOIN dim_teams t1 ON m.team1_id = t1.team_id
                JOIN dim_teams t2 ON m.team2_id = t2.team_id
                LEFT JOIN dim_teams tw ON m.toss_winner_id = tw.team_id
                LEFT JOIN dim_teams w ON m.winner_team_id = w.team_id
                WHERE m.match_id = %s;
            """, (match_id,))
            match_row = cur.fetchone()
            if not match_row:
                return None

            # Get innings scores
            cur.execute("""
                SELECT 
                    d.innings_no,
                    t.team_name AS batting_team,
                    SUM(d.runs_total) AS total_runs,
                    COUNT(CASE WHEN d.is_wicket THEN 1 END) AS wickets_lost,
                    MAX(d.over_no) + 1 AS overs_played
                FROM fact_deliveries d
                JOIN dim_teams t ON d.batting_team_id = t.team_id
                WHERE d.match_id = %s
                GROUP BY d.innings_no, t.team_name
                ORDER BY d.innings_no;
            """, (match_id,))
            innings = [dict(r) for r in cur.fetchall()]
            
            result = dict(match_row)
            result["innings"] = innings
            return result
        finally:
            cur.close()
            conn.close()

    # ----------------------------------------------------
    # BATTING ANALYTICS
    # ----------------------------------------------------
    @staticmethod
    def get_top_run_scorers(season: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
        conn, cur = get_db_cursor()
        try:
            if season:
                cur.execute("""
                    WITH season_matches AS (
                        SELECT match_id FROM fact_matches m
                        JOIN dim_seasons s ON m.season_id = s.season_id
                        WHERE s.season_name = %s
                    )
                    SELECT 
                        p.player_name,
                        COUNT(DISTINCT d.match_id) AS matches_batted,
                        SUM(d.runs_batter) AS total_runs,
                        COUNT(CASE WHEN d.wides = 0 THEN 1 END) AS balls_faced,
                        ROUND((SUM(d.runs_batter) * 100.0) / NULLIF(COUNT(CASE WHEN d.wides = 0 THEN 1 END), 0), 2) AS strike_rate,
                        COUNT(CASE WHEN d.runs_batter = 4 THEN 1 END) AS fours,
                        COUNT(CASE WHEN d.runs_batter = 6 THEN 1 END) AS sixes
                    FROM fact_deliveries d
                    JOIN season_matches sm ON d.match_id = sm.match_id
                    JOIN dim_players p ON d.batter_id = p.player_id
                    GROUP BY p.player_name
                    ORDER BY total_runs DESC
                    LIMIT %s;
                """, (str(season), limit))
            else:
                cur.execute("""
                    SELECT 
                        player_name,
                        matches_batted,
                        total_runs,
                        balls_faced,
                        strike_rate,
                        dismissals,
                        batting_average,
                        fours,
                        sixes,
                        highest_score,
                        fifties,
                        hundreds
                    FROM v_batter_summary
                    ORDER BY total_runs DESC
                    LIMIT %s;
                """, (limit,))
            return [dict(r) for r in cur.fetchall()]
        finally:
            cur.close()
            conn.close()

    @staticmethod
    def get_batter_profile(player_name: str) -> Optional[Dict[str, Any]]:
        conn, cur = get_db_cursor()
        try:
            # Overall summary
            cur.execute("""
                SELECT * FROM v_batter_summary 
                WHERE LOWER(player_name) = LOWER(%s)
                LIMIT 1;
            """, (player_name.strip(),))
            overall = cur.fetchone()
            if not overall:
                return None

            # Season by season performance
            cur.execute("""
                SELECT 
                    s.season_name,
                    COUNT(DISTINCT d.match_id) AS matches,
                    SUM(d.runs_batter) AS runs,
                    COUNT(CASE WHEN d.wides = 0 THEN 1 END) AS balls,
                    ROUND((SUM(d.runs_batter) * 100.0) / NULLIF(COUNT(CASE WHEN d.wides = 0 THEN 1 END), 0), 2) AS strike_rate,
                    COUNT(CASE WHEN d.runs_batter = 4 THEN 1 END) AS fours,
                    COUNT(CASE WHEN d.runs_batter = 6 THEN 1 END) AS sixes
                FROM fact_deliveries d
                JOIN fact_matches m ON d.match_id = m.match_id
                JOIN dim_seasons s ON m.season_id = s.season_id
                JOIN dim_players p ON d.batter_id = p.player_id
                WHERE LOWER(p.player_name) = LOWER(%s)
                GROUP BY s.season_name
                ORDER BY s.season_name;
            """, (player_name.strip(),))
            seasons = [dict(r) for r in cur.fetchall()]

            # Phase breakdown
            cur.execute("""
                SELECT match_phase, phase_runs, phase_balls, phase_strike_rate, phase_fours, phase_sixes
                FROM v_match_phase_batting
                WHERE LOWER(player_name) = LOWER(%s)
                ORDER BY match_phase;
            """, (player_name.strip(),))
            phases = [dict(r) for r in cur.fetchall()]

            res = dict(overall)
            res["seasons"] = seasons
            res["phases"] = phases
            return res
        finally:
            cur.close()
            conn.close()

    # ----------------------------------------------------
    # BOWLING ANALYTICS
    # ----------------------------------------------------
    @staticmethod
    def get_top_wicket_takers(season: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
        conn, cur = get_db_cursor()
        try:
            if season:
                cur.execute("""
                    WITH season_matches AS (
                        SELECT match_id FROM fact_matches m
                        JOIN dim_seasons s ON m.season_id = s.season_id
                        WHERE s.season_name = %s
                    )
                    SELECT 
                        p.player_name,
                        COUNT(DISTINCT d.match_id) AS matches_bowled,
                        ROUND(COUNT(CASE WHEN d.is_legal_ball THEN 1 END) / 6.0, 1) AS overs,
                        SUM(d.runs_batter + d.wides + d.noballs) AS runs_conceded,
                        COUNT(CASE WHEN d.is_bowler_wicket THEN 1 END) AS wickets,
                        ROUND((SUM(d.runs_batter + d.wides + d.noballs) * 6.0) / NULLIF(COUNT(CASE WHEN d.is_legal_ball THEN 1 END), 0), 2) AS economy
                    FROM fact_deliveries d
                    JOIN season_matches sm ON d.match_id = sm.match_id
                    JOIN dim_players p ON d.bowler_id = p.player_id
                    GROUP BY p.player_name
                    ORDER BY wickets DESC, economy ASC
                    LIMIT %s;
                """, (str(season), limit))
            else:
                cur.execute("""
                    SELECT 
                        player_name,
                        matches_bowled,
                        overs_bowled,
                        runs_conceded,
                        wickets,
                        economy_rate,
                        bowling_average,
                        bowling_strike_rate,
                        best_wickets_in_match
                    FROM v_bowler_summary
                    ORDER BY wickets DESC, economy_rate ASC
                    LIMIT %s;
                """, (limit,))
            return [dict(r) for r in cur.fetchall()]
        finally:
            cur.close()
            conn.close()

    @staticmethod
    def get_bowler_profile(player_name: str) -> Optional[Dict[str, Any]]:
        conn, cur = get_db_cursor()
        try:
            cur.execute("""
                SELECT * FROM v_bowler_summary
                WHERE LOWER(player_name) = LOWER(%s)
                LIMIT 1;
            """, (player_name.strip(),))
            overall = cur.fetchone()
            if not overall:
                return None

            cur.execute("""
                SELECT 
                    s.season_name,
                    COUNT(DISTINCT d.match_id) AS matches,
                    ROUND(COUNT(CASE WHEN d.is_legal_ball THEN 1 END) / 6.0, 1) AS overs,
                    SUM(d.runs_batter + d.wides + d.noballs) AS runs_conceded,
                    COUNT(CASE WHEN d.is_bowler_wicket THEN 1 END) AS wickets,
                    ROUND((SUM(d.runs_batter + d.wides + d.noballs) * 6.0) / NULLIF(COUNT(CASE WHEN d.is_legal_ball THEN 1 END), 0), 2) AS economy
                FROM fact_deliveries d
                JOIN fact_matches m ON d.match_id = m.match_id
                JOIN dim_seasons s ON m.season_id = s.season_id
                JOIN dim_players p ON d.bowler_id = p.player_id
                WHERE LOWER(p.player_name) = LOWER(%s)
                GROUP BY s.season_name
                ORDER BY s.season_name;
            """, (player_name.strip(),))
            seasons = [dict(r) for r in cur.fetchall()]

            cur.execute("""
                SELECT match_phase, phase_legal_balls, phase_runs_conceded, phase_wickets, phase_economy
                FROM v_match_phase_bowling
                WHERE LOWER(player_name) = LOWER(%s)
                ORDER BY match_phase;
            """, (player_name.strip(),))
            phases = [dict(r) for r in cur.fetchall()]

            res = dict(overall)
            res["seasons"] = seasons
            res["phases"] = phases
            return res
        finally:
            cur.close()
            conn.close()

    # ----------------------------------------------------
    # HEAD-TO-HEAD & TEAM PERFORMANCE
    # ----------------------------------------------------
    @staticmethod
    def get_head_to_head(team1: str, team2: str) -> Dict[str, Any]:
        conn, cur = get_db_cursor()
        try:
            cur.execute("""
                SELECT 
                    COUNT(*) AS total_matches,
                    COUNT(CASE WHEN w.team_name ILIKE %s THEN 1 END) AS team1_wins,
                    COUNT(CASE WHEN w.team_name ILIKE %s THEN 1 END) AS team2_wins,
                    COUNT(CASE WHEN m.winner_team_id IS NULL THEN 1 END) AS ties_or_no_result
                FROM fact_matches m
                JOIN dim_teams t1 ON m.team1_id = t1.team_id
                JOIN dim_teams t2 ON m.team2_id = t2.team_id
                LEFT JOIN dim_teams w ON m.winner_team_id = w.team_id
                WHERE (t1.team_name ILIKE %s AND t2.team_name ILIKE %s)
                   OR (t1.team_name ILIKE %s AND t2.team_name ILIKE %s);
            """, (f"%{team1}%", f"%{team2}%", f"%{team1}%", f"%{team2}%", f"%{team2}%", f"%{team1}%"))
            summary = cur.fetchone()
            
            # Fetch recent matches
            cur.execute("""
                SELECT 
                    m.match_id,
                    m.match_date,
                    s.season_name,
                    v.venue_name,
                    w.team_name AS winner,
                    m.win_margin_runs,
                    m.win_margin_wickets,
                    m.player_of_match
                FROM fact_matches m
                JOIN dim_seasons s ON m.season_id = s.season_id
                JOIN dim_venues v ON m.venue_id = v.venue_id
                JOIN dim_teams t1 ON m.team1_id = t1.team_id
                JOIN dim_teams t2 ON m.team2_id = t2.team_id
                LEFT JOIN dim_teams w ON m.winner_team_id = w.team_id
                WHERE (t1.team_name ILIKE %s AND t2.team_name ILIKE %s)
                   OR (t1.team_name ILIKE %s AND t2.team_name ILIKE %s)
                ORDER BY m.match_date DESC
                LIMIT 10;
            """, (f"%{team1}%", f"%{team2}%", f"%{team2}%", f"%{team1}%"))
            matches = [dict(r) for r in cur.fetchall()]

            res = dict(summary)
            res["team1"] = team1
            res["team2"] = team2
            res["recent_matches"] = matches
            return res
        finally:
            cur.close()
            conn.close()

    @staticmethod
    def get_player_vs_opponent(player_name: str, opponent_team: str) -> Optional[Dict[str, Any]]:
        conn, cur = get_db_cursor()
        try:
            # Batting vs Opponent
            cur.execute("""
                SELECT 
                    p.player_name,
                    opp.team_name AS opponent,
                    COUNT(DISTINCT d.match_id) AS matches_batted,
                    SUM(d.runs_batter) AS total_runs,
                    COUNT(CASE WHEN d.wides = 0 THEN 1 END) AS balls_faced,
                    ROUND((SUM(d.runs_batter) * 100.0) / NULLIF(COUNT(CASE WHEN d.wides = 0 THEN 1 END), 0), 2) AS strike_rate,
                    COUNT(CASE WHEN d.runs_batter = 4 THEN 1 END) AS fours,
                    COUNT(CASE WHEN d.runs_batter = 6 THEN 1 END) AS sixes,
                    MAX(d.runs_batter) AS max_boundary
                FROM fact_deliveries d
                JOIN dim_players p ON d.batter_id = p.player_id
                JOIN dim_teams opp ON d.bowling_team_id = opp.team_id
                WHERE LOWER(p.player_name) = LOWER(%s)
                  AND opp.team_name ILIKE %s
                GROUP BY p.player_name, opp.team_name;
            """, (player_name.strip(), f"%{opponent_team}%"))
            batting_res = cur.fetchone()

            # Bowling vs Opponent
            cur.execute("""
                SELECT 
                    p.player_name,
                    opp.team_name AS opponent,
                    COUNT(DISTINCT d.match_id) AS matches_bowled,
                    ROUND(COUNT(CASE WHEN d.is_legal_ball THEN 1 END) / 6.0, 1) AS overs,
                    SUM(d.runs_batter + d.wides + d.noballs) AS runs_conceded,
                    COUNT(CASE WHEN d.is_bowler_wicket THEN 1 END) AS wickets,
                    ROUND((SUM(d.runs_batter + d.wides + d.noballs) * 6.0) / NULLIF(COUNT(CASE WHEN d.is_legal_ball THEN 1 END), 0), 2) AS economy
                FROM fact_deliveries d
                JOIN dim_players p ON d.bowler_id = p.player_id
                JOIN dim_teams opp ON d.batting_team_id = opp.team_id
                WHERE LOWER(p.player_name) = LOWER(%s)
                  AND opp.team_name ILIKE %s
                GROUP BY p.player_name, opp.team_name;
            """, (player_name.strip(), f"%{opponent_team}%"))
            bowling_res = cur.fetchone()

            if not batting_res and not bowling_res:
                return None

            return {
                "player_name": player_name,
                "opponent": opponent_team,
                "batting": dict(batting_res) if batting_res else None,
                "bowling": dict(bowling_res) if bowling_res else None,
            }
        finally:
            cur.close()
            conn.close()

    # ----------------------------------------------------
    # VENUE & PHASE ANALYTICS
    # ----------------------------------------------------
    @staticmethod
    def get_venue_statistics(limit: int = 10) -> List[Dict[str, Any]]:
        conn, cur = get_db_cursor()
        try:
            cur.execute("""
                SELECT 
                    v.venue_name,
                    v.city,
                    COUNT(m.match_id) AS matches_played,
                    COUNT(CASE WHEN m.toss_decision = 'field' THEN 1 END) AS toss_field_count,
                    COUNT(CASE WHEN m.toss_decision = 'bat' THEN 1 END) AS toss_bat_count,
                    COUNT(CASE WHEN m.winner_team_id = m.toss_winner_id THEN 1 END) AS toss_and_match_wins
                FROM dim_venues v
                JOIN fact_matches m ON v.venue_id = m.venue_id
                GROUP BY v.venue_name, v.city
                ORDER BY matches_played DESC
                LIMIT %s;
            """, (limit,))
            return [dict(r) for r in cur.fetchall()]
        finally:
            cur.close()
            conn.close()

    @staticmethod
    def get_death_overs_rankings(min_balls: int = 60, limit: int = 10) -> List[Dict[str, Any]]:
        conn, cur = get_db_cursor()
        try:
            cur.execute("""
                SELECT 
                    player_name,
                    phase_runs,
                    phase_balls,
                    phase_strike_rate,
                    phase_fours,
                    phase_sixes
                FROM v_match_phase_batting
                WHERE match_phase = 'Death (15-19)'
                  AND phase_balls >= %s
                ORDER BY phase_strike_rate DESC
                LIMIT %s;
            """, (min_balls, limit))
            return [dict(r) for r in cur.fetchall()]
        finally:
            cur.close()
            conn.close()
