from __future__ import annotations
from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    vault_path: Path
    api_key: str
    port: int = 8083
    backwater_url: str = "http://localhost:8080"
    tz: str = "UTC"
    flat: bool = True

    model_config = {"env_prefix": "BLACKGLASS_"}


settings = Settings()
