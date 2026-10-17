from app.services.fred_api_config_service import FredApiConfigService
from config import settings


def test_fred_api_config_reads_env_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "FRED_API_KEY", "fred-env-key")
    service = FredApiConfigService(tmp_path / "fred.json")

    config = service.read_config()

    assert config["apiKeySet"] is True
    assert config["apiKeyPreview"] == "fred********-key"
    assert config["source"] == "env"


def test_fred_api_config_save_overrides_env_and_updates_runtime(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "FRED_API_KEY", "fred-env-key")
    service = FredApiConfigService(tmp_path / "fred.json")

    config = service.save_config({"apiKey": "fred-saved-key"})

    assert config["apiKeySet"] is True
    assert config["apiKeyPreview"] == "fred********-key"
    assert config["source"] == "saved"
    assert service.read_effective_api_key() == "fred-saved-key"
    assert settings.FRED_API_KEY == "fred-saved-key"


def test_fred_config_default_path_is_under_runtime_root():
    assert settings.FRED_CONFIG_PATH.resolve().is_relative_to(settings.RUNTIME_ROOT_DIR.resolve())
