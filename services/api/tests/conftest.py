import pytest

from app import main as main_module


@pytest.fixture(autouse=True)
def compatibility_auth_mode(monkeypatch: pytest.MonkeyPatch):
    """Keep pre-auth regression tests focused on their original behavior."""
    monkeypatch.setattr(main_module.settings, "auth_required", False)
    monkeypatch.setattr(main_module.settings, "bootstrap_admin_username", "")
    monkeypatch.setattr(main_module.settings, "bootstrap_admin_password", None)
    monkeypatch.setattr(main_module.settings, "asr_provider", "mock")
