from __future__ import annotations

import json

from .base import AgentMessage, BaseAgent


class PlannerAgent(BaseAgent):
    def _format_input(self, message: AgentMessage) -> str:
        return json.dumps(
            {"role": message.role, "content": message.content, "artifacts": message.artifacts, "metadata": message.metadata},
            ensure_ascii=False,
            indent=2,
        )

    def _parse_output(self, raw_response: str) -> AgentMessage:
        spec_text = self.extract_tag(raw_response, "SPEC")
        spec = self.parse_json_block(spec_text)
        return AgentMessage(role=self.name, content=spec_text or raw_response, artifacts={"spec": spec}, metadata={"approved": False})
