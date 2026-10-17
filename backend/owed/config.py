from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    scoring_interval_ms: int = 50
    database_url: str = "postgresql://owed:owed@localhost:5433/owed"
    data_dir: str = "../data/raw/hackathon-100"
    demo_company: str = "company-020"
    gemini_api_key: str = ""
    sentry_dsn: str = ""
    photon_api_key: str = ""
    planner: str = "gemini"            # gemini | jev
    finance_tools: str = "owed_model"  # owed_model | jev


settings = Settings()
