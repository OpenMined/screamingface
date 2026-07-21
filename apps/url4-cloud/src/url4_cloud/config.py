"""url4-cloud application settings (env-prefixed ``URL4_CLOUD_``)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration; overridable via ``URL4_CLOUD_*`` env vars."""

    model_config = SettingsConfigDict(env_prefix="URL4_CLOUD_")

    # WHY: HS256 signing secret for the JWT topic-capability token (spec §4). Never logged.
    jwt_secret: str = "dev-insecure-change-me"
    nats_url: str = "nats://localhost:4222"
    # INVARIANT: stateless iat window (seconds) — start rejected when now - iat exceeds it (§4).
    iat_window_s: int = 60
    # WHY: sync-hold cap; a run outliving it degrades to 202 async (spec §5).
    sync_max_wait_s: float = 30.0
    # INVARIANT: k8s Job activeDeadlineSeconds ceiling = 16h (spec §3).
    job_deadline_s: int = 57600
