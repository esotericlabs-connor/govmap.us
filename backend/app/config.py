from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://govmap:govmap@localhost:5432/govmap"
    cors_origins: str = "http://localhost:3000"

    # Credentials for the /internal/* ops endpoints. Left empty by default,
    # which keeps those endpoints locked (every request 401s) until real
    # values are set — secure by default. See app/routers/pipeline_status.py.
    internal_user: str = ""
    internal_password: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
