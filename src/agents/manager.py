from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .base import AgentMessage, BaseAgent


class ManagerAgent(BaseAgent):
    def __init__(self, name: str, llm_client: Any, system_prompt: str, project_root: str | Path | None = None) -> None:
        super().__init__(name, llm_client, system_prompt)
        self.project_root = Path(project_root) if project_root else None

    def _format_input(self, message: AgentMessage) -> str:
        return json.dumps(
            {"role": message.role, "content": message.content, "artifacts": message.artifacts, "metadata": message.metadata},
            ensure_ascii=False,
            indent=2,
        )

    def _parse_output(self, raw_response: str) -> AgentMessage:
        approved = self.extract_tag(raw_response, "APPROVED").lower() == "true"
        step_spec_text = self.extract_tag(raw_response, "STEP_SPEC")
        project_state_text = self.extract_tag(raw_response, "PROJECT_STATE")
        review = self.extract_tag(raw_response, "REVIEW")
        artifacts: dict[str, Any] = {}
        if step_spec_text:
            artifacts["step_spec"] = self.parse_json_block(step_spec_text)
        if project_state_text:
            artifacts["project_state"] = self.parse_json_block(project_state_text)
        return AgentMessage(role=self.name, content=review or raw_response, artifacts=artifacts, metadata={"approved": approved})
