from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.schemas.domain import RiskLevel

_BASE_DIR = Path(__file__).resolve().parent.parent.parent
_ENV_FILE = _BASE_DIR / ".env"
_DEFAULT_DB_FILE = (_BASE_DIR / "fleet_studio.db").as_posix()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE) if _ENV_FILE.exists() else ".env",
        env_prefix="FLEET_STUDIO_",
        extra="ignore",
    )

    database_url: str = f"sqlite+aiosqlite:///{_DEFAULT_DB_FILE}"
    auth_required: bool = False
    session_secret: str = "local-development-only-change-me"
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_metadata_url: str = ""
    oidc_redirect_uri: str = "http://localhost:8000/auth/callback"
    oidc_roles_claim: str = "roles"
    hermes_base_url: str = "http://127.0.0.1:9119"
    hermes_api_token: str = ""
    hermes_loopback_bridge_enabled: bool = False
    hermes_tool_risk_overrides: dict[str, RiskLevel] = Field(default_factory=dict)
    hermes_hooks_enabled: bool = False
    hermes_cycle_timeout_seconds: int = 600
    hermes_home: str = ""
    max_hermes_profiles: int = 25
    llm_base_url: str = ""
    llm_model: str = "qwen/qwen3.8-27b"
    llm_timeout_seconds: float = 15.0
    daemon_token: str = ""
    webhook_secret: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_sender: str = ""
    smtp_username: str = ""
    smtp_password: str = ""
    output_webhook_url: str = ""
    output_webhook_token: str = ""
    otel_exporter_otlp_endpoint: str = ""
    otel_exporter_otlp_headers: dict[str, str] = Field(default_factory=dict)
    frontend_origin: str = "http://localhost:3000"


settings = Settings()
