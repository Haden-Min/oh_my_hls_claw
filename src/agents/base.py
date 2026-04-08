from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentMessage:
    role: str
    content: str
    artifacts: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseAgent(ABC):
    def __init__(self, name: str, llm_client: Any, system_prompt: str) -> None:
        self.name = name
        self.llm = llm_client
        self.system_prompt = system_prompt
        self.conversation_history: list[dict[str, str]] = []

    async def send(self, message: AgentMessage) -> AgentMessage:
        self.conversation_history.append({"role": "user", "content": self._format_input(message)})
        response = await self.llm.chat(system=self.system_prompt, messages=self.conversation_history)
        self.conversation_history.append({"role": "assistant", "content": response})
        return self._parse_output(response)

    def reset(self) -> None:
        self.conversation_history = []

    @abstractmethod
    def _format_input(self, message: AgentMessage) -> str:
        raise NotImplementedError

    @abstractmethod
    def _parse_output(self, raw_response: str) -> AgentMessage:
        raise NotImplementedError

    @staticmethod
    def extract_tag(text: str, tag: str) -> str:
        match = re.search(fr"<{tag}>(.*?)</{tag}>", text, re.DOTALL)
        return match.group(1).strip() if match else ""

    @staticmethod
    def parse_json_block(text: str) -> dict[str, Any]:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {}
