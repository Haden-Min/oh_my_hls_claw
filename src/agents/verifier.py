from __future__ import annotations

import json

from .base import AgentMessage, BaseAgent


class VerifierAgent(BaseAgent):
    def _format_input(self, message: AgentMessage) -> str:
        return json.dumps(
            {"content": message.content, "artifacts": message.artifacts, "metadata": message.metadata},
            ensure_ascii=False,
            indent=2,
        )

    def _parse_output(self, raw_response: str) -> AgentMessage:
        testbench = self.extract_tag(raw_response, "TESTBENCH")
        code_review = self.extract_tag(raw_response, "CODE_REVIEW")
        verdict = self.extract_tag(raw_response, "VERDICT") or "REVIEW"
        fix = self.extract_tag(raw_response, "FIX_SUGGESTION")
        approved = verdict.strip().upper() == "PASS"
        return AgentMessage(
            role=self.name,
            content=code_review or raw_response,
            artifacts={"testbench": testbench, "fix_suggestion": fix, "verdict": verdict},
            metadata={"approved": approved, "verdict": verdict},
        )
