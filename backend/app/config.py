"""Runtime configuration, read from environment variables (and backend/.env)."""
from __future__ import annotations

from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(BACKEND_DIR / ".env"), extra="ignore")

    database_url: str = "postgresql://localhost:5432/trialmatch"

    # OpenRouter (OpenAI-compatible). Free models are tried in order; OpenRouter
    # falls through the list when one is rate limited or unavailable.
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    llm_models: List[str] = [
        "nvidia/nemotron-3.5-super-vl:free",
        "xingchen-agi/xing4.0-29b-a4b:free",
        "google/gemma-4-31b-it:free",
    ]
    # Free tier allows 50 requests/day; keep headroom for interactive "explain" calls.
    llm_daily_budget: int = 40

    # Embeddings: "auto" uses fastembed (bge-small) if installed, else local LSA.
    embedding_provider: str = "auto"
    embedding_dim: int = 384

    # Ingestion
    ingest_conditions: List[str] = [
        "breast cancer", "lung cancer", "prostate cancer", "colorectal cancer",
        "melanoma", "leukemia", "lymphoma", "pancreatic cancer",
        "type 2 diabetes", "type 1 diabetes", "obesity", "heart failure",
        "hypertension", "asthma", "COPD", "alzheimer disease", "parkinson disease",
        "multiple sclerosis", "depression", "rheumatoid arthritis", "crohn disease",
        "chronic kidney disease", "HIV", "long covid", "migraine", "sickle cell disease",
    ]
    ingest_per_condition: int = 120
    ingest_interval_hours: float = 24.0

    cors_origins: List[str] = ["http://localhost:3000"]
    # When set, saving annotations requires this value in the X-Annotate-Token header.
    annotate_token: str = ""
    artifacts_dir: Path = BACKEND_DIR / "artifacts"
    gold_dir: Path = BACKEND_DIR / "data" / "gold"


settings = Settings()
