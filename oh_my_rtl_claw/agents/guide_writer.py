from __future__ import annotations

import json

from .base import AgentMessage, BaseAgent


class GuideWriterAgent(BaseAgent):
    def _format_input(self, message: AgentMessage) -> str:
        return json.dumps(
            {"content": message.content, "artifacts": message.artifacts, "metadata": message.metadata},
            ensure_ascii=False,
            indent=2,
        )

    def _parse_output(self, raw_response: str) -> AgentMessage:
        document = self.extract_tag(raw_response, "DOCUMENT")
        return AgentMessage(role=self.name, content=document or raw_response, artifacts={"document": document or raw_response}, metadata={"approved": True})
