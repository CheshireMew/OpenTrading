from app.services.llm_config_service import LlmConfigService
from config import settings


def test_llm_config_deepseek_reasoning_switch_updates_model(tmp_path):
    service = LlmConfigService(tmp_path / "llm.json")

    config = service.save_config(
        {
            "provider": "deepseek",
            "apiKey": "sk-test-deepseek",
            "reasoningEnabled": True,
        }
    )
    effective = service.read_effective_config()

    assert config["modelId"] == "deepseek-reasoner"
    assert effective["modelId"] == "deepseek-reasoner"
    assert effective["baseUrl"] == "https://api.deepseek.com/v1"


def test_llm_config_preset_uses_default_base_and_model(tmp_path):
    service = LlmConfigService(tmp_path / "llm.json")

    config = service.save_config(
        {
            "provider": "openai",
            "apiKey": "sk-test-openai",
            "baseUrl": "ignored",
            "modelId": "ignored",
        }
    )
    effective = service.read_effective_config()

    assert config["baseUrl"] == "https://api.openai.com/v1"
    assert config["modelId"] == "gpt-5.2-chat-latest"
    assert config["apiKeyPreview"] == "sk-t********enai"
    assert effective["apiKey"] == "sk-test-openai"


def test_llm_config_custom_keeps_manual_base_and_model(tmp_path):
    service = LlmConfigService(tmp_path / "llm.json")

    config = service.save_config(
        {
            "provider": "custom",
            "apiKey": "local-key",
            "baseUrl": "http://localhost:11434/v1",
            "modelId": "qwen-local",
        }
    )

    assert config["baseUrl"] == "http://localhost:11434/v1"
    assert config["modelId"] == "qwen-local"


def test_llm_config_blank_api_key_update_preserves_existing_key(tmp_path):
    service = LlmConfigService(tmp_path / "llm.json")
    service.save_config({"provider": "openai", "apiKey": "sk-existing"})

    service.save_config({"provider": "siliconflow", "apiKey": None})
    effective = service.read_effective_config()

    assert effective["provider"] == "siliconflow"
    assert effective["apiKey"] == "sk-existing"


def test_llm_config_explicit_blank_key_overrides_environment_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "environment-key")
    service = LlmConfigService(tmp_path / "llm.json")

    saved = service.save_config({
        "provider": "deepseek",
        "apiKey": "",
        "reasoningEnabled": False,
    })

    assert saved["apiKeySet"] is False
    assert service.read_effective_config()["apiKey"] == ""


def test_llm_config_presets_include_glm_and_minimax():
    service = LlmConfigService()
    presets = service.list_presets()
    preset_ids = {item["id"] for item in presets}

    assert "glm" in preset_ids
    assert "minimax" in preset_ids


def test_llm_config_default_path_is_under_runtime_root():
    assert settings.LLM_CONFIG_PATH.resolve().is_relative_to(settings.RUNTIME_ROOT_DIR.resolve())
