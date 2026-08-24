from __future__ import annotations

from typing import TYPE_CHECKING

from .aliyun import AliyunAsrProvider, AliyunTokenProvider
from .base import AsrProvider
from .mock import MockAsrProvider

if TYPE_CHECKING:
    from ..config import Settings


def create_asr_provider(settings: Settings) -> AsrProvider:
    provider = settings.asr_provider.strip().lower()
    if provider == "mock":
        return MockAsrProvider()
    if provider != "aliyun":
        raise ValueError(f"不支持的ASR供应商：{settings.asr_provider}")

    missing = settings.missing_aliyun_asr_settings
    if missing:
        raise ValueError(f"阿里云ASR缺少配置：{', '.join(missing)}")

    access_key_id = settings.aliyun_access_key_id
    access_key_secret = settings.aliyun_access_key_secret
    if not access_key_id or not access_key_secret:
        raise ValueError("阿里云ASR访问密钥未配置")

    token_provider = AliyunTokenProvider(
        access_key_id=access_key_id.get_secret_value(),
        access_key_secret=access_key_secret.get_secret_value(),
        region_id=settings.aliyun_nls_region_id,
    )
    return AliyunAsrProvider(
        appkey=settings.aliyun_nls_appkey or "",
        token_provider=token_provider,
        websocket_url=settings.aliyun_nls_websocket_url,
        vocabulary_id=settings.aliyun_nls_vocabulary_id,
    )
