import pytest
import sys
from pathlib import Path
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "database"))
sys.path.insert(0, str(PROJECT_ROOT / "utils"))
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from config import AppConfig
from logger import get_logger, set_request_id, get_request_id, LatencyTracker
from connection import get_db_connection, execute_query, DatabaseManager
from main import app

def test_app_config_validation():
    assert AppConfig.validate() is True
    summary = AppConfig.get_safe_summary()
    assert summary["db_name"] == "cricket_intelligence"
    assert "db_password_set" in summary
    assert "password" not in summary  # Password must not be leaked
    assert summary["statement_timeout_ms"] >= 100
    assert summary["max_rows_limit"] >= 1

def test_logger_and_request_id_context():
    test_id = "test-req-12345"
    set_request_id(test_id)
    assert get_request_id() == test_id
    
    logger = get_logger("test_observability")
    logger.info("Structured logging test message")
    
    # Latency tracker
    with LatencyTracker("test_operation", logger=logger, slow_threshold_ms=10.0) as tracker:
        pass
    assert tracker.elapsed_ms >= 0.0

def test_db_connection_pooling_and_timeout_setting():
    pool = DatabaseManager.get_pool()
    assert pool is not None
    
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SHOW statement_timeout;")
            val = cur.fetchone()[0]
            # Verify statement_timeout is configured (e.g. '5s' or '5000ms')
            assert "5" in val or "ms" in val or "s" in val

def test_db_read_only_security_guard():
    # Write statements must be rejected by execute_query read_only guard
    with pytest.raises(ValueError, match="Security Alert: Prohibited write verb 'DROP'"):
        execute_query("DROP TABLE dummy_test;")
        
    with pytest.raises(ValueError, match="Security Alert: Prohibited write verb 'DELETE'"):
        execute_query("DELETE FROM fact_matches;")

def test_db_query_row_limiting():
    # Query with max_rows constraint
    rows = execute_query("SELECT match_id FROM fact_matches;", max_rows=5)
    assert len(rows) == 5

def test_fastapi_request_id_and_process_time_headers():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert "X-Request-ID" in response.headers
    assert "X-Process-Time" in response.headers
    assert response.headers["X-Request-ID"] is not None
    
    # Custom client-supplied Request ID
    custom_id = "client-trace-abc-999"
    response_custom = client.get("/health", headers={"X-Request-ID": custom_id})
    assert response_custom.status_code == 200
    assert response_custom.headers["X-Request-ID"] == custom_id
