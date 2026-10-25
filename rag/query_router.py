import re
from enum import Enum
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

class RouteType(str, Enum):
    SQL_ONLY = "SQL_ONLY"
    RAG_ONLY = "RAG_ONLY"
    HYBRID = "HYBRID"
    CLARIFICATION = "CLARIFICATION"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"

@dataclass
class RouteDecision:
    route: RouteType
    confidence: float
    reason: str
    sql_intent: Optional[str] = None
    sql_params: Dict[str, Any] = None
    clarification_prompt: Optional[str] = None

class QueryRouter:
    """
    Intelligent Query Router directing user requests to the appropriate engine:
    - SQL_ONLY: Exact numerical aggregations, rankings, strike rates, economy, H2H
    - RAG_ONLY: Match narratives, ball event descriptions, cricket rules
    - HYBRID: Combined statistical comparison and contextual narrative
    - CLARIFICATION: Underspecified or ambiguous queries
    - INSUFFICIENT_DATA: Out-of-scope or unrecorded information
    """

    # Out-of-scope topics
    OUT_OF_SCOPE_TERMS = [
        "fifa", "world cup", "football", "soccer", "tennis", "nba",
        "basketball", "bbl", "psl", "cpl", "super smash", "election",
        "weather", "stock price", "crypto", "bitcoin"
    ]

    # Explicit SQL keywords
    SQL_KEYWORDS = [
        "how many runs", "most runs", "highest run", "top scorer", "leading run",
        "how many wickets", "most wickets", "highest wicket", "leading wicket",
        "strike rate", "economy rate", "average", "head to head", "h2h",
        "win percentage", "how many matches won", "boundaries", "most sixes",
        "most fours", "fifties", "centuries", "100s", "50s", "death overs strike rate",
        "powerplay run rate", "total matches per season"
    ]

    # Explicit RAG keywords
    RAG_KEYWORDS = [
        "summarize", "summary", "story of", "what happened", "explain the rule",
        "rules of", "definition of", "how does super over work", "what is dls",
        "duckworth lewis", "bowler wicket rule", "narrate", "overview of the match"
    ]

    @classmethod
    def route_query(
        cls,
        query: str,
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> RouteDecision:
        q_clean = query.strip()
        q_lower = q_clean.lower()
        words = q_lower.split()

        # 1. Out of Scope Check
        for oos in cls.OUT_OF_SCOPE_TERMS:
            if re.search(rf"\b{re.escape(oos)}\b", q_lower):
                return RouteDecision(
                    route=RouteType.INSUFFICIENT_DATA,
                    confidence=0.98,
                    reason=f"Query references '{oos}', which is outside the IPL cricket analytics domain."
                )

        # Check for future years
        year_match = re.search(r"\b(20[3-9]\d)\b", q_lower)
        if year_match:
            return RouteDecision(
                route=RouteType.INSUFFICIENT_DATA,
                confidence=0.99,
                reason=f"Query asks about future year {year_match.group(1)}, for which no IPL data exists."
            )

        # 2. Ambiguity & Clarification Check
        AMBIGUOUS_PATTERNS = [
            r"\bwho is the best\b", r"\bbest player\b", r"\bgreatest player\b",
            r"\bmatch score\b", r"\bipl stats\b", r"\bwho won\??\b", r"\btop team\b"
        ]
        if any(re.search(p, q_lower) for p in AMBIGUOUS_PATTERNS) and not any(w in q_lower for w in ["2016", "2024", "final", "runs", "wickets", "sixes"]):
            return RouteDecision(
                route=RouteType.CLARIFICATION,
                confidence=0.95,
                reason="Query is ambiguous without specified criteria, season, team, or player.",
                clarification_prompt="Could you please specify which season, team, or metric (e.g. most runs, wickets, or head-to-head) you would like to analyze?"
            )

        if "the match" in q_lower and not re.search(r"\b(\d{6,7}|20\d{2}|final|csk|rcb|mi|kkr)\b", q_lower):
            return RouteDecision(
                route=RouteType.CLARIFICATION,
                confidence=0.92,
                reason="Query refers to 'the match' without a specific match identifier, season, or participating teams.",
                clarification_prompt="Which specific match or teams are you referring to? You can provide a match ID, season, or team names."
            )

        # 3. Detect Hybrid Queries
        has_sql_need = any(k in q_lower for k in cls.SQL_KEYWORDS)
        has_rag_need = any(k in q_lower for k in cls.RAG_KEYWORDS)
        is_comparative = "compare" in q_lower or "versus" in q_lower or " vs " in q_lower or "difference between" in q_lower

        if (has_sql_need and has_rag_need) or (is_comparative and any(k in q_lower for k in ["style", "explain", "why", "performance", "trend"])):
            intent, params = cls._extract_sql_intent(q_clean)
            return RouteDecision(
                route=RouteType.HYBRID,
                confidence=0.92,
                reason="Query requires both verified statistical calculations and narrative contextual analysis.",
                sql_intent=intent,
                sql_params=params
            )

        # 4. Pure SQL Queries
        if has_sql_need:
            intent, params = cls._extract_sql_intent(q_clean)
            return RouteDecision(
                route=RouteType.SQL_ONLY,
                confidence=0.95,
                reason="Query asks for exact numerical statistics, aggregations, or rankings best solved by the SQL Analytics Engine.",
                sql_intent=intent,
                sql_params=params
            )

        # 5. Pure RAG Queries
        if has_rag_need or any(w in q_lower for w in ["final", "scorecard", "toss", "super over", "rule"]):
            return RouteDecision(
                route=RouteType.RAG_ONLY,
                confidence=0.90,
                reason="Query asks for qualitative context, match narratives, or cricket rules best solved by RAG retrieval."
            )

        # 6. Fallback based on Entity Matching
        intent, params = cls._extract_sql_intent(q_clean)
        if intent:
            return RouteDecision(
                route=RouteType.SQL_ONLY,
                confidence=0.85,
                reason="Query maps directly to a verified statistical player/team profile.",
                sql_intent=intent,
                sql_params=params
            )

        # Default to Hybrid RAG for general conversational inquiries
        return RouteDecision(
            route=RouteType.RAG_ONLY,
            confidence=0.80,
            reason="Query is contextual or open-ended; utilizing hybrid semantic retrieval."
        )

    @classmethod
    def _extract_sql_intent(cls, query: str) -> tuple[Optional[str], Dict[str, Any]]:
        q_lower = query.lower()
        params: Dict[str, Any] = {}

        # Extract season if present
        season_match = re.search(r"\b(20\d{2}(?:/\d{2})?)\b", q_lower)
        if season_match:
            params["season"] = season_match.group(1)

        # Check Head to Head
        teams_found = []
        team_patterns = {
            "Chennai Super Kings": ["csk", "chennai super kings", "chennai"],
            "Mumbai Indians": ["mi", "mumbai indians", "mumbai"],
            "Royal Challengers Bangalore": ["rcb", "royal challengers bangalore", "bangalore", "bengaluru"],
            "Kolkata Knight Riders": ["kkr", "kolkata knight riders", "kolkata"],
            "Delhi Capitals": ["dc", "delhi capitals", "delhi daredevils", "delhi"],
            "Rajasthan Royals": ["rr", "rajasthan royals", "rajasthan"],
            "Sunrisers Hyderabad": ["srh", "sunrisers hyderabad", "hyderabad"],
            "Punjab Kings": ["pbks", "punjab kings", "kings xi punjab", "punjab"],
            "Lucknow Super Giants": ["lsg", "lucknow super giants", "lucknow"],
            "Gujarat Titans": ["gt", "gujarat titans", "gujarat"]
        }
        for team_name, aliases in team_patterns.items():
            if any(re.search(rf"\b{re.escape(a)}\b", q_lower) for a in aliases):
                teams_found.append(team_name)

        if len(teams_found) >= 2 or ("head to head" in q_lower and len(teams_found) >= 1):
            params["team1"] = teams_found[0]
            params["team2"] = teams_found[1] if len(teams_found) > 1 else "Mumbai Indians"
            return "HEAD_TO_HEAD", params

        # Check Wickets
        if any(w in q_lower for w in ["wicket", "bowler", "economy"]):
            return "TOP_WICKET_TAKERS", params

        # Check Death Overs
        if "death" in q_lower or "slog" in q_lower:
            return "DEATH_OVERS_RANKINGS", params

        # Check Run Scorers
        if any(w in q_lower for w in ["runs", "batter", "strike rate", "scorer", "orange cap", "sixes", "fours"]):
            return "TOP_RUN_SCORERS", params

        # Check Venues
        if any(w in q_lower for w in ["stadium", "venue", "ground", "wankhede", "eden gardens", "chinnaswamy"]):
            return "VENUE_STATS", params

        # Check player profile and player vs opponent
        known_players = [
            ("V Kohli", ["kohli", "virat"]),
            ("MS Dhoni", ["dhoni", "thala", "msd"]),
            ("RG Sharma", ["rohit", "sharma", "hitman"]),
            ("AB de Villiers", ["abd", "villiers"]),
            ("DA Warner", ["warner"]),
            ("JJ Bumrah", ["bumrah"]),
            ("YS Chahal", ["chahal"]),
            ("B Kumar", ["bhuvneshwar", "bhuvi"])
        ]
        found_player = None
        for canon, aliases in known_players:
            if any(re.search(rf"\b{re.escape(a)}\b", q_lower) for a in aliases):
                found_player = canon
                params["player_name"] = canon
                break

        if found_player:
            if teams_found:
                params["opponent"] = teams_found[0]
                return "PLAYER_VS_OPPONENT", params
            return "PLAYER_PROFILE", params

        # Default fallback intent if general seasons question
        if "season" in q_lower or "matches per season" in q_lower:
            return "MATCHES_PER_SEASON", params

        return None, params
