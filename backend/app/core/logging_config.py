"""Structured logging configuration with trace_id context."""

import json
import logging
import sys
from datetime import datetime
from typing import Any, Dict, Optional
from contextvars import ContextVar

# Context variable to store trace_id for the current request
trace_id_context: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)


class JSONFormatter(logging.Formatter):
    """Custom formatter that outputs structured JSON logs with trace_id context."""
    
    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record as JSON.
        Includes trace_id from context if available.
        """
        log_data: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Add trace_id from context or extra field
        trace_id = trace_id_context.get()
        if trace_id:
            log_data["trace_id"] = trace_id
        elif "trace_id" in record.__dict__:
            log_data["trace_id"] = record.__dict__["trace_id"]
        
        # Add extra fields from record.extra (passed via logger.info(..., extra={...}))
        if hasattr(record, "extra"):
            log_data.update(record.extra)
        
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        # Add module and line number for debugging
        log_data["location"] = f"{record.filename}:{record.lineno}"
        
        return json.dumps(log_data)


def setup_json_logging(log_level: str = "INFO"):
    """
    Configure structured JSON logging for entire application.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    # Remove existing handlers
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create console handler with JSON formatter
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, log_level))
    
    json_formatter = JSONFormatter()
    console_handler.setFormatter(json_formatter)
    
    # Configure root logger
    root_logger.setLevel(getattr(logging, log_level))
    root_logger.addHandler(console_handler)
    
    # Suppress noisy third-party loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("redis").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)


def set_trace_id(trace_id: Optional[str]):
    """
    Set trace_id for current request context.
    Called by middleware to propagate trace_id to all logs in the request.
    """
    trace_id_context.set(trace_id)


def get_trace_id() -> Optional[str]:
    """Get trace_id from current context."""
    return trace_id_context.get()
