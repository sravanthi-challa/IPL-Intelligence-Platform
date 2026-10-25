import re
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

@dataclass
class TransformedQuery:
    original_query: str
    transformed_query: str
    season: Optional[str] = None
    team: Optional[str] = None
    player: Optional[str] = None
    doc_type: Optional[str] = None
    is_conversational_followup: bool = False
    resolved_references: Dict[str, str] = None

class QueryTransformer:
    """
    Transforms and disambiguates natural language user queries:
    - Resolves conversational references and pronouns ('he', 'that team', 'the final')
    - Extracts structured metadata filters (season, team, player, doc_type)
    - Expands cricket abbreviations and terminology
    """

    # Season extraction regex (e.g. 2008, 2016, 2024, or 2007/08)
    SEASON_PATTERN = re.compile(r"\b(20\d{2}(?:/\d{2})?)\b")
    
    # Team mappings
    TEAM_CANONICAL = {
        "csk": "Chennai Super Kings",
        "chennai": "Chennai Super Kings",
        "chennai super kings": "Chennai Super Kings",
        "rcb": "Royal Challengers Bangalore",
        "bangalore": "Royal Challengers Bangalore",
        "bengaluru": "Royal Challengers Bangalore",
        "royal challengers bangalore": "Royal Challengers Bangalore",
        "mi": "Mumbai Indians",
        "mumbai": "Mumbai Indians",
        "mumbai indians": "Mumbai Indians",
        "kkr": "Kolkata Knight Riders",
        "kolkata": "Kolkata Knight Riders",
        "kolkata knight riders": "Kolkata Knight Riders",
        "dc": "Delhi Capitals",
        "delhi": "Delhi Capitals",
        "delhi capitals": "Delhi Capitals",
        "rr": "Rajasthan Royals",
        "rajasthan": "Rajasthan Royals",
        "rajasthan royals": "Rajasthan Royals",
        "srh": "Sunrisers Hyderabad",
        "hyderabad": "Sunrisers Hyderabad",
        "sunrisers hyderabad": "Sunrisers Hyderabad",
        "pbks": "Punjab Kings",
        "punjab": "Punjab Kings",
        "kings xi punjab": "Punjab Kings",
        "lsg": "Lucknow Super Giants",
        "lucknow": "Lucknow Super Giants",
        "gt": "Gujarat Titans",
        "gujarat": "Gujarat Titans",
    }

    @classmethod
    def transform(
        cls,
        query: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        active_context: Optional[Any] = None
    ) -> TransformedQuery:
        transformed = query.strip()
        season = None
        team = None
        player = None
        doc_type = None
        is_followup = False
        resolved = {}

        # 1. Extract Season
        season_match = cls.SEASON_PATTERN.search(transformed)
        if season_match:
            season = season_match.group(1)
        elif "first ipl" in transformed.lower() or "inaugural" in transformed.lower():
            season = "2007/08"

        # 2. Extract Team & Expand Team Abbreviations
        query_lower = transformed.lower()
        for k, canonical in cls.TEAM_CANONICAL.items():
            pattern = rf"\b{re.escape(k)}\b"
            if re.search(pattern, query_lower):
                team = canonical
                transformed = re.sub(pattern, canonical, transformed, flags=re.IGNORECASE)
                break

        # 3. Detect Document Type Intent
        if any(w in query_lower for w in ["rule", "definition", "what is", "how is", "glossary", "tie", "super over"]):
            doc_type = "glossary"
        elif any(w in query_lower for w in ["profile", "career", "biography", "stats of", "player"]):
            doc_type = "player"
        elif any(w in query_lower for w in ["match", "final", "scorecard", "versus", "vs", "won the toss"]):
            doc_type = "match"

        # 4. Resolve via ActiveContext if available
        if active_context:
            if not season and active_context.active_season:
                season = active_context.active_season
                resolved["season"] = season

            # Ellipse follow-up: e.g. "what about against MI?", "and against CSK?"
            is_ellipse = query_lower.startswith(("what about", "how about", "and against", "against "))
            pronoun_match = re.search(r"\b(he|him|his|that player|this player)\b", transformed, re.IGNORECASE)

            if (pronoun_match or is_ellipse) and active_context.active_player:
                is_followup = True
                player = active_context.active_player
                resolved["player"] = player
                if pronoun_match:
                    transformed = re.sub(
                        r"\b(he|him|his|that player|this player)\b",
                        player,
                        transformed,
                        flags=re.IGNORECASE
                    )
                elif is_ellipse and team:
                    transformed = f"How did {player} perform against {team}?"

        # 5. Resolve Conversational Pronouns & Follow-ups from message history
        if not is_followup and conversation_history and len(conversation_history) > 0:
            last_assistant_msg = ""
            last_user_msg = ""
            for turn in reversed(conversation_history):
                if turn.get("role") == "assistant" and not last_assistant_msg:
                    last_assistant_msg = turn.get("content", "")
                elif turn.get("role") == "user" and not last_user_msg:
                    last_user_msg = turn.get("content", "")

            pronoun_match = re.search(r"\b(he|him|his|that player|this player)\b", transformed, re.IGNORECASE)
            if pronoun_match and last_assistant_msg:
                is_followup = True
                player_candidate = cls._extract_entity_from_text(last_assistant_msg, last_user_msg)
                if player_candidate:
                    resolved["player"] = player_candidate
                    player = player_candidate
                    transformed = re.sub(
                        r"\b(he|him|his|that player|this player)\b",
                        player_candidate,
                        transformed,
                        flags=re.IGNORECASE
                    )

            if not season and last_user_msg:
                prev_season_match = cls.SEASON_PATTERN.search(last_user_msg)
                if prev_season_match:
                    season = prev_season_match.group(1)
                    resolved["season"] = season

        return TransformedQuery(
            original_query=query,
            transformed_query=transformed,
            season=season,
            team=team,
            player=player,
            doc_type=doc_type,
            is_conversational_followup=is_followup,
            resolved_references=resolved
        )

    @classmethod
    def _extract_entity_from_text(cls, assistant_text: str, user_text: str) -> Optional[str]:
        # Search for well-known player names mentioned in prior response
        known_players = [
            "Virat Kohli", "V Kohli", "MS Dhoni", "Rohit Sharma", "RG Sharma",
            "AB de Villiers", "David Warner", "DA Warner", "S Dhawan", "KL Rahul",
            "Jasprit Bumrah", "JJ Bumrah", "Yuzvendra Chahal", "YS Chahal",
            "Bhuvneshwar Kumar", "B Kumar", "Sunil Narine", "SP Narine",
            "Brendon McCullum", "BB McCullum", "Suresh Raina", "SK Raina"
        ]
        combined = f"{user_text}\n{assistant_text}"
        for p in known_players:
            if re.search(rf"\b{re.escape(p)}\b", combined, re.IGNORECASE):
                return p
        return None
