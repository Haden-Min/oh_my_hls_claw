from __future__ import annotations

import asyncio
import re

import httpx

from .base import BaseLLMClient


class RateLimitExhausted(RuntimeError):
    pass


class OpenAIClient(BaseLLMClient):
    def __init__(
        self,
        api_key: str = "",
        model: str = "gpt-5.4",
        base_url: str = "https://api.openai.com/v1/chat/completions",
        use_oauth_proxy: bool = False,
        max_retries: int = 10,
        base_wait: float = 5.0,
        max_wait: float = 300.0,
    ) -> None:
        self.model = model
        self.use_oauth_proxy = use_oauth_proxy
        self.max_retries = max_retries
        self.base_wait = base_wait
        self.max_wait = max_wait
        self.base_url = (
            "http://127.0.0.1:10531/v1/chat/completions" if use_oauth_proxy else base_url
        )
        self.api_key = "not-needed" if use_oauth_proxy else api_key
        self.client = httpx.AsyncClient(timeout=180.0)

    async def chat(
        self,
        system: str,
        messages: list[dict[str, str]],
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> str:
        formatted = [{"role": "system", "content": system}] + messages
        headers = {"Content-Type": "application/json"}
        if not self.use_oauth_proxy:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {
            "model": self.model,
            "messages": formatted,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        for attempt in range(self.max_retries):
            try:
                response = await self.client.post(self.base_url, headers=headers, json=payload)
                if response.status_code == 429:
                    await asyncio.sleep(self._parse_retry_after(response, attempt))
                    continue
                if response.status_code >= 500:
                    await asyncio.sleep(min(self.base_wait * (2**attempt), self.max_wait))
                    continue
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"]
            except httpx.TimeoutException:
                await asyncio.sleep(min(self.base_wait * (2**attempt), self.max_wait))
        raise RateLimitExhausted("OpenAI chat retries exhausted")

    def _parse_retry_after(self, response: httpx.Response, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return float(retry_after) + 1.0
            except ValueError:
                pass
        for key in ("x-ratelimit-reset-requests", "x-ratelimit-reset-tokens"):
            if response.headers.get(key):
                duration = self._parse_duration(response.headers[key])
                if duration > 0:
                    return duration + 1.0
        return min(self.base_wait * (2**attempt), self.max_wait)

    @staticmethod
    def _parse_duration(duration_str: str) -> float:
        total = 0.0
        minute = re.search(r"(\d+)m", duration_str)
        second = re.search(r"(\d+(?:\.\d+)?)s", duration_str)
        milli = re.search(r"(\d+)ms", duration_str)
        if minute:
            total += int(minute.group(1)) * 60
        if second:
            total += float(second.group(1))
        if milli:
            total += int(milli.group(1)) / 1000
        return total

    def count_tokens(self, text: str) -> int:
        return max(1, len(text.split()))

    def get_cost(self, input_tokens: int, output_tokens: int) -> float:
        if self.use_oauth_proxy:
            return 0.0
        return (input_tokens * 2.5 + output_tokens * 10.0) / 1_000_000
