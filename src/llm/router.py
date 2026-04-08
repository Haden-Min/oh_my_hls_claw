from __future__ import annotations

from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from ..utils.file_manager import FileManager
from .base import BaseLLMClient
from .claude_client import ClaudeClient
from .gemini_client import GeminiClient
from .ollama_client import OllamaClient
from .openai_client import OpenAIClient


class ModelRouter:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.file_manager = FileManager(self.root)
        load_dotenv(self.root / ".env")
        self.model_config = self.file_manager.read_yaml(self.root / "config" / "models.yaml")
        self.settings = self.file_manager.read_yaml(self.root / "config" / "settings.yaml")

    def get_agent_config(self, agent_name: str) -> dict[str, Any]:
        return self.model_config.get("agents", {}).get(agent_name, {})

    def build_client(self, agent_name: str) -> BaseLLMClient:
        import os

        config = self.get_agent_config(agent_name)
        provider = config.get("provider", "openai")
        if provider == "openai":
            openai_settings = self.settings.get("openai", {})
            rate_limit = openai_settings.get("rate_limit", {})
            return OpenAIClient(
                api_key=os.getenv("OPENAI_API_KEY", ""),
                model=config.get("model", "gpt-5.4"),
                base_url=openai_settings.get("oauth_proxy_url", "https://api.openai.com/v1/chat/completions").replace("/v1", "/v1/chat/completions") if openai_settings.get("use_oauth_proxy") else "https://api.openai.com/v1/chat/completions",
                use_oauth_proxy=bool(openai_settings.get("use_oauth_proxy", False)),
                max_retries=int(rate_limit.get("max_retries", 10)),
                base_wait=float(rate_limit.get("base_wait_seconds", 5)),
                max_wait=float(rate_limit.get("max_wait_seconds", 300)),
            )
        if provider == "anthropic":
            return ClaudeClient(api_key=os.getenv("ANTHROPIC_API_KEY", ""), model=config.get("model", "claude-sonnet-4-20250514"))
        if provider == "gemini":
            return GeminiClient(api_key=os.getenv("GOOGLE_API_KEY", ""), model=config.get("model", "gemini-2.0-flash"))
        if provider == "ollama":
            return OllamaClient(base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"), model=config.get("model", "gemma4:26b-it-q4_K_M"))
        raise ValueError(f"Unsupported provider: {provider}")
