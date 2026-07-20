"""Application settings via pydantic-settings. Every knob lives here."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    wire_env: str = "dev"
    # Lite mode by default: SQLite file + no Redis = zero-infra. Set a
    # postgresql+asyncpg URL and a redis URL for the scale path.
    database_url: str = "sqlite+aiosqlite:///./wire.db"
    redis_url: str = ""
    # Run beat-style background loops inside the API process. On when Redis
    # is absent; the docker-compose scale path sets EMBEDDED_WORKER=0 and
    # runs Celery instead.
    embedded_worker: bool = True
    secret_key: str = "dev-secret-change-me"
    api_base_url: str = "http://localhost:8000"

    # provider keys (platform tier — ALL optional; users can instead paste
    # their own keys in the Studio engine panel, browser-side only)
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    google_api_key: str = ""      # Gemini: free tier for text AND embeddings
    groq_api_key: str = ""        # free tier, fast — the recommended first key
    openrouter_api_key: str = ""  # gives access to many :free models
    deepseek_api_key: str = ""
    mistral_api_key: str = ""
    xai_api_key: str = ""
    fal_key: str = ""
    deepgram_api_key: str = ""

    # ingestion
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_user_agent: str = "wire/0.1"
    youtube_api_key: str = ""
    youtube_daily_quota_units: int = 10_000
    newsdata_api_key: str = ""
    gnews_api_key: str = ""
    mediastack_api_key: str = ""
    news_api_vendor: str = "newsdata"

    # billing
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_pro: str = ""
    stripe_price_byok: str = ""
    byok_master_key: str = ""

    # publishing
    publish_vendor: str = "ayrshare"
    ayrshare_api_key: str = ""
    publish_webhook_secret: str = ""

    # storage
    s3_endpoint_url: str = ""
    s3_bucket: str = "wire-artifacts"
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_region: str = "auto"

    # local GPU mode
    local_mode: bool = Field(default=False, alias="LOCAL_MODE")
    ollama_base_url: str = "http://localhost:11434"
    comfyui_base_url: str = "http://localhost:8188"

    # corpus tuning
    cluster_similarity_threshold: float = 0.86
    cluster_window_hours: int = 72
    briefing_expiry_hours: int = 48
    briefing_regen_growth: float = 0.40
    embed_batch_size: int = 64

    # ranking weights
    rank_w_interest: float = 0.45
    rank_w_source: float = 0.25
    rank_w_recency: float = 0.20
    rank_w_diversity: float = 0.10
    recency_half_life_hours: float = 8.0
    max_per_domain_per_day: int = 3
    feed_size_paid: int = 50
    feed_size_free: int = 20

    # learning rates
    lr_swipe_right: float = 0.08
    lr_swipe_left: float = 0.03
    lr_dwell: float = 0.01
    dwell_threshold_ms: int = 4000

    # trace retention
    trace_full_payload_days: int = 7


@lru_cache
def get_settings() -> Settings:
    return Settings()
