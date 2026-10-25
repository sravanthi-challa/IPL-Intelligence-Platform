from typing import Dict, Any, Optional, List
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "analytics"))
sys.path.insert(0, str(PROJECT_ROOT / "rag"))

from metrics import CricketAnalytics
from query_router import QueryRouter, RouteType, RouteDecision
from query_transformer import QueryTransformer
from hybrid_retrieval import HybridRetriever
from reranker import Reranker
from context_builder import ContextBuilder
from generator import RAGGenerator
from memory import SessionManager, SessionMemory

class ConversationalOrchestrator:
    """
    Unified Orchestrator implementing dynamic routing across:
    1. SQL_ONLY (Parameterized statistical execution)
    2. RAG_ONLY (Semantic hybrid document retrieval)
    3. HYBRID (Dual SQL calculation + contextual retrieval)
    4. CLARIFICATION (Disambiguation questions)
    5. INSUFFICIENT_DATA (Refusal for out-of-scope questions)

    Maintains active multi-turn conversational session memory and context resolution.
    """
    def __init__(self):
        self.hybrid_retriever = HybridRetriever()
        self.reranker = Reranker(enabled=True)
        self.generator = RAGGenerator()
        self.session_manager = SessionManager()

    def chat(
        self,
        message: str,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Public conversational entrypoint handling session lookup,
        multi-turn coreference resolution, routing, and response packaging.
        """
        session: SessionMemory = self.session_manager.get_or_create(session_id)
        history = session.get_history()

        # 1. Transform query using session history and active entity context
        transformed = QueryTransformer.transform(
            query=message,
            conversation_history=history,
            active_context=session.active_context
        )

        # 2. Process query along optimal route
        response = self.process_query(
            query=transformed.transformed_query,
            conversation_history=history
        )
        response["session_id"] = session.session_id
        response["original_query"] = message
        response["transformed_query"] = transformed.transformed_query

        # 3. Extract active entities to update session memory
        new_entities = {}
        if transformed.player:
            new_entities["player"] = transformed.player
        elif response.get("sql_data"):
            data = response["sql_data"]
            if isinstance(data, list) and len(data) > 0 and "player_name" in data[0]:
                new_entities["player"] = data[0]["player_name"]
            elif isinstance(data, dict) and "player_name" in data:
                new_entities["player"] = data["player_name"]

        if transformed.season:
            new_entities["season"] = transformed.season
        if transformed.team:
            new_entities["team"] = transformed.team

        # 4. Record turns in session memory
        session.add_turn(role="user", content=message)
        session.add_turn(
            role="assistant",
            content=response["answer"],
            route=response["route"],
            entities=new_entities
        )

        return response

    def process_query(
        self,
        query: str,
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        # 1. Route Decision
        decision: RouteDecision = QueryRouter.route_query(query, conversation_history)

        # 2. Handle Refusal (INSUFFICIENT_DATA)
        if decision.route == RouteType.INSUFFICIENT_DATA:
            return {
                "query": query,
                "route": decision.route.value,
                "route_reason": decision.reason,
                "answer": (
                    f"I cannot answer this question because it is outside the IPL analytics domain. "
                    f"{decision.reason} The system contains verified data exclusively for the Indian Premier League (2008–2024)."
                ),
                "sql_data": None,
                "sources": [],
                "retrieved_chunks": []
            }

        # 3. Handle Ambiguity (CLARIFICATION)
        if decision.route == RouteType.CLARIFICATION:
            return {
                "query": query,
                "route": decision.route.value,
                "route_reason": decision.reason,
                "answer": decision.clarification_prompt,
                "sql_data": None,
                "sources": [],
                "retrieved_chunks": []
            }

        # 4. Handle SQL_ONLY Path
        if decision.route == RouteType.SQL_ONLY:
            sql_results = self._execute_sql_intent(decision.sql_intent, decision.sql_params)
            context = ContextBuilder.build_context(chunks=[], sql_data=sql_results)
            answer = self.generator.generate_answer(
                question=query,
                context_text=context["context_text"],
                conversation_history=conversation_history
            )
            return {
                "query": query,
                "route": decision.route.value,
                "route_reason": decision.reason,
                "answer": answer,
                "sql_data": sql_results,
                "sources": [{"doc_id": "postgres_sql_engine", "title": f"SQL View: {decision.sql_intent}"}],
                "retrieved_chunks": []
            }

        # 5. Handle HYBRID Path
        if decision.route == RouteType.HYBRID:
            sql_results = self._execute_sql_intent(decision.sql_intent, decision.sql_params)
            raw_chunks = self.hybrid_retriever.retrieve(query=query, top_k=6)
            chunks = self.reranker.rerank(query, raw_chunks, top_k=3)
            context = ContextBuilder.build_context(chunks=chunks, sql_data=sql_results)
            answer = self.generator.generate_answer(
                question=query,
                context_text=context["context_text"],
                conversation_history=conversation_history
            )
            return {
                "query": query,
                "route": decision.route.value,
                "route_reason": decision.reason,
                "answer": answer,
                "sql_data": sql_results,
                "sources": context["sources"] + [{"doc_id": "postgres_sql_engine", "title": f"SQL View: {decision.sql_intent}"}],
                "retrieved_chunks": chunks
            }

        # 6. Handle RAG_ONLY Path
        raw_chunks = self.hybrid_retriever.retrieve(query=query, top_k=6)
        chunks = self.reranker.rerank(query, raw_chunks, top_k=3)
        context = ContextBuilder.build_context(chunks=chunks)
        answer = self.generator.generate_answer(
            question=query,
            context_text=context["context_text"],
            conversation_history=conversation_history
        )
        return {
            "query": query,
            "route": decision.route.value,
            "route_reason": decision.reason,
            "answer": answer,
            "sql_data": None,
            "sources": context["sources"],
            "retrieved_chunks": chunks
        }

    def _execute_sql_intent(self, intent: Optional[str], params: Dict[str, Any]) -> Any:
        season = params.get("season")
        if intent == "TOP_RUN_SCORERS":
            return CricketAnalytics.get_top_run_scorers(season=season, limit=5)
        elif intent == "TOP_WICKET_TAKERS":
            return CricketAnalytics.get_top_wicket_takers(season=season, limit=5)
        elif intent == "HEAD_TO_HEAD":
            t1 = params.get("team1", "Chennai Super Kings")
            t2 = params.get("team2", "Mumbai Indians")
            return CricketAnalytics.get_head_to_head(t1, t2)
        elif intent == "PLAYER_VS_OPPONENT":
            pname = params.get("player_name", "V Kohli")
            opp = params.get("opponent", "Chennai Super Kings")
            res = CricketAnalytics.get_player_vs_opponent(pname, opp)
            if res:
                return res
            return CricketAnalytics.get_batter_profile(pname)
        elif intent == "PLAYER_PROFILE":
            pname = params.get("player_name", "V Kohli")
            return CricketAnalytics.get_batter_profile(pname)
        elif intent == "DEATH_OVERS_RANKINGS":
            return CricketAnalytics.get_death_overs_rankings(min_balls=80, limit=5)
        elif intent == "VENUE_STATS":
            return CricketAnalytics.get_venue_statistics(limit=5)
        elif intent == "MATCHES_PER_SEASON":
            return CricketAnalytics.get_matches_per_season()
        else:
            return CricketAnalytics.get_top_run_scorers(limit=5)
