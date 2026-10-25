import pytest
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "rag"))
sys.path.insert(0, str(PROJECT_ROOT / "analytics"))

from memory import SessionMemory, SessionManager
from orchestrator import ConversationalOrchestrator

def test_session_memory_turns_and_context():
    session = SessionMemory(session_id="test_sess_1")
    assert session.session_id == "test_sess_1"
    assert len(session.history) == 0

    session.add_turn(
        role="user",
        content="Who scored the most runs in 2016?",
        route="SQL_ONLY",
        entities={"player": "V Kohli", "season": "2016"}
    )
    session.add_turn(
        role="assistant",
        content="Virat Kohli was the top scorer with 973 runs.",
        route="SQL_ONLY"
    )

    history = session.get_history(max_turns=2)
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"
    assert session.active_context.active_player == "V Kohli"
    assert session.active_context.active_season == "2016"

    # Reset
    session.clear()
    assert len(session.history) == 0
    assert session.active_context.active_player is None

def test_session_manager_get_or_create():
    manager = SessionManager(max_age_seconds=3600)
    sess1 = manager.get_or_create()
    assert sess1.session_id is not None
    assert manager.session_count() == 1

    # Same session ID fetches existing session
    sess1_fetch = manager.get_or_create(sess1.session_id)
    assert sess1_fetch is sess1

    # New session
    sess2 = manager.get_or_create()
    assert sess2.session_id != sess1.session_id
    assert manager.session_count() == 2

def test_multi_turn_conversational_resolution():
    orchestrator = ConversationalOrchestrator()
    session_id = "test_turn_session"

    # Turn 1: Ask about top scorer in 2016
    res1 = orchestrator.chat(message="Who scored the most runs in 2016?", session_id=session_id)
    assert res1["route"] == "SQL_ONLY"
    assert res1["session_id"] == session_id
    assert any("Kohli" in r["player_name"] for r in res1["sql_data"])

    # Turn 2: Follow-up using pronoun "he"
    res2 = orchestrator.chat(message="How did he perform against CSK?", session_id=session_id)
    assert "Kohli" in res2["transformed_query"]
    assert "Chennai Super Kings" in res2["transformed_query"]
    assert res2["route"] == "SQL_ONLY"
    assert res2["sql_data"] is not None

    # Turn 3: Ellipse follow-up "What about against MI?"
    res3 = orchestrator.chat(message="What about against MI?", session_id=session_id)
    assert "Kohli" in res3["transformed_query"]
    assert "Mumbai Indians" in res3["transformed_query"]
    assert res3["sql_data"] is not None
