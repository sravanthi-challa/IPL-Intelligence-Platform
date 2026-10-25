import os
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import APIRouter, HTTPException, Query, Depends

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "analytics"))
sys.path.insert(0, str(PROJECT_ROOT / "rag"))
sys.path.insert(0, str(PROJECT_ROOT / "database"))

from metrics import CricketAnalytics
from orchestrator import ConversationalOrchestrator
from hybrid_retrieval import HybridRetriever
from vector_store import VectorStore
from connection import get_db_connection
from models import (
    ChatRequest, ChatResponse, AnalyticsQueryRequest,
    SearchRequest, HealthResponse
)

router = APIRouter()

# Singleton orchestrator and retrieval instances
orchestrator = ConversationalOrchestrator()
hybrid_retriever = HybridRetriever()
vector_store = VectorStore()

def get_db():
    with get_db_connection() as conn:
        yield conn

# ----------------------------------------------------
# HEALTH CHECK
# ----------------------------------------------------
@router.get("/health", response_model=HealthResponse)
def health_check(conn=Depends(get_db)):
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM fact_matches;")
            matches_cnt = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM fact_deliveries;")
            deliv_cnt = cur.fetchone()[0]
            chunks_cnt = vector_store.count()

        return HealthResponse(
            status="healthy",
            database="connected",
            total_matches=matches_cnt,
            total_deliveries=deliv_cnt,
            vector_chunks=chunks_cnt,
            version="1.0.0"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database health check failed: {str(e)}")

# ----------------------------------------------------
# CONVERSATIONAL CHAT
# ----------------------------------------------------
@router.post("/chat", response_model=ChatResponse)
def chat_endpoint(req: ChatRequest):
    try:
        res = orchestrator.chat(message=req.message, session_id=req.session_id)
        return ChatResponse(
            session_id=res["session_id"],
            original_query=res["original_query"],
            transformed_query=res.get("transformed_query"),
            route=res["route"],
            route_reason=res["route_reason"],
            answer=res["answer"],
            sources=res.get("sources", []),
            sql_data=res.get("sql_data"),
            retrieved_chunks=[
                {
                    "chunk_id": c.get("chunk_id", ""),
                    "doc_id": c.get("doc_id", ""),
                    "title": c.get("title", ""),
                    "score": c.get("score")
                }
                for c in res.get("retrieved_chunks", [])
            ]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat processing error: {str(e)}")

# ----------------------------------------------------
# DIMENSION LOOKUPS
# ----------------------------------------------------
@router.get("/seasons")
def list_seasons(conn=Depends(get_db)):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT season_id, season_name FROM dim_seasons ORDER BY season_name;")
        return cur.fetchall()

@router.get("/teams")
def list_teams(conn=Depends(get_db)):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT team_id, team_name FROM dim_teams ORDER BY team_name;")
        return cur.fetchall()

@router.get("/venues")
def list_venues(conn=Depends(get_db)):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT venue_id, venue_name, city FROM dim_venues ORDER BY venue_name;")
        return cur.fetchall()

@router.get("/players")
def list_players(search: Optional[str] = None, limit: int = 50, conn=Depends(get_db)):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        if search:
            cur.execute("""
                SELECT player_id, player_name, cricsheet_player_id
                FROM dim_players
                WHERE player_name ILIKE %s
                ORDER BY player_name
                LIMIT %s;
            """, (f"%{search}%", limit))
        else:
            cur.execute("""
                SELECT player_id, player_name, cricsheet_player_id
                FROM dim_players
                ORDER BY player_name
                LIMIT %s;
            """, (limit,))
        return cur.fetchall()

@router.get("/matches")
def list_matches(season: Optional[str] = None, limit: int = 20, conn=Depends(get_db)):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        if season:
            cur.execute("""
                SELECT 
                    m.match_id, m.match_date, s.season_name, v.venue_name,
                    t1.team_name AS team1, t2.team_name AS team2,
                    w.team_name AS winner, m.win_margin_runs, m.win_margin_wickets,
                    m.player_of_match
                FROM fact_matches m
                JOIN dim_seasons s ON m.season_id = s.season_id
                JOIN dim_venues v ON m.venue_id = v.venue_id
                JOIN dim_teams t1 ON m.team1_id = t1.team_id
                JOIN dim_teams t2 ON m.team2_id = t2.team_id
                LEFT JOIN dim_teams w ON m.winner_team_id = w.team_id
                WHERE s.season_name = %s
                ORDER BY m.match_date DESC
                LIMIT %s;
            """, (season, limit))
        else:
            cur.execute("""
                SELECT 
                    m.match_id, m.match_date, s.season_name, v.venue_name,
                    t1.team_name AS team1, t2.team_name AS team2,
                    w.team_name AS winner, m.win_margin_runs, m.win_margin_wickets,
                    m.player_of_match
                FROM fact_matches m
                JOIN dim_seasons s ON m.season_id = s.season_id
                JOIN dim_venues v ON m.venue_id = v.venue_id
                JOIN dim_teams t1 ON m.team1_id = t1.team_id
                JOIN dim_teams t2 ON m.team2_id = t2.team_id
                LEFT JOIN dim_teams w ON m.winner_team_id = w.team_id
                ORDER BY m.match_date DESC
                LIMIT %s;
            """, (limit,))
        return cur.fetchall()

# ----------------------------------------------------
# CONSTRAINED SQL ANALYTICS
# ----------------------------------------------------
@router.post("/analytics/query")
def analytics_query_endpoint(req: AnalyticsQueryRequest):
    intent = req.intent.upper()
    try:
        if intent == "TOP_RUN_SCORERS":
            data = CricketAnalytics.get_top_run_scorers(season=req.season, limit=req.limit)
        elif intent == "TOP_WICKET_TAKERS":
            data = CricketAnalytics.get_top_wicket_takers(season=req.season, limit=req.limit)
        elif intent == "HEAD_TO_HEAD":
            t1 = req.team1 or "Chennai Super Kings"
            t2 = req.team2 or "Mumbai Indians"
            data = CricketAnalytics.get_head_to_head(t1, t2)
        elif intent == "DEATH_OVERS_RANKINGS":
            data = CricketAnalytics.get_death_overs_rankings(limit=req.limit)
        elif intent == "VENUE_STATS":
            data = CricketAnalytics.get_venue_statistics(limit=req.limit)
        elif intent == "MATCHES_PER_SEASON":
            data = CricketAnalytics.get_matches_per_season()
        elif intent == "PLAYER_PROFILE":
            pname = req.player_name or "V Kohli"
            data = CricketAnalytics.get_batter_profile(pname)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported analytics intent: {req.intent}")

        return {
            "intent": intent,
            "params": req.model_dump(),
            "results": data
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analytics query failed: {str(e)}")

# ----------------------------------------------------
# SEARCH ENDPOINT
# ----------------------------------------------------
@router.post("/search")
def search_endpoint(req: SearchRequest):
    try:
        if req.use_hybrid:
            results = hybrid_retriever.retrieve(
                query=req.query,
                top_k=req.top_k,
                doc_type=req.doc_type
            )
        else:
            from embeddings import get_embedding_provider
            emb = get_embedding_provider()
            q_vec = emb.embed_text(req.query)
            results = vector_store.similarity_search(
                query_embedding=q_vec,
                top_k=req.top_k,
                doc_type=req.doc_type
            )
        return {
            "query": req.query,
            "mode": "hybrid" if req.use_hybrid else "vector",
            "count": len(results),
            "results": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

# ----------------------------------------------------
# DATASET EVALUATION SUMMARY
# ----------------------------------------------------
@router.get("/evaluation/summary")
def evaluation_summary(conn=Depends(get_db)):
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM fact_matches;")
        m_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM fact_deliveries;")
        d_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM dim_players;")
        p_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM dim_seasons;")
        s_count = cur.fetchone()[0]

    return {
        "dataset": "Cricsheet IPL Match Records (2008-2024)",
        "total_matches": m_count,
        "total_deliveries": d_count,
        "total_players": p_count,
        "total_seasons": s_count,
        "retrieval_architecture": "Hybrid (PostgreSQL Full-Text Search + Dense Vectors via Reciprocal Rank Fusion)",
        "router_supported_modes": ["SQL_ONLY", "RAG_ONLY", "HYBRID", "CLARIFICATION", "INSUFFICIENT_DATA"],
        "vector_chunks_indexed": vector_store.count()
    }
