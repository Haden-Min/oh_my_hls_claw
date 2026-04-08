from __future__ import annotations

import asyncio

import httpx

from .base import BaseLLMClient


class ClaudeClient(BaseLLMClient):
    BASE_URL = "https://api.anthropic.com/v1/messages"

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514") -> None:
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
        for attempt in range(10):
            response = await self.client.post(
                self.BASE_URL,
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": self.model,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "system": system,
                    "messages": messages,
                },
            )
            if response.status_code == 429:
                await asyncio.sleep(min(5 * (2**attempt), 300))
                continue
            response.raise_for_status()
            return response.json()["content"][0]["text"]
        raise RuntimeError("Claude chat retries exhausted")

    def count_tokens(self, text: str) -> int:
        return max(1, len(text.split()))

    def get_cost(self, input_tokens: int, output_tokens: int) -> float:
        return (input_tokens * 3.0 + output_tokens * 15.0) / 1_000_000
