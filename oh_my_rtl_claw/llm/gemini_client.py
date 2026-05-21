from __future__ import annotations

import asyncio

import httpx

from .base import BaseLLMClient


class GeminiClient(BaseLLMClient):
    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash") -> None:
        self.api_key = api_key
        self.model = model
        self.client = httpx.AsyncClient(timeout=120.0)

    async def chat(
        self,
        system: str,
        messages: list[dict[str, str]],
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> str:
        contents = [{"role": "user", "parts": [{"text": system}]}]
        for message in messages:
            role = "user" if message["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": message["content"]}]})
        payload = {
            "contents": contents,
            "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
        }
        url = f"{self.BASE_URL}/{self.model}:generateContent?key={self.api_key}"
        for attempt in range(10):
            response = await self.client.post(url, json=payload)
            if response.status_code == 429:
                await asyncio.sleep(min(5 * (2**attempt), 300))
                continue
            response.raise_for_status()
            data = response.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]
        raise RuntimeError("Gemini chat retries exhausted")

    def count_tokens(self, text: str) -> int:
        return max(1, len(text.split()))

    def get_cost(self, input_tokens: int, output_tokens: int) -> float:
        return (input_tokens * 0.10 + output_tokens * 0.40) / 1_000_000
