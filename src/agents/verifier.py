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
        testbench = self.decode_html_entities(self.extract_tag(raw_response, "TESTBENCH"))
        code_review = self.extract_tag(raw_response, "CODE_REVIEW")
        verdict = self.extract_tag(raw_response, "VERDICT") or "REVIEW"
        fix = self.extract_tag(raw_response, "FIX_SUGGESTION")
        score_text = self.extract_tag(raw_response, "SCORE")
        score = int(score_text) if score_text.isdigit() else (100 if verdict.strip().upper() == "PASS" else 0 if verdict.strip().upper() == "FAIL" else 50)
        approved = score >= 100 or verdict.strip().upper() == "PASS"
        return AgentMessage(
            role=self.name,
            content=code_review or raw_response,
            artifacts={"testbench": testbench, "fix_suggestion": fix, "verdict": verdict},
            metadata={"approved": approved, "verdict": verdict, "score": score},
        )
