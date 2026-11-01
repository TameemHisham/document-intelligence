from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    data_dir: Path = Path("data")
    database_url: str = ""  # defaults to sqlite inside data_dir

    # Auth
    jwt_secret: str = "dev-secret-change-me-in-production-please"
    jwt_ttl_hours: int = 24 * 7
    file_token_ttl_minutes: int = 60
    google_client_id: str = ""
    dev_auth: bool = False  # enables POST /auth/dev (local testing without Google)
    frontend_origin: str = "http://localhost:3000"

    # Backends: local dev defaults vs. cloud (Cloud Run + Cloud SQL + Pub/Sub)
    vector_backend: Literal["faiss", "pgvector"] = "faiss"
    task_backend: Literal["background", "pubsub"] = "background"
    gcp_project: str = ""
    gcp_location: str = "us-central1"
    pubsub_topic: str = "ingest"
    pubsub_push_audience: str = ""  # worker URL; when set, push requests must carry a Google OIDC token
    pubsub_push_sa_email: str = ""  # ...issued to this service account

    # Gemini: natural-language search -> structured filters (falls back to local rules)
    gemini_api_key: str = ""
    gemini_use_vertex: bool = False  # on GCP: Vertex AI via the service account, no key
    gemini_model: str = "gemini-2.5-flash-lite"

    # Category grouping
    group_name_similarity: float = 0.8  # SBERT cosine for "Gym notes" ~ "Workout notes"
    merge_centroid_similarity: float = 0.92  # CLIP centroid cosine for categories with similar photos

    # Storage / OCR
    storage_backend: Literal["local", "gcs"] = "local"
    gcs_bucket: str = ""
    ocr_backend: Literal["vision", "none"] = "vision"
    max_upload_mb: int = 20

    # Claude
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-5-5"
    claude_timeout_s: float = 60.0
    claude_max_retries: int = 1
    describe_max_tokens: int = 1000
    ask_max_tokens: int = 1500
    claude_image_max_side: int = 1092  # ~1.6k input tokens per image

    # Cost guards (hard caps, checked before every paid call)
    monthly_budget_usd: float = 5.0  # all users, Claude + Vision
    user_daily_budget_usd: float = 1.0
    ocr_monthly_limit: int = 900  # Google Vision: first 1,000 images/month free

    # Abuse limits
    max_files_per_request: int = 10
    max_uploads_per_day: int = 100
    max_documents_per_user: int = 2000
    max_image_pixels: int = 50_000_000
    rate_ask_per_minute: int = 10
    rate_search_per_minute: int = 60
    rate_upload_per_minute: int = 30  # requests; the UI sends batches of up to 5 files
    rate_reprocess_per_minute: int = 5

    # Models
    fake_models: bool = False  # deterministic hash embeddings, no downloads (tests / quick debugging)
    text_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    clip_model: str = "sentence-transformers/clip-ViT-B-32"
    spacy_model: str = "en_core_web_sm"

    # Retrieval
    chunk_max_words: int = 120
    chunk_overlap_sentences: int = 1
    text_min_score: float = 0.25
    image_min_score: float = 0.21
    image_relative_margin: float = 0.03
    classifier_min_examples: int = 3

    @field_validator("anthropic_api_key", "gemini_api_key")
    @classmethod
    def _placeholder_means_unset(cls, v: str) -> str:
        return "" if v.strip().startswith("REPLACE_ME") else v.strip()

    @property
    def db_url(self) -> str:
        return self.database_url or f"sqlite:///{self.data_dir / 'app.db'}"


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.data_dir.mkdir(parents=True, exist_ok=True)
    return s
