import os
from pathlib import Path
from typing import Dict, Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent

# Automatically load .env file if present
ENV_FILE = PROJECT_ROOT / ".env"
if ENV_FILE.exists():
    with open(ENV_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip("\"'")
                if key not in os.environ:
                    os.environ[key] = val

class AppConfig:
    """
    Centralized configuration with validation, safe secret masking,
    and enterprise governance defaults.
    """
    # Database Settings
    DB_HOST: str = os.environ.get("DB_HOST", "localhost")
    DB_PORT: int = int(os.environ.get("DB_PORT", 5432))
    DB_NAME: str = os.environ.get("DB_NAME", "cricket_intelligence")
    DB_USER: str = os.environ.get("DB_USER", "postgres")
    DB_PASSWORD: str = os.environ.get("DB_PASSWORD", "")
    
    # Database Security & Governance
    STATEMENT_TIMEOUT_MS: int = int(os.environ.get("DB_STATEMENT_TIMEOUT_MS", 5000))  # 5s max execution
    DB_POOL_MIN: int = int(os.environ.get("DB_POOL_MIN", 1))
    DB_POOL_MAX: int = int(os.environ.get("DB_POOL_MAX", 10))
    MAX_ROWS_LIMIT: int = int(os.environ.get("MAX_ROWS_LIMIT", 1000))                 # Max rows returned per analytical query
    
    # LLM Settings
    LLM_PROVIDER: str = os.environ.get("LLM_PROVIDER", "openai").lower()
    LLM_MODEL: str = os.environ.get("LLM_MODEL", "gpt-4o-mini")
    OPENAI_API_KEY: Optional[str] = os.environ.get("OPENAI_API_KEY") or os.environ.get("LLM_API_KEY")
    LLM_TEMPERATURE: float = float(os.environ.get("LLM_TEMPERATURE", 0.0))
    LLM_MAX_TOKENS: int = int(os.environ.get("LLM_MAX_TOKENS", 1024))

    # Retrieval & Vector Settings
    EMBEDDING_PROVIDER: str = os.environ.get("EMBEDDING_PROVIDER", "openai").lower()
    EMBEDDING_MODEL: str = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")
    VECTOR_DIMENSIONS: int = int(os.environ.get("VECTOR_DIMENSIONS", 384))
    TOP_K: int = int(os.environ.get("TOP_K", 5))
    RERANKER_ENABLED: bool = os.environ.get("RERANKER_ENABLED", "true").lower() in ("true", "1", "yes")

    # Observability
    LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO").upper()
    LOG_FORMAT: str = os.environ.get("LOG_FORMAT", "TEXT").upper() # 'TEXT' or 'JSON'

    @classmethod
    def get_db_dict(cls) -> Dict[str, Any]:
        """Returns connection dictionary for psycopg2."""
        return {
            "host": cls.DB_HOST,
            "port": cls.DB_PORT,
            "dbname": cls.DB_NAME,
            "user": cls.DB_USER,
            "password": cls.DB_PASSWORD,
        }

    @classmethod
    def get_safe_summary(cls) -> Dict[str, Any]:
        """Returns non-sensitive configuration representation with redacted credentials."""
        return {
            "db_host": cls.DB_HOST,
            "db_port": cls.DB_PORT,
            "db_name": cls.DB_NAME,
            "db_user": cls.DB_USER,
            "db_password_set": bool(cls.DB_PASSWORD),
            "statement_timeout_ms": cls.STATEMENT_TIMEOUT_MS,
            "db_pool_limits": f"{cls.DB_POOL_MIN}-{cls.DB_POOL_MAX}",
            "max_rows_limit": cls.MAX_ROWS_LIMIT,
            "llm_provider": cls.LLM_PROVIDER,
            "llm_model": cls.LLM_MODEL,
            "api_key_set": bool(cls.OPENAI_API_KEY),
            "embedding_provider": cls.EMBEDDING_PROVIDER,
            "vector_dimensions": cls.VECTOR_DIMENSIONS,
            "top_k": cls.TOP_K,
            "reranker_enabled": cls.RERANKER_ENABLED,
            "log_level": cls.LOG_LEVEL
        }

    @classmethod
    def validate(cls) -> bool:
        """Validates critical system parameters."""
        assert cls.DB_PORT > 0 and cls.DB_PORT < 65536, "Invalid DB port"
        assert cls.STATEMENT_TIMEOUT_MS >= 100, "Statement timeout must be at least 100ms"
        assert cls.MAX_ROWS_LIMIT >= 1, "Max rows limit must be positive"
        assert cls.DB_POOL_MIN >= 1, "DB pool minimum must be at least 1"
        assert cls.DB_POOL_MAX >= cls.DB_POOL_MIN, "DB pool maximum must be >= minimum"
        return True

# Validate immediately upon module import
AppConfig.validate()
