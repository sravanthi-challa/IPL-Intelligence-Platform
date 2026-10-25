import logging
import json
import time
import uuid
import contextvars
from typing import Optional, Any, Callable
from functools import wraps

# Context variable for distributed request tracing
request_id_ctx = contextvars.ContextVar("request_id", default=None)

def set_request_id(req_id: Optional[str] = None) -> str:
    rid = req_id or str(uuid.uuid4())
    request_id_ctx.set(rid)
    return rid

def get_request_id() -> Optional[str]:
    return request_id_ctx.get()

class StructuredFormatter(logging.Formatter):
    """
    Format logs with timestamp, log level, logger name, and contextual request ID.
    Supports JSON output format when configured.
    """
    def __init__(self, json_mode: bool = False):
        super().__init__()
        self.json_mode = json_mode

    def format(self, record: logging.LogRecord) -> str:
        req_id = get_request_id() or "-"
        if self.json_mode:
            log_data = {
                "timestamp": self.formatTime(record, self.datefmt),
                "level": record.levelname,
                "logger": record.name,
                "request_id": req_id,
                "message": record.getMessage()
            }
            if record.exc_info:
                log_data["exception"] = self.formatException(record.exc_info)
            return json.dumps(log_data)
        else:
            time_str = self.formatTime(record, "%Y-%m-%d %H:%M:%S")
            exc_text = ""
            if record.exc_info:
                exc_text = "\n" + self.formatException(record.exc_info)
            return f"{time_str} [{record.levelname:<7}] [{req_id}] {record.name}: {record.getMessage()}{exc_text}"

def get_logger(name: str) -> logging.Logger:
    """Returns a logger with structured formatters configured."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        from config import AppConfig
        json_mode = (AppConfig.LOG_FORMAT == "JSON")
        handler.setFormatter(StructuredFormatter(json_mode=json_mode))
        logger.addHandler(handler)
        logger.setLevel(getattr(logging, AppConfig.LOG_LEVEL, logging.INFO))
    return logger

class LatencyTracker:
    """Context manager to measure and trace operation latency."""
    def __init__(self, operation_name: str, logger: Optional[logging.Logger] = None, slow_threshold_ms: float = 500.0):
        self.operation_name = operation_name
        self.logger = logger or get_logger("latency_tracer")
        self.slow_threshold_ms = slow_threshold_ms
        self.elapsed_ms = 0.0

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.elapsed_ms = (time.time() - self.start_time) * 1000.0
        if exc_type is not None:
            self.logger.error(f"{self.operation_name} FAILED after {self.elapsed_ms:.2f}ms: {exc_val}")
        elif self.elapsed_ms >= self.slow_threshold_ms:
            self.logger.warning(f"SLOW OPERATION: {self.operation_name} took {self.elapsed_ms:.2f}ms (threshold: {self.slow_threshold_ms}ms)")
        else:
            self.logger.debug(f"{self.operation_name} completed in {self.elapsed_ms:.2f}ms")
