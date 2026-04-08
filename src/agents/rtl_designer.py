from __future__ import annotations

import json

from .base import AgentMessage, BaseAgent


class RTLDesignerAgent(BaseAgent):
    def _format_input(self, message: AgentMessage) -> str:
        return json.dumps(
            {"content": message.content, "artifacts": message.artifacts, "metadata": message.metadata},
            ensure_ascii=False,
            indent=2,
        )

    def _parse_output(self, raw_response: str) -> AgentMessage:
        verilog = self.decode_html_entities(self.extract_tag(raw_response, "VERILOG"))
        notes = self.extract_tag(raw_response, "NOTES")
        return AgentMessage(role=self.name, content=notes or raw_response, artifacts={"verilog": verilog}, metadata={})
