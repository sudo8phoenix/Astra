from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # =====================================================================
    # APPLICATION SETTINGS
    # =====================================================================
    app_name: str = "AI Personal Assistant API"
    app_env: str = "development"
    app_debug: bool = True
    api_prefix: str = "/api"
    api_version: str = "v1"
    allowed_origins: list[str] = ["*"]

    # =====================================================================
    # SERVER SETTINGS
    # =====================================================================
    host: str = "0.0.0.0"
    port: int = 8000
    reload: bool = True
    workers: int = 4

    # =====================================================================
    # DATABASE SETTINGS
    # =====================================================================
    database_url: str = "postgresql://user:password@localhost:5432/ai_assistant_dev"
    database_async_url: str = "postgresql+asyncpg://user:password@localhost:5432/ai_assistant_dev"
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_recycle: int = 3600
    db_echo: bool = False

    # =====================================================================
    # REDIS SETTINGS
    # =====================================================================
    redis_url: str = "redis://localhost:6379/0"
    redis_cache_url: str = "redis://localhost:6379/1"
    redis_session_ttl: int = 3600
    redis_cache_ttl: int = 1800

    # =====================================================================
    # JWT & AUTHENTICATION SETTINGS
    # =====================================================================
    jwt_secret_key: str = "your-very-secure-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiration_hours: int = 24
    jwt_refresh_expiration_days: int = 7

    # =====================================================================
    # OAUTH 2.0 SETTINGS
    # =====================================================================
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    google_oauth_redirect_uri: str = "http://localhost:8000/api/v1/auth/google/callback"

    github_oauth_client_id: str = ""
    github_oauth_client_secret: str = ""
    github_oauth_redirect_uri: str = "http://localhost:8000/api/v1/auth/github/callback"

    frontend_url: str = "http://localhost:3000"

    # =====================================================================
    # LLM SETTINGS
    # =====================================================================
    groq_api_key: str = ""
    groq_planner_model: str = "llama-3.3-70b-versatile"
    groq_execution_model: str = "llama-3.1-8b-instant"
    llm_temperature: float = 0.7
    llm_max_tokens: int = 2048
    llm_daily_token_limit: int = 1000000
    llm_cost_threshold_cents: int = 500
    llm_input_cost_per_1k_tokens_usd: float = 0.0005
    llm_output_cost_per_1k_tokens_usd: float = 0.0015

    # =====================================================================
    # EXTERNAL API SETTINGS
    # =====================================================================
    gmail_api_scopes: str = "https://www.googleapis.com/auth/gmail.readonly,https://www.googleapis.com/auth/gmail.send"
    gmail_max_results: int = 10

    calendar_api_scopes: str = "https://www.googleapis.com/auth/calendar.readonly,https://www.googleapis.com/auth/calendar.events"

    whatsapp_business_api_key: str = ""
    whatsapp_business_phone_id: str = ""

    openweather_api_key: str = ""

    # =====================================================================
    # LOGGING SETTINGS
    # =====================================================================
    log_level: str = "INFO"
    log_format: str = "json"
    log_output: str = "stdout,file"
    log_file_path: str = "./logs/app.log"
    log_file_max_bytes: int = 10485760
    log_file_backup_count: int = 5

    # =====================================================================
    # OBSERVABILITY SETTINGS
    # =====================================================================
    sentry_dsn: str = ""
    sentry_environment: str = "development"
    datadog_enabled: bool = False
    datadog_service_name: str = "ai-assistant-api"
    datadog_env: str = "development"
    metrics_enabled: bool = True
    metrics_port: int = 8001

    # =====================================================================
    # AUDIT SETTINGS
    # =====================================================================
    audit_log_enabled: bool = True
    audit_log_table: str = "audit_logs"
    audit_log_level: str = "info"

    # =====================================================================
    # FEATURE FLAGS
    # =====================================================================
    feature_email_management: bool = True
    feature_calendar_management: bool = True
    feature_task_management: bool = True
    feature_whatsapp_integration: bool = False

    # =====================================================================
    # EMAIL SETTINGS (for system notifications)
    # =====================================================================
    smtp_server: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    system_email: str = "noreply@ai-assistant.local"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def debug(self) -> bool:
        """Backward-compatible alias used by existing middleware."""
        return self.app_debug


settings = Settings()
