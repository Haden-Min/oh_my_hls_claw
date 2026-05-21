from __future__ import annotations

import asyncio

import httpx

from .base import BaseLLMClient


class OllamaClient(BaseLLMClient):
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "gemma4:26b-it-q4_K_M") -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.client = httpx.AsyncClient(timeout=180.0)

    async def chat(
        self,
        system: str,
        messages: list[dict[str, str]],
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> str:
        payload = {
            "model": self.model,
            "stream": False,
            "messages": [{"role": "system", "content": system}] + messages,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        url = f"{self.base_url}/api/chat"
        for attempt in range(10):
            response = await self.client.post(url, json=payload)
            if response.status_code == 429:
                await asyncio.sleep(min(5 * (2**attempt), 300))
                continue
            response.raise_for_status()
            return response.json()["message"]["content"]
        raise RuntimeError("Ollama chat retries exhausted")

    def count_tokens(self, text: str) -> int:
        return max(1, len(text.split()))

    def get_cost(self, input_tokens: int, output_tokens: int) -> float:
        return 0.0
