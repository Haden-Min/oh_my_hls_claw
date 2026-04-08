from __future__ import annotations

import json
from pathlib import Path
import re
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
        score_text = self.extract_tag(raw_response, "SCORE")
        score = int(score_text) if score_text.isdigit() else 100 if self.extract_tag(raw_response, "APPROVED").lower() == "true" else 0
        approved = score >= 100 or self.extract_tag(raw_response, "APPROVED").lower() == "true"
        step_spec_text = self.extract_tag(raw_response, "STEP_SPEC")
        project_state_text = self.extract_tag(raw_response, "PROJECT_STATE")
        review = self.extract_tag(raw_response, "REVIEW") or self.extract_tag(raw_response, "FEEDBACK")
        artifacts: dict[str, Any] = {}
        if step_spec_text:
            artifacts["step_spec"] = self.parse_json_block(step_spec_text)
        if project_state_text:
            artifacts["project_state"] = self.parse_json_block(project_state_text)
        return AgentMessage(role=self.name, content=review or raw_response, artifacts=artifacts, metadata={"approved": approved, "score": score})

    @staticmethod
    def normalize_execution_plan(spec: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(spec)
        raw_steps = spec.get("design_steps", [])
        module_order: list[str] = []
        grouped: dict[str, dict[str, Any]] = {}

        for item in raw_steps:
            module = item.get("module", "unnamed_module")
            if module not in grouped:
                module_order.append(module)
                grouped[module] = {
                    "module": module,
                    "description_parts": [],
                    "dependencies": set(),
                    "priority": item.get("priority", "medium"),
                    "verification": [],
                    "deliverables": [],
                }
            bucket = grouped[module]
            description = item.get("description") or item.get("step") or item.get("step_id") or f"Implement and verify {module}"
            bucket["description_parts"].append(str(description))
            for dependency in ManagerAgent._coerce_list(item.get("dependencies", item.get("depends_on", []))):
                if dependency != module:
                    bucket["dependencies"].add(dependency)
            bucket["verification"].extend(ManagerAgent._coerce_list(item.get("verification", item.get("verification_scope", []))))
            bucket["deliverables"].extend(ManagerAgent._coerce_list(item.get("deliverables", [])))

        design_steps = []
        for index, module in enumerate(module_order, start=1):
            bucket = grouped[module]
            design_steps.append(
                {
                    "step": index,
                    "step_id": f"step_{index:02d}_{ManagerAgent._slugify(module)}",
                    "module": module,
                    "description": " ".join(bucket["description_parts"]),
                    "dependencies": sorted(bucket["dependencies"]),
                    "priority": bucket["priority"],
                    "verification": ManagerAgent._dedupe_preserve_order(bucket["verification"]),
                    "deliverables": ManagerAgent._dedupe_preserve_order(bucket["deliverables"]),
                }
            )

        normalized["design_steps"] = design_steps
        return normalized

    @staticmethod
    def _dedupe_preserve_order(values: list[Any]) -> list[Any]:
        seen: set[str] = set()
        ordered: list[Any] = []
        for value in values:
            key = json.dumps(value, sort_keys=True, ensure_ascii=False) if not isinstance(value, str) else value
            if key in seen:
                continue
            seen.add(key)
            ordered.append(value)
        return ordered

    @staticmethod
    def _slugify(text: str) -> str:
        return re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").lower()

    @staticmethod
    def _coerce_list(value: Any) -> list[Any]:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        return [value]
