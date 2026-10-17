from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    scoring_interval_ms: int = 50
    database_url: str = "postgresql://owed:owed@localhost:5433/owed"
    data_dir: str = "../data/raw/hackathon-100"
    demo_company: str = "company-020"
    public_base_url: str = "http://localhost:8000"
    gemini_live_model: str = "gemini-3.8-live"
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = ""
    voice_stream_token: str = ""
    twilio_auth_token: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_api_key: str = ""
    sentry_dsn: str = ""
    photon_api_key: str = ""
    planner: str = "gemini"            # gemini | jev
    finance_tools: str = "owed_model"  # owed_model | jev


settings = Settings()
