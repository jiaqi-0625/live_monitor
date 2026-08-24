import json
import os
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from cryptography.fernet import Fernet, InvalidToken
from pydantic import SecretStr

from .config import Settings

AI_CONFIG_PURPOSES = {"realtime", "corpus"}


@dataclass(frozen=True)
class ResolvedAiConfig:
    purpose: str
    api_base: str
    api_key: str
    model: str
    source: str

    @property
    def configured(self) -> bool:
        return bool(self.api_base and self.api_key and self.model)

    def as_settings(self, settings: Settings) -> Settings:
        return settings.model_copy(
            update={
                "llm_api_base": self.api_base,
                "llm_api_key": SecretStr(self.api_key) if self.api_key else None,
                "llm_model": self.model,
            }
        )


class ApiKeyCipher:
    def __init__(self, settings: Settings):
        configured_key = (
            settings.app_config_encryption_key.get_secret_value()
            if settings.app_config_encryption_key
            else ""
        )
        if configured_key:
            key = configured_key.encode("ascii")
        else:
            key_path = settings.storage_root / ".ai-config.key"
            key_path.parent.mkdir(parents=True, exist_ok=True)
            if key_path.exists():
                key = key_path.read_bytes().strip()
            else:
                key = Fernet.generate_key()
                key_path.write_bytes(key)
                if os.name != "nt":
                    key_path.chmod(0o600)
        try:
            self._fernet = Fernet(key)
        except ValueError as exc:
            raise RuntimeError("APP_CONFIG_ENCRYPTION_KEY 必须是有效的 Fernet 密钥") from exc

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode("utf-8")).decode("ascii")

    def decrypt(self, value: str) -> str:
        try:
            return self._fernet.decrypt(value.encode("ascii")).decode("utf-8")
        except InvalidToken as exc:
            raise RuntimeError("AI 配置密钥无法解密，请检查服务端加密密钥") from exc


def resolve_ai_config(database, settings: Settings, purpose: str) -> ResolvedAiConfig:
    if purpose not in AI_CONFIG_PURPOSES:
        raise ValueError("未知的 AI 配置用途")
    stored = database.get_ai_config(purpose)
    if stored:
        api_key = ""
        if stored["api_key_encrypted"]:
            api_key = ApiKeyCipher(settings).decrypt(stored["api_key_encrypted"])
        return ResolvedAiConfig(
            purpose=purpose,
            api_base=stored["api_base"],
            api_key=api_key,
            model=stored["model"],
            source="admin",
        )
    return ResolvedAiConfig(
        purpose=purpose,
        api_base=settings.llm_api_base,
        api_key=(
            settings.llm_api_key.get_secret_value() if settings.llm_api_key else ""
        ),
        model=settings.llm_model,
        source="environment",
    )


def fetch_available_models(config: ResolvedAiConfig) -> list[str]:
    if not config.api_base or not config.api_key:
        raise ValueError("请先配置 API 地址和密钥")
    request = Request(
        f"{config.api_base.rstrip('/')}/models",
        headers={"Authorization": f"Bearer {config.api_key}"},
    )
    try:
        with urlopen(request, timeout=20) as response:
            body = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(f"模型列表接口返回 HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError("服务器无法连接模型服务") from exc
    models = body.get("data", [])
    return sorted(
        {
            str(item.get("id", "")).strip()
            for item in models
            if isinstance(item, dict) and item.get("id")
        }
    )


def test_ai_connection(config: ResolvedAiConfig) -> None:
    if not config.configured:
        raise ValueError("请完整配置 API 地址、密钥和模型")
    request = Request(
        f"{config.api_base.rstrip('/')}/chat/completions",
        data=json.dumps(
            {
                "model": config.model,
                "messages": [{"role": "user", "content": "只回复 OK"}],
                "temperature": 0,
                "max_tokens": 4,
            }
        ).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=25) as response:
            body = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(f"模型测试返回 HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError("服务器无法连接模型服务") from exc
    if not body.get("choices"):
        raise RuntimeError("模型服务响应格式不正确")
