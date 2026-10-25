import json
import os
from typing import List, Dict, Any, Optional
import psycopg2
from psycopg2.extras import RealDictCursor

DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "database": os.environ.get("DB_NAME", "cricket_intelligence"),
    "user": os.environ.get("DB_USER", "postgres"),
    "password": os.environ.get("DB_PASSWORD", ""),
    "port": int(os.environ.get("DB_PORT", 5432)),
}

def get_db():
    conn = psycopg2.connect(**DB_CONFIG)
    return conn, conn.cursor(cursor_factory=RealDictCursor)

class DocumentBuilder:
    """
    Builds factual, evidence-grounded documents from the PostgreSQL database
    for RAG semantic retrieval and LLM context assembly.
    """

    @staticmethod
    def build_match_document(match_id: int) -> Optional[Dict[str, Any]]:
        conn, cur = get_db()
        try:
            # 1. Fetch match metadata
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
            m = cur.fetchone()
            if not m:
                return None

            # 2. Fetch innings summaries
            cur.execute("""
                SELECT 
                    d.innings_no,
                    t.team_name AS batting_team,
                    SUM(d.runs_total) AS total_runs,
                    COUNT(CASE WHEN d.is_wicket THEN 1 END) AS wickets,
                    MAX(d.over_no) + 1 AS overs_played
                FROM fact_deliveries d
                JOIN dim_teams t ON d.batting_team_id = t.team_id
                WHERE d.match_id = %s
                GROUP BY d.innings_no, t.team_name
                ORDER BY d.innings_no;
            """, (match_id,))
            innings_list = cur.fetchall()

            # 3. Top performers in this match
            cur.execute("""
                SELECT 
                    p.player_name,
                    t.team_name,
                    SUM(d.runs_batter) AS runs,
                    COUNT(CASE WHEN d.wides = 0 THEN 1 END) AS balls,
                    COUNT(CASE WHEN d.runs_batter = 4 THEN 1 END) AS fours,
                    COUNT(CASE WHEN d.runs_batter = 6 THEN 1 END) AS sixes
                FROM fact_deliveries d
                JOIN dim_players p ON d.batter_id = p.player_id
                JOIN dim_teams t ON d.batting_team_id = t.team_id
                WHERE d.match_id = %s
                GROUP BY p.player_name, t.team_name
                ORDER BY runs DESC
                LIMIT 3;
            """, (match_id,))
            top_batters = cur.fetchall()

            cur.execute("""
                SELECT 
                    p.player_name,
                    COUNT(CASE WHEN d.is_bowler_wicket THEN 1 END) AS wickets,
                    SUM(d.runs_batter + d.wides + d.noballs) AS runs_conceded,
                    ROUND(COUNT(CASE WHEN d.is_legal_ball THEN 1 END) / 6.0, 1) AS overs
                FROM fact_deliveries d
                JOIN dim_players p ON d.bowler_id = p.player_id
                WHERE d.match_id = %s
                GROUP BY p.player_name
                HAVING COUNT(CASE WHEN d.is_bowler_wicket THEN 1 END) > 0
                ORDER BY wickets DESC, runs_conceded ASC
                LIMIT 3;
            """, (match_id,))
            top_bowlers = cur.fetchall()

            # Format match narrative
            city_str = f", {m['city']}" if m.get('city') else ""
            toss_str = f"{m['toss_winner']} won the toss and decided to {m['toss_decision']}." if m.get('toss_winner') else "Toss information not recorded."
            
            if m.get('winner'):
                if m.get('win_margin_runs'):
                    margin_str = f"won by {m['win_margin_runs']} runs"
                elif m.get('win_margin_wickets'):
                    margin_str = f"won by {m['win_margin_wickets']} wickets"
                else:
                    margin_str = "won the match"
                result_str = f"{m['winner']} {margin_str}."
            elif m.get('result_type') == 'tie':
                result_str = "Match ended in a tie (Super Over)."
            else:
                result_str = "Match ended with no result."

            pom_str = f" Player of the Match was {m['player_of_match']}." if m.get('player_of_match') else ""

            innings_text = []
            for inn in innings_list:
                innings_text.append(f"Innings {inn['innings_no']} ({inn['batting_team']}): {inn['total_runs']}/{inn['wickets']} in {inn['overs_played']} overs.")

            bat_perf = [f"{b['player_name']} ({b['runs']} runs off {b['balls']} balls, {b['fours']}x4, {b['sixes']}x6)" for b in top_batters]
            bowl_perf = [f"{b['player_name']} ({b['wickets']} wickets for {b['runs_conceded']} runs in {b['overs']} ov)" for b in top_bowlers]

            body = (
                f"Match ID: {m['match_id']} | Season: {m['season_name']} | Date: {m['match_date']}\n"
                f"Venue: {m['venue_name']}{city_str}\n"
                f"Teams: {m['team1']} vs {m['team2']}\n"
                f"Toss: {toss_str}\n"
                f"Result: {result_str}{pom_str}\n\n"
                f"Scorecard Progression:\n" + "\n".join(innings_text) + "\n\n"
                f"Key Batting Performances: {', '.join(bat_perf) if bat_perf else 'None'}\n"
                f"Key Bowling Performances: {', '.join(bowl_perf) if bowl_perf else 'None'}"
            )

            title = f"Match {m['match_id']}: {m['team1']} vs {m['team2']} ({m['season_name']})"
            doc_id = f"match_{m['match_id']}"
            
            metadata = {
                "doc_type": "match",
                "match_id": m["match_id"],
                "season": m["season_name"],
                "teams": [m["team1"], m["team2"]],
                "venue": m["venue_name"],
                "winner": m["winner"],
                "player_of_match": m["player_of_match"],
                "date": str(m["match_date"]),
            }

            return {
                "doc_id": doc_id,
                "doc_type": "match",
                "title": title,
                "content": body,
                "metadata": metadata,
            }
        finally:
            cur.close()
            conn.close()

    @staticmethod
    def build_player_document(player_name: str) -> Optional[Dict[str, Any]]:
        conn, cur = get_db()
        try:
            last_name = player_name.strip().split()[-1]
            # Batting profile
            cur.execute("""
                SELECT * FROM v_batter_summary 
                WHERE LOWER(player_name) = LOWER(%s)
                   OR player_name ILIKE %s
                ORDER BY total_runs DESC
                LIMIT 1;
            """, (player_name.strip(), f"%{last_name}%"))
            bat = cur.fetchone()

            # Bowling profile
            cur.execute("""
                SELECT * FROM v_bowler_summary 
                WHERE LOWER(player_name) = LOWER(%s)
                   OR player_name ILIKE %s
                ORDER BY wickets DESC
                LIMIT 1;
            """, (player_name.strip(), f"%{last_name}%"))
            bowl = cur.fetchone()

            if not bat and not bowl:
                return None

            name = bat["player_name"] if bat else bowl["player_name"]
            player_id = bat["player_id"] if bat else bowl["player_id"]

            sections = [f"Player Profile: {name} (Player ID: {player_id})"]
            
            if bat and bat["total_runs"] > 0:
                sections.append(
                    f"IPL Batting Career:\n"
                    f"- Matches Batted: {bat['matches_batted']}\n"
                    f"- Total Runs: {bat['total_runs']}\n"
                    f"- Balls Faced: {bat['balls_faced']}\n"
                    f"- Strike Rate: {bat['strike_rate']}\n"
                    f"- Batting Average: {bat['batting_average']}\n"
                    f"- Boundaries: {bat['fours']} fours, {bat['sixes']} sixes\n"
                    f"- Highest Score: {bat['highest_score']}\n"
                    f"- Milestones: {bat['hundreds']} centuries, {bat['fifties']} half-centuries"
                )

            if bowl and bowl["wickets"] > 0:
                sections.append(
                    f"IPL Bowling Career:\n"
                    f"- Matches Bowled: {bowl['matches_bowled']}\n"
                    f"- Overs Bowled: {bowl['overs_bowled']} ({bowl['legal_balls_bowled']} legal deliveries)\n"
                    f"- Wickets Taken: {bowl['wickets']}\n"
                    f"- Runs Conceded: {bowl['runs_conceded']}\n"
                    f"- Economy Rate: {bowl['economy_rate']}\n"
                    f"- Bowling Average: {bowl['bowling_average']}\n"
                    f"- Bowling Strike Rate: {bowl['bowling_strike_rate']} balls/wicket\n"
                    f"- Best Match Haul: {bowl['best_wickets_in_match']} wickets"
                )

            # Get phase splits
            cur.execute("""
                SELECT match_phase, phase_runs, phase_balls, phase_strike_rate
                FROM v_match_phase_batting
                WHERE player_id = %s
                ORDER BY match_phase;
            """, (player_id,))
            bat_phases = cur.fetchall()
            if bat_phases:
                p_text = [f"  * {bp['match_phase']}: {bp['phase_runs']} runs off {bp['phase_balls']} balls (SR: {bp['phase_strike_rate']})" for bp in bat_phases]
                sections.append("Batting Phase Analysis:\n" + "\n".join(p_text))

            content = "\n\n".join(sections)
            doc_id = f"player_{player_id}"
            
            metadata = {
                "doc_type": "player",
                "player_id": player_id,
                "player_name": name,
                "total_runs": int(bat["total_runs"]) if bat else 0,
                "total_wickets": int(bowl["wickets"]) if bowl else 0,
            }

            return {
                "doc_id": doc_id,
                "doc_type": "player",
                "title": f"Player Profile: {name}",
                "content": content,
                "metadata": metadata,
            }
        finally:
            cur.close()
            conn.close()

    @staticmethod
    def build_data_dictionary_documents() -> List[Dict[str, Any]]:
        """
        Creates semantic cricket data dictionary and terminology documents.
        """
        glossary = [
            {
                "doc_id": "dict_batting_metrics",
                "doc_type": "glossary",
                "title": "Cricket Glossary: Batting Statistics Definitions",
                "content": (
                    "Batting Metric Definitions in IPL Intelligence:\n\n"
                    "1. Batting Strike Rate: Calculated as (Total Batter Runs * 100.0) / Balls Faced. "
                    "Note: In official cricket rules, wides do NOT count as balls faced, but no-balls DO count as balls faced.\n\n"
                    "2. Batting Average: Calculated as Total Batter Runs / Total Dismissals. "
                    "Instances where a batter remains not out or retires hurt are not counted as dismissals.\n\n"
                    "3. Boundary Percentage: Proportion of total runs scored from fours and sixes ((4*fours + 6*sixes)*100.0 / total_runs).\n\n"
                    "4. Innings vs Matches: A player may participate in a match as a fielder or lower-order player without batting; "
                    "thus 'matches played' may exceed 'innings batted'."
                ),
                "metadata": {"doc_type": "glossary", "category": "batting"}
            },
            {
                "doc_id": "dict_bowling_metrics",
                "doc_type": "glossary",
                "title": "Cricket Glossary: Bowling Statistics & Wicket Rules",
                "content": (
                    "Bowling Metric Definitions & Cricket Laws in IPL Intelligence:\n\n"
                    "1. Bowler Wickets: Only dismissals caused by the bowler are credited as bowler wickets: "
                    "bowled, caught, caught and bowled, lbw, stumped, and hit wicket. "
                    "Run outs, retired hurt, retired out, and obstructing the field are NOT credited to the bowler.\n\n"
                    "2. Bowling Economy Rate: Calculated as (Runs Conceded * 6.0) / Legal Deliveries Bowled. "
                    "Runs conceded includes batter runs, wides, and no-balls. "
                    "Byes, leg-byes, and penalty runs are fielding extras and are NOT charged against the bowler.\n\n"
                    "3. Bowling Strike Rate: The average number of legal balls bowled per wicket taken (Legal Balls / Wickets). Lower is better.\n\n"
                    "4. Bowling Average: The average number of runs conceded per wicket taken (Runs Conceded / Wickets). Lower is better."
                ),
                "metadata": {"doc_type": "glossary", "category": "bowling"}
            },
            {
                "doc_id": "dict_match_phases",
                "doc_type": "glossary",
                "title": "Cricket Glossary: Match Phases in T20 Cricket",
                "content": (
                    "T20 Match Phases Definitions in IPL Intelligence:\n\n"
                    "1. Powerplay (Overs 0 to 5 / First 6 Overs): Fielding restrictions apply where only two fielders are allowed outside "
                    "the 30-yard circle. High run rates and attacking batting are common.\n\n"
                    "2. Middle Overs (Overs 6 to 14 / Overs 7 to 15): Spinners and medium pacers control the game. Up to 5 fielders allowed "
                    "on the boundary. Focus is on strike rotation and wicket conservation.\n\n"
                    "3. Death Overs / Slog Overs (Overs 15 to 19 / Last 5 Overs): Batters aggressively hit boundaries; bowlers utilize yorkers, "
                    "slower balls, and wide lines. High scoring rates and frequent wickets."
                ),
                "metadata": {"doc_type": "glossary", "category": "phases"}
            },
            {
                "doc_id": "dict_tie_super_over",
                "doc_type": "glossary",
                "title": "Cricket Glossary: Ties, Super Overs, and No Results",
                "content": (
                    "IPL Match Result Classifications:\n\n"
                    "1. Normal Result: A match completed with a clear winner by runs (when batting first defends) or by wickets (when chasing team wins).\n\n"
                    "2. Tie / Super Over / Eliminator: When both teams score the exact same number of runs in their completed innings, "
                    "the match is tied and resolved by a Super Over (one over per side). The winner of the Super Over is awarded the match.\n\n"
                    "3. No Result: Matches abandoned due to rain, weather, or unplayable conditions without completing the minimum required overs (5 overs per side)."
                ),
                "metadata": {"doc_type": "glossary", "category": "rules"}
            }
        ]
        return glossary
