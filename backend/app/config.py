from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://govmap:govmap@localhost:5432/govmap"
    cors_origins: str = "http://localhost:3000"

    # Credentials for the /internal/* ops endpoints. Left empty by default,
    # which keeps those endpoints locked (every request 401s) until real
    # values are set — secure by default. See app/routers/pipeline_status.py.
    internal_user: str = ""
    internal_password: str = ""

    # Optional: POST target for pipeline-failure alerts (e.g. an ntfy.sh or
    # Slack incoming webhook). Unset = failures are logged only.
    alert_webhook_url: str = ""

    # Congress.gov API key — required for the bills/votes pipelines (Increment 3).
    congress_gov_api_key: str = ""
    # The Congress being tracked. Bump to 120 in Jan 2027 (env-overridable so a
    # redeploy, not a code change, rolls the number over).
    congress_number: int = 119
    # Per-run cap on how many most-recently-updated bills to pull+enrich. Keeps
    # each refresh well under the 5,000 req/hr key limit; raise to widen
    # coverage toward the full corpus.
    congress_gov_bill_limit: int = 250
    # Which session of the Congress (1 = first year, 2 = second) — builds the
    # House Clerk / Senate LIS roll-call URLs. 119th: 1=2025, 2=2026.
    congress_session: int = 2
    # Per-chamber cap on how many most-recent roll-call votes to pull.
    votes_limit: int = 100

    # OpenFEC (api.data.gov) key for campaign-finance totals (Increment 4).
    # Free key from https://api.data.gov/signup/. Empty = the finance pipeline
    # is skipped and records a non-fatal error, exactly like the bills pipeline
    # without a Congress.gov key. Sent as the X-Api-Key header, never a URL param.
    fec_api_key: str = ""
    # The FEC 2-year election cycle to pull totals for (even year). 119th
    # Congress → 2026; bump to 2028 in Jan 2027 (env-overridable, like
    # congress_number). Pulled in bulk per chamber, so it's a handful of calls.
    fec_cycle: int = 2026

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
