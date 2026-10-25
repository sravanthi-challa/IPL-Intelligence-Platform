-- ====================================================================
-- IPL INTELLIGENCE: Analytical Database Views
-- ====================================================================

-- 1. BATTER OVERALL SUMMARY VIEW
CREATE OR REPLACE VIEW v_batter_summary AS
WITH batter_innings AS (
    SELECT 
        d.match_id,
        d.batter_id,
        SUM(d.runs_batter) AS innings_runs,
        COUNT(CASE WHEN d.wides = 0 THEN 1 END) AS innings_balls,
        COUNT(CASE WHEN d.runs_batter = 4 THEN 1 END) AS innings_fours,
        COUNT(CASE WHEN d.runs_batter = 6 THEN 1 END) AS innings_sixes
    FROM fact_deliveries d
    GROUP BY d.match_id, d.batter_id
),
batter_dismissals AS (
    SELECT 
        player_out_id AS player_id,
        COUNT(*) AS total_outs
    FROM fact_deliveries
    WHERE is_wicket = TRUE 
      AND player_out_id IS NOT NULL 
      AND dismissal_type NOT IN ('retired hurt')
    GROUP BY player_out_id
)
SELECT 
    p.player_id,
    p.player_name,
    COUNT(DISTINCT bi.match_id) AS matches_batted,
    SUM(bi.innings_runs) AS total_runs,
    SUM(bi.innings_balls) AS balls_faced,
    ROUND((SUM(bi.innings_runs) * 100.0) / NULLIF(SUM(bi.innings_balls), 0), 2) AS strike_rate,
    COALESCE(bd.total_outs, 0) AS dismissals,
    ROUND(SUM(bi.innings_runs) * 1.0 / NULLIF(COALESCE(bd.total_outs, 0), 0), 2) AS batting_average,
    SUM(bi.innings_fours) AS fours,
    SUM(bi.innings_sixes) AS sixes,
    MAX(bi.innings_runs) AS highest_score,
    COUNT(CASE WHEN bi.innings_runs >= 50 AND bi.innings_runs < 100 THEN 1 END) AS fifties,
    COUNT(CASE WHEN bi.innings_runs >= 100 THEN 1 END) AS hundreds
FROM dim_players p
JOIN batter_innings bi ON p.player_id = bi.batter_id
LEFT JOIN batter_dismissals bd ON p.player_id = bd.player_id
GROUP BY p.player_id, p.player_name, bd.total_outs;


-- 2. BOWLER OVERALL SUMMARY VIEW
CREATE OR REPLACE VIEW v_bowler_summary AS
WITH bowler_matches AS (
    SELECT 
        d.match_id,
        d.bowler_id,
        COUNT(CASE WHEN d.is_legal_ball THEN 1 END) AS match_legal_balls,
        SUM(d.runs_batter + d.wides + d.noballs) AS match_runs_conceded,
        COUNT(CASE WHEN d.is_bowler_wicket THEN 1 END) AS match_wickets
    FROM fact_deliveries d
    GROUP BY d.match_id, d.bowler_id
)
SELECT 
    p.player_id,
    p.player_name,
    COUNT(DISTINCT bm.match_id) AS matches_bowled,
    SUM(bm.match_legal_balls) AS legal_balls_bowled,
    ROUND(SUM(bm.match_legal_balls) / 6.0, 1) AS overs_bowled,
    SUM(bm.match_runs_conceded) AS runs_conceded,
    SUM(bm.match_wickets) AS wickets,
    ROUND((SUM(bm.match_runs_conceded) * 6.0) / NULLIF(SUM(bm.match_legal_balls), 0), 2) AS economy_rate,
    ROUND(SUM(bm.match_runs_conceded) * 1.0 / NULLIF(SUM(bm.match_wickets), 0), 2) AS bowling_average,
    ROUND(SUM(bm.match_legal_balls) * 1.0 / NULLIF(SUM(bm.match_wickets), 0), 2) AS bowling_strike_rate,
    MAX(bm.match_wickets) AS best_wickets_in_match
FROM dim_players p
JOIN bowler_matches bm ON p.player_id = bm.bowler_id
GROUP BY p.player_id, p.player_name;


-- 3. MATCH PHASE DEFINITIONS & BATTING METRICS
-- Powerplay: overs 0 to 5
-- Middle: overs 6 to 14
-- Death: overs 15 to 19
CREATE OR REPLACE VIEW v_match_phase_batting AS
SELECT 
    p.player_id,
    p.player_name,
    CASE 
        WHEN d.over_no BETWEEN 0 AND 5 THEN 'Powerplay (0-5)'
        WHEN d.over_no BETWEEN 6 AND 14 THEN 'Middle (6-14)'
        ELSE 'Death (15-19)'
    END AS match_phase,
    SUM(d.runs_batter) AS phase_runs,
    COUNT(CASE WHEN d.wides = 0 THEN 1 END) AS phase_balls,
    ROUND((SUM(d.runs_batter) * 100.0) / NULLIF(COUNT(CASE WHEN d.wides = 0 THEN 1 END), 0), 2) AS phase_strike_rate,
    COUNT(CASE WHEN d.runs_batter = 4 THEN 1 END) AS phase_fours,
    COUNT(CASE WHEN d.runs_batter = 6 THEN 1 END) AS phase_sixes
FROM fact_deliveries d
JOIN dim_players p ON d.batter_id = p.player_id
GROUP BY p.player_id, p.player_name, match_phase;


-- 4. MATCH PHASE BOWLING METRICS
CREATE OR REPLACE VIEW v_match_phase_bowling AS
SELECT 
    p.player_id,
    p.player_name,
    CASE 
        WHEN d.over_no BETWEEN 0 AND 5 THEN 'Powerplay (0-5)'
        WHEN d.over_no BETWEEN 6 AND 14 THEN 'Middle (6-14)'
        ELSE 'Death (15-19)'
    END AS match_phase,
    COUNT(CASE WHEN d.is_legal_ball THEN 1 END) AS phase_legal_balls,
    SUM(d.runs_batter + d.wides + d.noballs) AS phase_runs_conceded,
    COUNT(CASE WHEN d.is_bowler_wicket THEN 1 END) AS phase_wickets,
    ROUND((SUM(d.runs_batter + d.wides + d.noballs) * 6.0) / NULLIF(COUNT(CASE WHEN d.is_legal_ball THEN 1 END), 0), 2) AS phase_economy
FROM fact_deliveries d
JOIN dim_players p ON d.bowler_id = p.player_id
GROUP BY p.player_id, p.player_name, match_phase;


-- 5. TEAM HEAD-TO-HEAD SUMMARY VIEW
CREATE OR REPLACE VIEW v_team_head_to_head AS
SELECT 
    LEAST(t1.team_name, t2.team_name) AS team_a,
    GREATEST(t1.team_name, t2.team_name) AS team_b,
    COUNT(*) AS total_matches,
    COUNT(CASE WHEN w.team_name = LEAST(t1.team_name, t2.team_name) THEN 1 END) AS team_a_wins,
    COUNT(CASE WHEN w.team_name = GREATEST(t1.team_name, t2.team_name) THEN 1 END) AS team_b_wins,
    COUNT(CASE WHEN m.winner_team_id IS NULL THEN 1 END) AS ties_or_no_result
FROM fact_matches m
JOIN dim_teams t1 ON m.team1_id = t1.team_id
JOIN dim_teams t2 ON m.team2_id = t2.team_id
LEFT JOIN dim_teams w ON m.winner_team_id = w.team_id
GROUP BY team_a, team_b;
