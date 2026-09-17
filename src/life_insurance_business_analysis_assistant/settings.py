from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    deepseek_api_key: str | None = os.getenv("DEEPSEEK_API_KEY")
    deepseek_base_url: str | None = os.getenv("DEEPSEEK_BASE_URL")
    deepseek_model: str = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
    deepseek_model_provider: str = os.getenv("DEEPSEEK_MODEL_PROVIDER", "deepseek")
    backend_base_url: str = os.getenv("BACKEND_BASE_URL", "http://localhost:8080")


settings = Settings()
