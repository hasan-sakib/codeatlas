import pytest
from fastapi.testclient import TestClient

from app.core.config import clear_settings_cache
from app.main import create_app

REQUIRED_SETTINGS_ENV = {
    "DATABASE__URL": "postgresql+asyncpg://test:test@localhost:5432/test",
    "QDRANT__URL": "http://localhost:6333",
    "REDIS__URL": "redis://localhost:6379/0",
    "OLLAMA__BASE_URL": "http://localhost:11434",
    "SECURITY__JWT_SECRET_KEY": "test-secret-key",
}


@pytest.fixture(autouse=True)
def settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provide the minimal required settings via env vars so Settings()
    constructs without a real .env file or live infrastructure.
    Individual tests may monkeypatch additional/overriding vars.
    """
    for key, value in REQUIRED_SETTINGS_ENV.items():
        monkeypatch.setenv(key, value)
    clear_settings_cache()
    yield
    clear_settings_cache()


@pytest.fixture
def client(settings_env: None) -> TestClient:
    return TestClient(create_app())
