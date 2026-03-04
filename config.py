from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def load_env_file(file_path: str = ".env") -> None:
    env_path = Path(file_path)
    if not env_path.exists() or not env_path.is_file():
        return

    for raw_line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")

        if key and key not in os.environ:
            os.environ[key] = value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore", case_sensitive=False)

    app_name: str = "5-Agent Workflow API"
    app_version: str = "1.1.0"
    app_host: str = Field(default="127.0.0.1", alias="APP_HOST")
    app_port: int = Field(default=8003, alias="APP_PORT")

    default_file_root: str = Field(default=".", alias="DEFAULT_FILE_ROOT")
    max_iterations_default: int = Field(default=8, alias="MAX_ITERATIONS")

    planner_model: str = Field(default="llama-3.3-70b-versatile", alias="PLANNER_MODEL")
    router_model: str = Field(default="llama-3.1-8b-instant", alias="ROUTER_MODEL")
    executor_model: str = Field(default="llama-3.1-8b-instant", alias="EXECUTOR_MODEL")
    evaluator_model: str = Field(default="llama-3.3-70b-versatile", alias="EVALUATOR_MODEL")

    groq_api_key: str | None = Field(default=None, alias="GROQ_API_KEY")
    serpapi_api_key: str | None = Field(default=None, alias="SERPAPI_API_KEY")

    groq_max_retries: int = Field(default=3, alias="GROQ_MAX_RETRIES")
    groq_retry_base_delay_seconds: float = Field(default=0.6, alias="GROQ_RETRY_BASE_DELAY_SECONDS")
    groq_retry_max_delay_seconds: float = Field(default=6.0, alias="GROQ_RETRY_MAX_DELAY_SECONDS")

    memory_recent_chat_limit: int = Field(default=30, alias="MEMORY_RECENT_CHAT_LIMIT")
    memory_retrieval_k: int = Field(default=6, alias="MEMORY_RETRIEVAL_K")

    python_exec_timeout_seconds: int = Field(default=4, alias="PYTHON_EXEC_TIMEOUT_SECONDS")
    python_exec_max_output_chars: int = Field(default=12000, alias="PYTHON_EXEC_MAX_OUTPUT_CHARS")
    python_exec_sandbox_mode: str = Field(default="subprocess", alias="PYTHON_EXEC_SANDBOX_MODE")
    python_exec_docker_image: str = Field(default="python:3.11-alpine", alias="PYTHON_EXEC_DOCKER_IMAGE")
    python_exec_docker_memory: str = Field(default="256m", alias="PYTHON_EXEC_DOCKER_MEMORY")

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_env_file()
    return Settings()


def setup_logging(level: str | None = None) -> None:
    settings = get_settings()
    chosen_level = (level or settings.log_level or "INFO").upper()
    numeric_level = getattr(logging, chosen_level, logging.INFO)

    root_logger = logging.getLogger()
    if not root_logger.handlers:
        logging.basicConfig(
            level=numeric_level,
            format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        )
    else:
        root_logger.setLevel(numeric_level)
