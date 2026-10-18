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
    gemini_model: str = "gemini-3.8-flash"
    gemini_api_key: str = ""
    environment: str = "development"
    release: str = "hackathon"
    sentry_dsn: str = ""
    agent_seed: str = ""
    agentverse_api_key: str = ""
    agent_public_endpoint: str = ""
    agent_port: int = 8001
    internal_api_url: str = "http://127.0.0.1:8000"
    customer_agent_endpoint: str = "http://127.0.0.1:8001/submit"
    photon_owner_handle: str = ""
    photon_project_id: str = ""
    photon_sms_sender_id: str = ""
    photon_email_sender_id: str = ""
    photon_demo_recipient: str = ""
    photon_webhook_token: str = ""
    photon_api_key: str = ""
    planner: str = "gemini"            # gemini | jev
    finance_tools: str = "owed_model"  # owed_model | jev
    # pay rails (docs/devin/task-1-pay-page.md)
    visa_user_id: str = ""
    visa_password: str = ""
    visa_cert_path: str = ""
    visa_key_path: str = ""
    visa_acquiring_bin: str = "408999"
    solana_rpc_url: str = "https://api.devnet.solana.com"
    solana_recipient: str = ""
    solana_usdc_mint: str = "4zMMC9srt5Ri5X14GAgXhaHii3GnPAEERYPJgZJDncDU"


settings = Settings()
