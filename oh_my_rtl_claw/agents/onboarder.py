from __future__ import annotations

import json

from .base import AgentMessage, BaseAgent


class OnboarderAgent(BaseAgent):
    def _format_input(self, message: AgentMessage) -> str:
        return json.dumps(
            {"content": message.content, "artifacts": message.artifacts, "metadata": message.metadata},
            ensure_ascii=False,
            indent=2,
        )

    def _parse_output(self, raw_response: str) -> AgentMessage:
        constraints = self.extract_tag(raw_response, "CONSTRAINTS")
        wrapper = self.extract_tag(raw_response, "WRAPPER")
        build_script = self.extract_tag(raw_response, "BUILD_SCRIPT")
        firmware = self.extract_tag(raw_response, "FIRMWARE")
        return AgentMessage(
            role=self.name,
            content=raw_response,
            artifacts={
                "constraints": constraints,
                "wrapper": wrapper,
                "build_script": build_script,
                "firmware": firmware,
            },
            metadata={"approved": True},
        )
