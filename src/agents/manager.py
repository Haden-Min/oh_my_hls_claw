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
        modules = spec.get("modules", [])
        module_specs = {module.get("name", "unnamed_module"): module for module in modules if module.get("name")}
        hierarchy = ManagerAgent._build_module_hierarchy(modules)
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
                    "module_spec": module_specs.get(module, {"name": module}),
                }
            bucket = grouped[module]
            description = ManagerAgent._choose_description(item, module)
            bucket["description_parts"].append(str(description))
            for dependency in ManagerAgent._coerce_list(item.get("dependencies", item.get("depends_on", []))):
                if dependency != module:
                    bucket["dependencies"].add(dependency)
            bucket["verification"].extend(ManagerAgent._coerce_list(item.get("verification", item.get("verification_scope", []))))
            bucket["deliverables"].extend(ManagerAgent._coerce_list(item.get("deliverables", [])))

        # Ensure every module in the spec participates in the execution graph, even if the planner omitted a step.
        for module in module_specs:
            if module in grouped:
                continue
            module_order.append(module)
            grouped[module] = {
                "module": module,
                "description_parts": [f"Implement and verify {module}"],
                "dependencies": set(),
                "priority": "medium",
                "verification": [],
                "deliverables": [],
                "module_spec": module_specs[module],
            }

        for module, bucket in grouped.items():
            for dependency in hierarchy.get(module, {}).get("children", []):
                if dependency != module:
                    bucket["dependencies"].add(dependency)

        ordered_modules = ManagerAgent._topological_module_order(module_order, grouped)

        design_steps = []
        for index, module in enumerate(ordered_modules, start=1):
            bucket = grouped[module]
            hierarchy_info = hierarchy.get(module, {})
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
                    "hierarchy_level": hierarchy_info.get("level", 0),
                    "child_modules": hierarchy_info.get("children", []),
                    "parent_modules": hierarchy_info.get("parents", []),
                }
            )

        normalized["design_steps"] = design_steps
        normalized["module_hierarchy"] = {
            module: {
                "children": hierarchy.get(module, {}).get("children", []),
                "parents": hierarchy.get(module, {}).get("parents", []),
                "level": hierarchy.get(module, {}).get("level", 0),
            }
            for module in ordered_modules
        }
        return normalized

    @staticmethod
    def _build_module_hierarchy(modules: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        hierarchy: dict[str, dict[str, Any]] = {}
        module_names = {module.get("name") for module in modules if module.get("name")}
        for module in modules:
            name = module.get("name")
            if not name:
                continue
            hierarchy[name] = {
                "children": ManagerAgent._extract_related_modules(module, module_names, ("child_modules", "children", "submodules", "depends_on", "dependencies")),
                "parents": [],
                "level": 0,
            }

        for name, info in hierarchy.items():
            for child in info["children"]:
                hierarchy.setdefault(child, {"children": [], "parents": [], "level": 0})
                if name not in hierarchy[child]["parents"]:
                    hierarchy[child]["parents"].append(name)

        for name in hierarchy:
            hierarchy[name]["children"] = ManagerAgent._dedupe_preserve_order(hierarchy[name]["children"])
            hierarchy[name]["parents"] = ManagerAgent._dedupe_preserve_order(hierarchy[name]["parents"])

        levels: dict[str, int] = {}

        def compute_level(module_name: str, trail: set[str] | None = None) -> int:
            if module_name in levels:
                return levels[module_name]
            trail = trail or set()
            if module_name in trail:
                return 0
            trail = set(trail)
            trail.add(module_name)
            children = hierarchy.get(module_name, {}).get("children", [])
            if not children:
                levels[module_name] = 0
                return 0
            level = max(compute_level(child, trail) + 1 for child in children)
            levels[module_name] = level
            return level

        for name in hierarchy:
            hierarchy[name]["level"] = compute_level(name)
        return hierarchy

    @staticmethod
    def _extract_related_modules(module: dict[str, Any], module_names: set[str], fields: tuple[str, ...]) -> list[str]:
        related: list[str] = []
        for field in fields:
            values = ManagerAgent._coerce_list(module.get(field))
            for value in values:
                if isinstance(value, str) and value in module_names and value != module.get("name"):
                    related.append(value)
                elif isinstance(value, dict):
                    candidate = value.get("module") or value.get("name")
                    if isinstance(candidate, str) and candidate in module_names and candidate != module.get("name"):
                        related.append(candidate)
        return ManagerAgent._dedupe_preserve_order(related)

    @staticmethod
    def _topological_module_order(module_order: list[str], grouped: dict[str, dict[str, Any]]) -> list[str]:
        ordered: list[str] = []
        visited: set[str] = set()
        visiting: set[str] = set()

        def visit(module: str) -> None:
            if module in visited:
                return
            if module in visiting:
                return
            visiting.add(module)
            for dependency in grouped.get(module, {}).get("dependencies", []):
                if dependency in grouped:
                    visit(dependency)
            visiting.remove(module)
            visited.add(module)
            ordered.append(module)

        for module in module_order:
            visit(module)
        return ordered

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

    @staticmethod
    def _choose_description(item: dict[str, Any], module: str) -> str:
        description = item.get("description")
        if isinstance(description, str) and description.strip():
            return description.strip()
        step_value = item.get("step")
        if isinstance(step_value, str) and step_value.strip() and not step_value.strip().isdigit():
            return step_value.strip()
        step_id = item.get("step_id")
        if isinstance(step_id, str) and step_id.strip():
            return step_id.strip()
        return f"Implement and verify {module}"
