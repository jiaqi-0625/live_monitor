from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "汽车直播智能辅助工具"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    database_path: Path = Path("./storage/live-monitor.db")
    storage_root: Path = Path("./storage")
    web_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    asr_provider: str = "mock"
    aliyun_nls_appkey: str | None = None
    aliyun_access_key_id: SecretStr | None = None
    aliyun_access_key_secret: SecretStr | None = None
    aliyun_nls_region_id: str = "cn-shanghai"
    aliyun_nls_websocket_url: str = "wss://nls-gateway.cn-shanghai.aliyuncs.com/ws/v1"
    aliyun_nls_vocabulary_id: str | None = None
    autoengine_cookie: SecretStr | None = None
    llm_api_base: str = "https://api.deepseek.com"
    llm_api_key: SecretStr | None = None
    llm_model: str = "deepseek-chat"
    llm_analysis_interval_seconds: int = 60
    app_config_encryption_key: SecretStr | None = None
    auth_required: bool = True
    auth_session_days: int = 14
    auth_cookie_secure: bool = False
    bootstrap_admin_username: str = ""
    bootstrap_admin_password: SecretStr | None = None
    bootstrap_admin_display_name: str = "系统管理员"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.web_origins.split(",") if origin.strip()]

    @property
    def missing_aliyun_asr_settings(self) -> list[str]:
        if self.asr_provider.strip().lower() != "aliyun":
            return []
        values = {
            "ALIYUN_NLS_APPKEY": self.aliyun_nls_appkey,
            "ALIYUN_ACCESS_KEY_ID": self.aliyun_access_key_id,
            "ALIYUN_ACCESS_KEY_SECRET": self.aliyun_access_key_secret,
        }
        return [name for name, value in values.items() if not value]

    @property
    def asr_configured(self) -> bool:
        provider = self.asr_provider.strip().lower()
        if provider == "mock":
            return True
        if provider == "aliyun":
            return not self.missing_aliyun_asr_settings
        return False

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_api_base and self.llm_api_key and self.llm_model)


@lru_cache
def get_settings() -> Settings:
    return Settings()
