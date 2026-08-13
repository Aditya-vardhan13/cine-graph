from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Cinegraph Explorer API"
    environment: str = "development"
    database_url: str = "sqlite:///./cinegraph.db"
    api_cors_origins: str = "http://localhost:3000"
    wikidata_user_agent: str = "CineGraphExplorer/0.1 (https://github.com/Aditya-vardhan13/cine-graph)"
    raw_snapshot_root: str = "./data/raw-snapshots"
    source_request_interval_seconds: float = 1.0

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.api_cors_origins.split(",") if origin.strip()]

    @property
    def source_requests_per_minute(self) -> int:
        """A conservative sequential ceiling below Wikimedia's 200 rpm limit."""
        if not 0.5 <= self.source_request_interval_seconds <= 1.0:
            raise ValueError("source_request_interval_seconds must stay between 0.5 and 1.0 seconds.")
        return int(60 / self.source_request_interval_seconds)


@lru_cache
def get_settings() -> Settings:
    return Settings()
