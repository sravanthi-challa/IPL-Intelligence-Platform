import pytest
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "rag"))
sys.path.insert(0, str(PROJECT_ROOT / "analytics"))

from query_router import QueryRouter, RouteType
from orchestrator import ConversationalOrchestrator

def test_route_sql_numerical_questions():
    # 1. Season run scorer
    d1 = QueryRouter.route_query("Who scored the most runs in 2016?")
    assert d1.route == RouteType.SQL_ONLY
    assert d1.sql_intent == "TOP_RUN_SCORERS"
    assert d1.sql_params["season"] == "2016"

    # 2. Head to head
    d2 = QueryRouter.route_query("What is the head to head record between CSK and MI?")
    assert d2.route == RouteType.SQL_ONLY
    assert d2.sql_intent == "HEAD_TO_HEAD"

    # 3. Wicket takers
    d3 = QueryRouter.route_query("Who took the most wickets in IPL history?")
    assert d3.route == RouteType.SQL_ONLY
    assert d3.sql_intent == "TOP_WICKET_TAKERS"

def test_route_rag_narrative_and_rules():
    # 1. Match narrative
    d1 = QueryRouter.route_query("Summarize what happened in the 2016 final match")
    assert d1.route == RouteType.RAG_ONLY

    # 2. Cricket rules
    d2 = QueryRouter.route_query("Explain the cricket rules for tie and super overs")
    assert d2.route == RouteType.RAG_ONLY

def test_route_hybrid_questions():
    d = QueryRouter.route_query("Compare Kohli and Rohit in death overs and explain their batting styles")
    assert d.route == RouteType.HYBRID

def test_route_clarification_ambiguous():
    d1 = QueryRouter.route_query("Who is the best player?")
    assert d1.route == RouteType.CLARIFICATION
    assert d1.clarification_prompt is not None

    d2 = QueryRouter.route_query("Tell me about the match")
    assert d2.route == RouteType.CLARIFICATION

def test_route_insufficient_data():
    # Non-cricket domain
    d1 = QueryRouter.route_query("Who won the FIFA World Cup?")
    assert d1.route == RouteType.INSUFFICIENT_DATA

    # Future season
    d2 = QueryRouter.route_query("What was the result in IPL 2035?")
    assert d2.route == RouteType.INSUFFICIENT_DATA

def test_orchestrator_sql_route_execution():
    orchestrator = ConversationalOrchestrator()
    res = orchestrator.process_query("Who scored the most runs in 2016?")
    assert res["route"] == "SQL_ONLY"
    assert res["sql_data"] is not None
    # Verify Virat Kohli 973 runs in SQL data
    assert any("Kohli" in row["player_name"] for row in res["sql_data"])
    assert len(res["answer"]) > 0

def test_orchestrator_hybrid_route_execution():
    orchestrator = ConversationalOrchestrator()
    res = orchestrator.process_query("Compare Kohli and Rohit in death overs and explain")
    assert res["route"] == "HYBRID"
    assert res["sql_data"] is not None
    assert len(res["retrieved_chunks"]) > 0
    assert len(res["sources"]) > 0
