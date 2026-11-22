from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://timemachine:local-development-only@localhost:5434/timemachine"
    allowed_target_origins: str = "http://sample-api:8001,http://sample-api-v2:8001"
    dev_private_origins: str = "http://sample-api:8001,http://sample-api-v2:8001"
    dev_private_cidrs: str = "10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"
    cors_origins: str = "http://localhost:5175,http://127.0.0.1:5175,http://localhost:8002,http://127.0.0.1:8002"
    trusted_hosts: str = "localhost,127.0.0.1,backend,testserver"
    redact_fields: str = ""
    connect_timeout_seconds: float = Field(default=3, gt=0, le=30)
    read_timeout_seconds: float = Field(default=10, gt=0, le=120)
    total_timeout_seconds: float = Field(default=20, gt=0, le=180)
    max_response_bytes: int = Field(default=1_048_576, ge=1024, le=10_485_760)
    max_request_bytes: int = Field(default=262_144, ge=1024, le=1_048_576)
    max_concurrent_requests: int = Field(default=8, ge=1, le=64)
    max_executions_per_minute: int = Field(default=120, ge=1, le=10000)
    sample_v1_base_url: str = "http://sample-api:8001"
    sample_v2_base_url: str = "http://sample-api-v2:8001"

    replay_max_batch_size: int = Field(default=10, ge=1, le=25)
    replay_session_timeout_seconds: float = Field(default=120, gt=0, le=300)
    replay_max_concurrent_sessions: int = Field(default=2, ge=1, le=8)
    recover_replays_on_startup: bool = True

    @staticmethod
    def csv(value: str) -> list[str]:
        return [part.strip() for part in value.split(",") if part.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
