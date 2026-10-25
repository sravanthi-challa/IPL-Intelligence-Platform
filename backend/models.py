from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000, description="User natural language cricket question")
    session_id: Optional[str] = Field(None, description="Active session ID for multi-turn conversational memory")

class SourceReference(BaseModel):
    doc_id: str
    title: str
    doc_type: Optional[str] = None

class ChunkSnippet(BaseModel):
    chunk_id: str
    doc_id: str
    title: str
    score: Optional[float] = None

class ChatResponse(BaseModel):
    session_id: str
    original_query: str
    transformed_query: Optional[str] = None
    route: str
    route_reason: str
    answer: str
    sources: List[SourceReference] = []
    sql_data: Optional[Any] = None
    retrieved_chunks: List[ChunkSnippet] = []

class AnalyticsQueryRequest(BaseModel):
    intent: str = Field(..., description="Analytics intent: TOP_RUN_SCORERS, TOP_WICKET_TAKERS, HEAD_TO_HEAD, DEATH_OVERS_RANKINGS, VENUE_STATS, MATCHES_PER_SEASON")
    season: Optional[str] = None
    team1: Optional[str] = None
    team2: Optional[str] = None
    player_name: Optional[str] = None
    limit: int = Field(10, ge=1, le=50)

class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    top_k: int = Field(5, ge=1, le=20)
    doc_type: Optional[str] = None
    use_hybrid: bool = True

class HealthResponse(BaseModel):
    status: str
    database: str
    total_matches: int
    total_deliveries: int
    vector_chunks: int
    version: str = "1.0.0"
