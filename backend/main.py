import time
from pathlib import Path
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "backend"))
sys.path.insert(0, str(PROJECT_ROOT / "analytics"))
sys.path.insert(0, str(PROJECT_ROOT / "rag"))
sys.path.insert(0, str(PROJECT_ROOT / "database"))
sys.path.insert(0, str(PROJECT_ROOT / "utils"))

from routes import router
from logger import get_logger, set_request_id, get_request_id

logger = get_logger("ipl_intelligence_api")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting IPL Intelligence API server...")
    yield
    # Shutdown
    try:
        from database.connection import DatabaseManager
        DatabaseManager.close_pool()
        logger.info("Application shutdown: database pool closed.")
    except Exception as e:
        logger.error(f"Error closing database pool on shutdown: {e}")

app = FastAPI(
    title="IPL Intelligence Platform API",
    description="Production-style Conversational Cricket Analytics Platform using Hybrid RAG, PostgreSQL, and LLMs",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# CORS middleware for Streamlit and web frontends
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request latency, ID tracing, and structured logging middleware
@app.middleware("http")
async def add_process_time_and_logging(request: Request, call_next):
    client_req_id = request.headers.get("X-Request-ID")
    req_id = set_request_id(client_req_id)
    start_time = time.time()
    try:
        response = await call_next(request)
        process_time = time.time() - start_time
        response.headers["X-Request-ID"] = req_id
        response.headers["X-Process-Time"] = f"{process_time:.4f}s"
        logger.info(f"{request.method} {request.url.path} completed in {process_time:.4f}s [Status: {response.status_code}]")
        return response
    except Exception as exc:
        process_time = time.time() - start_time
        logger.error(f"{request.method} {request.url.path} failed after {process_time:.4f}s: {exc}")
        return JSONResponse(
            status_code=500,
            content={"detail": f"Internal Server Error: {str(exc)}"},
            headers={"X-Request-ID": req_id, "X-Process-Time": f"{process_time:.4f}s"}
        )

# Root endpoint
@app.get("/")
def root():
    return {
        "title": "IPL Intelligence: Conversational Cricket Analytics Platform API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
        "chat": "/chat"
    }

# Include API routes
app.include_router(router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
