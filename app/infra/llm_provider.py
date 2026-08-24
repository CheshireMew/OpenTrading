from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from config import settings


class LLMProviderAdapter:
    def __init__(self, llm_config: dict[str, Any] | None = None) -> None:
        config = llm_config or {
            "provider": "deepseek",
            "apiKey": settings.DEEPSEEK_API_KEY,
            "baseUrl": settings.DEEPSEEK_BASE_URL,
            "modelId": settings.AI_MODEL,
            "structuredOutputMode": "json_object",
        }
        self.provider = str(config.get("provider") or "custom")
        self.api_key = str(config.get("apiKey") or "")
        self.base_url = str(config.get("baseUrl") or "")
        self.model = str(config.get("modelId") or "")
        self.structured_output_mode = str(config.get("structuredOutputMode") or "json_object")
        if len(self.api_key) < 10 or "sk-your-key" in self.api_key:
            self.api_key = ""

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.base_url and self.model)

    @property
    def request_timeout(self) -> float:
        timeout = max(float(settings.LLM_REQUEST_TIMEOUT), 1.0)
        if self.provider == "deepseek" and self.model == "deepseek-reasoner":
            return max(timeout, 120.0)
        return timeout

    def endpoint(self) -> str:
        base_url = self.base_url.rstrip("/")
        if self.provider == "anthropic":
            return f"{base_url}/messages"
        if "/v1" in base_url or "/openai" in base_url:
            return f"{base_url}/chat/completions"
        return f"{base_url}/v1/chat/completions"

    def headers(self) -> dict[str, str]:
        if self.provider == "anthropic":
            return {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            }
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def build_payload(self, prompt: str, response_model: type[BaseModel]) -> dict[str, Any]:
        schema = response_model.model_json_schema()
        if self.provider == "anthropic":
            if self.structured_output_mode != "anthropic_json_schema":
                raise ValueError("Anthropic requires anthropic_json_schema")
            return {
                "model": self.model,
                "max_tokens": 2048,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": settings.LLM_TEMPERATURE,
                "output_config": {"format": {"type": "json_schema", "schema": schema}},
            }

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": settings.LLM_TEMPERATURE,
            "stream": False,
        }
        if self.structured_output_mode == "json_schema":
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": response_model.__name__,
                    "strict": True,
                    "schema": schema,
                },
            }
        elif self.structured_output_mode == "json_object":
            payload["response_format"] = {"type": "json_object"}
        else:
            raise ValueError("Unsupported structured output mode")
        return payload

    def extract_content(self, data: dict[str, Any]) -> tuple[str, str | None]:
        if self.provider == "anthropic":
            stop_reason = data.get("stop_reason")
            if stop_reason == "refusal":
                return "", "model_refused"
            if stop_reason == "max_tokens":
                return "", "model_output_truncated"
            content_items = data.get("content")
            if not isinstance(content_items, list):
                raise TypeError("content must be a list")
            for item in content_items:
                if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
                    return item["text"], None
            return "", None

        choices = data.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise TypeError("choices must contain an object")
        choice = choices[0]
        if choice.get("finish_reason") == "length":
            return "", "model_output_truncated"
        message = choice.get("message")
        if not isinstance(message, dict):
            raise TypeError("message must be an object")
        if message.get("refusal"):
            return "", "model_refused"
        content = message.get("content")
        if not isinstance(content, str):
            raise TypeError("content must be a string")
        return content, None


__all__ = ["LLMProviderAdapter"]
