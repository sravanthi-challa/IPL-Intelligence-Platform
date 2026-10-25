import pytest
import sys
from pathlib import Path
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))
sys.path.insert(0, str(PROJECT_ROOT / "analytics"))
sys.path.insert(0, str(PROJECT_ROOT / "rag"))

from main import app

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c

def test_api_root(client):
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "IPL Intelligence" in data["title"]
    assert data["version"] == "1.0.0"

def test_api_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"
    assert data["total_matches"] == 1241
    assert data["total_deliveries"] > 290000

def test_api_seasons(client):
    response = client.get("/seasons")
    assert response.status_code == 200
    seasons = response.json()
    assert len(seasons) >= 17
    assert any("2016" in s["season_name"] for s in seasons)

def test_api_teams(client):
    response = client.get("/teams")
    assert response.status_code == 200
    teams = response.json()
    assert len(teams) >= 10
    assert any("Chennai Super Kings" in t["team_name"] for t in teams)

def test_api_players_search(client):
    response = client.get("/players?search=Kohli")
    assert response.status_code == 200
    players = response.json()
    assert len(players) > 0
    assert any("Kohli" in p["player_name"] for p in players)

def test_api_chat_sql_route(client):
    payload = {"message": "Who scored the most runs in 2016?"}
    response = client.post("/chat", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["route"] == "SQL_ONLY"
    assert data["sql_data"] is not None
    assert any("Kohli" in row["player_name"] for row in data["sql_data"])
    assert data["session_id"] is not None

def test_api_chat_multi_turn(client):
    # Turn 1
    p1 = {"message": "Who scored the most runs in 2016?"}
    r1 = client.post("/chat", json=p1)
    assert r1.status_code == 200
    sess_id = r1.json()["session_id"]

    # Turn 2
    p2 = {"message": "How did he perform against CSK?", "session_id": sess_id}
    r2 = client.post("/chat", json=p2)
    assert r2.status_code == 200
    d2 = r2.json()
    assert "Kohli" in d2["transformed_query"]
    assert "Chennai Super Kings" in d2["transformed_query"]

def test_api_analytics_query(client):
    payload = {
        "intent": "HEAD_TO_HEAD",
        "team1": "Chennai Super Kings",
        "team2": "Mumbai Indians"
    }
    response = client.post("/analytics/query", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "HEAD_TO_HEAD"
    assert data["results"]["total_matches"] >= 35

def test_api_search(client):
    payload = {
        "query": "Powerplay fielding restrictions",
        "top_k": 3,
        "use_hybrid": True
    }
    response = client.post("/search", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["count"] > 0
    assert len(data["results"]) > 0

def test_api_evaluation_summary(client):
    response = client.get("/evaluation/summary")
    assert response.status_code == 200
    data = response.json()
    assert data["total_matches"] == 1241
    assert "Hybrid" in data["retrieval_architecture"]
