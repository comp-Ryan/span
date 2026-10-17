from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://owed:owed@localhost:5433/owed"
    data_dir: str = "../data/raw/hackathon-100"
    demo_company: str = "company-001"
    gemini_api_key: str = ""
    sentry_dsn: str = ""
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
