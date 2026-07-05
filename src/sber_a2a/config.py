from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Sber A2A Procurement MVP"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    log_level: str = "INFO"
    database_url: str = "sqlite+aiosqlite:///./data/a2a.db"
    supplier_mode: str = "embedded"
    supplier_endpoints: str = (
        "supplier-a=http://127.0.0.1:8201,"
        "supplier-b=http://127.0.0.1:8202,"
        "supplier-c=http://127.0.0.1:8203"
    )
    supplier_timeout_seconds: float = 5.0
    supplier_max_attempts: int = 2
    minimum_quotes: int = 2
    demo_identity_enabled: bool = False
    demo_identity_header: str = "X-Demo-User"

    llm_provider: Literal["disabled", "openrouter", "gigachat"] = "disabled"
    openrouter_api_key: SecretStr | None = None
    openrouter_model: str | None = None
    openrouter_app_url: str | None = None
    openrouter_app_title: str | None = None
    gigachat_credentials: SecretStr | None = None
    gigachat_access_token: SecretStr | None = None
    gigachat_model: str | None = None
    gigachat_scope: str | None = None
    gigachat_base_url: str | None = None
    gigachat_ca_bundle_file: str | None = None
    gigachat_verify_ssl_certs: bool = True

    @property
    def llm_ready(self) -> bool:
        if self.llm_provider == "openrouter":
            return (
                self.openrouter_api_key is not None
                and bool(self.openrouter_api_key.get_secret_value())
                and bool(self.openrouter_model)
            )
        if self.llm_provider == "gigachat":
            has_credentials = (
                self.gigachat_credentials is not None
                and bool(self.gigachat_credentials.get_secret_value())
            )
            has_access_token = (
                self.gigachat_access_token is not None
                and bool(self.gigachat_access_token.get_secret_value())
            )
            return (
                (has_credentials or has_access_token)
                and bool(self.gigachat_model)
            )
        return False

    @property
    def parsed_supplier_endpoints(self) -> dict[str, str]:
        endpoints: dict[str, str] = {}
        for entry in self.supplier_endpoints.split(","):
            supplier_id, separator, url = entry.strip().partition("=")
            if separator and supplier_id and url:
                endpoints[supplier_id] = url.rstrip("/")
        return endpoints


@lru_cache
def get_settings() -> Settings:
    return Settings()
