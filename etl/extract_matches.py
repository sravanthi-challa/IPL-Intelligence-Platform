import json
from pathlib import Path
from typing import Dict, Any, List, Tuple

# Official cricket rules: bowler wickets
BOWLER_WICKET_KINDS = {
    "bowled",
    "caught",
    "caught and bowled",
    "hit wicket",
    "lbw",
    "stumped",
}

NON_BOWLER_WICKET_KINDS = {
    "run out",
    "retired hurt",
    "retired out",
    "obstructing the field",
}

def parse_match_json(file_path: Path) -> Dict[str, Any]:
    """
    Parses a single Cricsheet JSON match file into normalized match,
    players, and delivery records.
    """
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    info = data.get("info", {})
    match_id = int(file_path.stem)
    
    # 1. Match metadata
    dates = info.get("dates", [])
    match_date = dates[0] if dates else None
    season = str(info.get("season", ""))
    venue = info.get("venue", "Unknown Venue")
    city = info.get("city")
    teams = info.get("teams", [])
    
    toss = info.get("toss", {})
    toss_winner = toss.get("winner")
    toss_decision = toss.get("decision")
    
    outcome = info.get("outcome", {})
    winner = outcome.get("winner")
    by_dict = outcome.get("by", {})
    win_margin_runs = by_dict.get("runs")
    win_margin_wickets = by_dict.get("wickets")
    result_type = outcome.get("result", "normal")
    
    pom_list = info.get("player_of_match", [])
    player_of_match = pom_list[0] if pom_list else None
    
    # 2. Extract players registry
    # registry: {name: cricsheet_id}
    people_registry = info.get("registry", {}).get("people", {})
    players_by_team = info.get("players", {})
    all_players: Dict[str, str] = {}
    
    # First populate from registry
    for name, c_id in people_registry.items():
        all_players[name] = c_id
        
    # Ensure any team player without a registry entry gets tracked
    for t, p_list in players_by_team.items():
        for p in p_list:
            if p not in all_players:
                all_players[p] = None

    # 3. Deliveries parsing
    deliveries_list: List[Dict[str, Any]] = []
    
    for inn_idx, inn in enumerate(data.get("innings", []), start=1):
        batting_team = inn.get("team")
        # Bowling team is the opposing team
        bowling_team = None
        for t in teams:
            if t != batting_team:
                bowling_team = t
                break
        if not bowling_team and len(teams) > 0:
            bowling_team = teams[0]
            
        overs = inn.get("overs", [])
        for over_data in overs:
            over_no = over_data.get("over", 0)
            delivs = over_data.get("deliveries", [])
            for ball_idx, deliv in enumerate(delivs, start=1):
                batter = deliv.get("batter")
                bowler = deliv.get("bowler")
                non_striker = deliv.get("non_striker")
                
                runs_dict = deliv.get("runs", {})
                runs_batter = runs_dict.get("batter", 0)
                runs_extras = runs_dict.get("extras", 0)
                runs_total = runs_dict.get("total", runs_batter + runs_extras)
                
                extras_dict = deliv.get("extras", {})
                wides = extras_dict.get("wides", 0)
                noballs = extras_dict.get("noballs", 0)
                byes = extras_dict.get("byes", 0)
                legbyes = extras_dict.get("legbyes", 0)
                penalty = extras_dict.get("penalty", 0)
                
                extra_type = next(iter(extras_dict.keys()), None) if extras_dict else None
                is_legal_ball = (wides == 0 and noballs == 0)
                
                wickets = deliv.get("wickets", [])
                is_wicket = len(wickets) > 0
                dismissal_type = None
                player_out = None
                is_bowler_wicket = False
                
                if is_wicket:
                    w = wickets[0]
                    dismissal_type = w.get("kind")
                    player_out = w.get("player_out")
                    is_bowler_wicket = dismissal_type in BOWLER_WICKET_KINDS

                deliveries_list.append({
                    "match_id": match_id,
                    "innings_no": inn_idx,
                    "over_no": over_no,
                    "ball_no": ball_idx,
                    "batting_team": batting_team,
                    "bowling_team": bowling_team,
                    "batter": batter,
                    "bowler": bowler,
                    "non_striker": non_striker,
                    "runs_batter": runs_batter,
                    "runs_extras": runs_extras,
                    "runs_total": runs_total,
                    "is_wicket": is_wicket,
                    "dismissal_type": dismissal_type,
                    "player_out": player_out,
                    "is_bowler_wicket": is_bowler_wicket,
                    "is_legal_ball": is_legal_ball,
                    "extra_type": extra_type,
                    "extra_runs": runs_extras,
                    "wides": wides,
                    "noballs": noballs,
                    "byes": byes,
                    "legbyes": legbyes,
                    "penalty": penalty,
                })

    return {
        "match": {
            "match_id": match_id,
            "match_date": match_date,
            "season": season,
            "venue": venue,
            "city": city,
            "teams": teams,
            "toss_winner": toss_winner,
            "toss_decision": toss_decision,
            "winner": winner,
            "win_margin_runs": win_margin_runs,
            "win_margin_wickets": win_margin_wickets,
            "result_type": result_type,
            "player_of_match": player_of_match,
        },
        "players": all_players,
        "deliveries": deliveries_list,
    }
