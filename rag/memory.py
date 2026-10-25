import time
import uuid
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

@dataclass
class ActiveContext:
    active_player: Optional[str] = None
    active_team: Optional[str] = None
    active_season: Optional[str] = None
    active_match_id: Optional[int] = None
    last_topic: Optional[str] = None

@dataclass
class ConversationTurn:
    role: str
    content: str
    route: Optional[str] = None
    timestamp: float = field(default_factory=time.time)

class SessionMemory:
    """
    In-memory, session-scoped conversational state tracking.
    Maintains message history and extracts active entities across turns.
    Keeps conversation state completely decoupled from permanent data storage.
    """
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.created_at = time.time()
        self.last_activity = time.time()
        self.history: List[ConversationTurn] = []
        self.active_context = ActiveContext()

    def add_turn(
        self,
        role: str,
        content: str,
        route: Optional[str] = None,
        entities: Optional[Dict[str, Any]] = None
    ):
        self.last_activity = time.time()
        self.history.append(ConversationTurn(role=role, content=content, route=route))

        # Update active entities if provided
        if entities:
            if entities.get("player"):
                self.active_context.active_player = entities["player"]
            if entities.get("season"):
                self.active_context.active_season = str(entities["season"])
            if entities.get("team"):
                self.active_context.active_team = entities["team"]
            if entities.get("match_id"):
                self.active_context.active_match_id = int(entities["match_id"])
            if entities.get("topic"):
                self.active_context.last_topic = entities["topic"]

    def get_history(self, max_turns: int = 6) -> List[Dict[str, str]]:
        recent = self.history[-max_turns:]
        return [{"role": t.role, "content": t.content} for t in recent]

    def reset_context(self):
        self.active_context = ActiveContext()

    def clear(self):
        self.history.clear()
        self.reset_context()

class SessionManager:
    """
    Thread-safe registry for managing active conversational sessions.
    Automatically expires sessions inactive for longer than max_age_seconds (default: 2 hours).
    """
    def __init__(self, max_age_seconds: int = 7200):
        self._sessions: Dict[str, SessionMemory] = {}
        self.max_age_seconds = max_age_seconds

    def get_or_create(self, session_id: Optional[str] = None) -> SessionMemory:
        self._cleanup_expired()
        if not session_id or session_id not in self._sessions:
            new_id = session_id or str(uuid.uuid4())
            self._sessions[new_id] = SessionMemory(session_id=new_id)
            return self._sessions[new_id]
        return self._sessions[session_id]

    def _cleanup_expired(self):
        now = time.time()
        expired = [sid for sid, s in self._sessions.items() if (now - s.last_activity) > self.max_age_seconds]
        for sid in expired:
            del self._sessions[sid]

    def session_count(self) -> int:
        return len(self._sessions)
