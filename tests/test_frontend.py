import pytest
import py_compile
from pathlib import Path

import sys
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "analytics"))
sys.path.insert(0, str(PROJECT_ROOT / "rag"))

def test_frontend_compilation():
    app_path = PROJECT_ROOT / "frontend" / "app.py"
    assert app_path.exists(), "frontend/app.py must exist"
    # Ensure no python syntax errors
    py_compile.compile(str(app_path), doraise=True)

def test_frontend_importable_components():
    # Verify core components required by the UI are available
    from metrics import CricketAnalytics
    from rag.orchestrator import ConversationalOrchestrator
    
    analytics = CricketAnalytics()
    orchestrator = ConversationalOrchestrator()
    assert analytics is not None
    assert orchestrator is not None
