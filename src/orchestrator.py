from __future__ import annotations

import asyncio
import os
import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .agents.base import AgentMessage
from .agents.guide_writer import GuideWriterAgent
from .agents.manager import ManagerAgent
from .agents.onboarder import OnboarderAgent
from .agents.planner import PlannerAgent
from .agents.rtl_designer import RTLDesignerAgent
from .agents.verifier import VerifierAgent
from .harness import HarnessLoop
from .llm.router import ModelRouter
from .sim.icarus_runner import IcarusRunner
from .sim.vivado_runner import VivadoRunner
from .utils.checkpoint import CheckpointManager
from .utils.console import Console, ProgressConsole
from .utils.cost_tracker import CostTracker
from .utils.file_manager import FileManager
from .utils.locale import Locale
from .utils.logger import configure_logger, get_logger


@dataclass
class RuntimeContext:
    root: Path
    settings: dict[str, Any]
    file_manager: FileManager
    locale: Locale
    console: ProgressConsole
    cost_tracker: CostTracker
    checkpoint_manager: CheckpointManager


class Orchestrator:
    PROTECTED_ROOT_DIRS = {
        "config",
        "docs",
        "examples",
        "locale",
        "src",
        "tests",
        "workspace",
        "__pycache__",
        ".git",
        ".venv",
    }

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.file_manager = FileManager(self.root)
        self.settings = self.file_manager.read_yaml(self.root / "config" / "settings.yaml")
        logging_settings = self.settings.get("logging", {})
        configure_logger(logging_settings.get("level", "INFO"), logging_settings.get("log_dir", "workspace/logs"))
        self.logger = get_logger()
        system_settings = self.settings.get("system", {})
        locale = Locale(system_settings.get("language", "en"), self.root / "locale")
        console = ProgressConsole(Console())
        cost_settings = self.settings.get("cost_tracking", {})
        self.context = RuntimeContext(
            root=self.root,
            settings=self.settings,
            file_manager=self.file_manager,
            locale=locale,
            console=console,
            cost_tracker=CostTracker(
                warn_threshold=float(cost_settings.get("warn_threshold_usd", 5.0)),
                hard_limit=float(cost_settings.get("hard_limit_usd", 20.0)),
            ),
            checkpoint_manager=CheckpointManager(locale=locale, console=console),
        )
        self.router = ModelRouter(self.root)
        self.agents = self._build_agents()

    def _build_agents(self) -> dict[str, Any]:
        prompts_dir = self.root / "config" / "prompts"

        def load_prompt(name: str) -> str:
            return self.file_manager.read_text(prompts_dir / f"{name}.md")

        return {
            "planner": PlannerAgent("planner", self.router.build_client("planner"), load_prompt("planner")),
            "manager": ManagerAgent("manager", self.router.build_client("manager"), load_prompt("manager")),
            "rtl_designer": RTLDesignerAgent("rtl_designer", self.router.build_client("rtl_designer"), load_prompt("rtl_designer")),
            "verifier": VerifierAgent("verifier", self.router.build_client("verifier"), load_prompt("verifier")),
            "guide_writer": GuideWriterAgent("guide_writer", self.router.build_client("guide_writer"), load_prompt("guide_writer")),
            "onboarder": OnboarderAgent("onboarder", self.router.build_client("onboarder"), load_prompt("onboarder")),
        }

    async def run_project(self, user_input: str, project_name: str | None = None, board: str | None = None) -> dict[str, Any]:
        project_started_at = time.perf_counter()
        planner: PlannerAgent = self.agents["planner"]
        manager: ManagerAgent = self.agents["manager"]
        rtl_designer: RTLDesignerAgent = self.agents["rtl_designer"]
        verifier: VerifierAgent = self.agents["verifier"]
        guide_writer: GuideWriterAgent = self.agents["guide_writer"]
        onboarder: OnboarderAgent = self.agents["onboarder"]

        self.context.console.status("Planning architecture")
        with self.context.console.spinner("Calling planner"):
            initial_spec = await planner.send(AgentMessage(role="user", content=user_input))
        harness_spec = HarnessLoop(
            planner,
            manager,
            max_iterations=int(self.settings["system"].get("harness_max_iterations", 15)),
            progress_callback=self.context.console.status,
            return_agent_a_on_agent_b_convergence=True,
        )
        self.context.console.status("Refining spec with manager")
        with self.context.console.spinner("Running planner-manager harness"):
            final_spec_message = await harness_spec.run_from_agent_a_response(initial_spec)
        final_spec = final_spec_message.artifacts.get("spec", self._safe_json(final_spec_message.content))
        if not final_spec:
            final_spec = initial_spec.artifacts.get("spec", self._safe_json(initial_spec.content))
        final_spec = manager.normalize_execution_plan(final_spec)

        resolved_name = project_name or final_spec.get("architecture_name") or self._slugify(user_input) or "unnamed_project"
        project_root = self.file_manager.ensure_project(resolved_name)
        manager.project_root = project_root

        if self.settings["system"].get("checkpoint_on_spec", True):
            await self.context.checkpoint_manager.prompt("Spec Review", final_spec)

        project_state = self._initialize_project_state(resolved_name, final_spec, board)
        self.file_manager.write_json(project_root / "project_state.json", project_state)
        self.file_manager.write_json(project_root / "spec" / "final_spec.json", final_spec)

        while ready_steps := self.get_ready_steps(project_state):
            self.context.console.status(f"Ready steps: {', '.join(step['module'] for step in ready_steps)}")
            results = await self.run_parallel_steps(project_state, ready_steps, rtl_designer, verifier, guide_writer, project_root, final_spec)
            for result in results:
                self._apply_step_result(project_state, result)
            self.file_manager.write_json(project_root / "project_state.json", project_state)
            if any(step["status"] == "failed" for step in project_state["steps"]):
                break

        final_status = self._summarize_project_status(project_state)
        project_state["status"] = final_status
        project_state["elapsed_seconds"] = round(time.perf_counter() - project_started_at, 3)
        self.file_manager.write_json(project_root / "project_state.json", project_state)

        if final_status != "completed":
            self.context.console.status(
                f"Project {resolved_name} ended with status {final_status} in {self.context.console.format_duration(project_state['elapsed_seconds'])}"
            )
            return project_state

        all_rtl = self.get_all_rtl_files(project_state)
        self.context.console.status("Generating onboarding assets")
        with self.context.console.spinner("Calling onboarder"):
            onboard_message = await onboarder.send(
                AgentMessage(
                    role="manager",
                    content="Generate onboarding files.",
                    artifacts={"rtl_files": all_rtl, "constraints": project_state.get("constraints", {})},
                )
            )
        self._write_onboard_assets(project_root, onboard_message)

        project_state["current_step"] = project_state["total_steps"]
        project_state["status"] = "completed"
        self.file_manager.write_json(project_root / "project_state.json", project_state)

        self.context.console.status("Writing final project documentation")
        with self.context.console.spinner("Calling guide_writer"):
            project_doc = await guide_writer.send(
                AgentMessage(role="manager", content="Write final project documentation.", artifacts=self.get_full_project_data(project_root, project_state))
            )
        self.file_manager.write_text(project_root / "docs" / "project_report.md", project_doc.artifacts.get("document", project_doc.content))

        self.file_manager.write_json(project_root / "project_state.json", project_state)
        self.context.console.status(
            f"Project completed: {resolved_name} in {self.context.console.format_duration(project_state['elapsed_seconds'])}"
        )
        return project_state

    async def run_parallel_steps(
        self,
        project_state: dict[str, Any],
        ready_steps: list[dict[str, Any]],
        rtl_designer: RTLDesignerAgent,
        verifier: VerifierAgent,
        guide_writer: GuideWriterAgent,
        project_root: Path,
        final_spec: dict[str, Any],
    ) -> list[dict[str, Any]]:
        semaphore = asyncio.Semaphore(int(self.settings["system"].get("max_parallel_agents", 3)))

        async def run_with_limit(step: dict[str, Any]) -> dict[str, Any]:
            async with semaphore:
                return await self.run_single_step(project_state, step, rtl_designer, verifier, guide_writer, project_root, final_spec)

        return await asyncio.gather(*[run_with_limit(step) for step in ready_steps])

    async def run_single_step(
        self,
        project_state: dict[str, Any],
        step: dict[str, Any],
        rtl_designer: RTLDesignerAgent,
        verifier: VerifierAgent,
        guide_writer: GuideWriterAgent,
        project_root: Path,
        final_spec: dict[str, Any],
    ) -> dict[str, Any]:
        step_started_at = time.perf_counter()
        module_name = step["module"]
        step_spec = self._find_module_spec(final_spec, module_name)
        step["status"] = "in_progress"
        self.context.console.status(f"Step {step['step']}: starting module {module_name}")
        self.context.console.status(f"Generating RTL for {module_name}")
        with self.context.console.spinner(f"Calling rtl_designer for {module_name}"):
            rtl_result = await rtl_designer.send(
                AgentMessage(
                    role="manager",
                    content="Generate Verilog module from step spec.",
                    artifacts={"step_spec": step, "module_spec": step_spec, "project_spec": final_spec},
                    metadata={"step": step["step"], "step_id": step["step_id"], "module": module_name},
                )
            )
        verilog, verify_result, sim_result, rtl_path, tb_path = await self._run_step_with_repair_loop(
            step=step,
            step_spec=step_spec,
            final_spec=final_spec,
            project_root=project_root,
            rtl_designer=rtl_designer,
            verifier=verifier,
            initial_rtl_result=rtl_result,
        )
        self.context.console.status(f"Writing documentation for {module_name}")
        with self.context.console.spinner(f"Calling guide_writer for {module_name}"):
            doc = await guide_writer.send(
                AgentMessage(
                    role="manager",
                    content=f"Write step {step['step']} documentation.",
                    artifacts={"spec": step, "module_spec": step_spec, "rtl": verilog, "tb": testbench, "sim_log": sim_result["log"]},
                )
            )
        doc_path = self.file_manager.write_text(project_root / "docs" / f"step_{int(step['step']):02d}_{module_name}.md", doc.artifacts.get("document", doc.content))
        elapsed_seconds = round(time.perf_counter() - step_started_at, 3)
        self.context.console.status(
            f"Step {step['step']} complete for {module_name} in {self.context.console.format_duration(elapsed_seconds)}"
        )
        return {
            "step": step["step"],
            "step_id": step["step_id"],
            "module": module_name,
            "rtl_file": str(rtl_path),
            "tb_file": str(tb_path),
            "sim_result": sim_result["status"],
            "sim_log_file": str(self.file_manager.write_text(project_root / "sim" / module_name / "sim.log", str(sim_result["log"]))),
            "doc_file": str(doc_path),
            "elapsed_seconds": elapsed_seconds,
            "status": "completed" if sim_result["pass"] else "failed",
        }

    async def _run_step_with_repair_loop(
        self,
        step: dict[str, Any],
        step_spec: dict[str, Any],
        final_spec: dict[str, Any],
        project_root: Path,
        rtl_designer: RTLDesignerAgent,
        verifier: VerifierAgent,
        initial_rtl_result: AgentMessage,
    ) -> tuple[str, AgentMessage, dict[str, object], Path, Path]:
        module_name = step["module"]
        max_attempts = int(self.settings["system"].get("harness_max_iterations", 15))
        rtl_result = initial_rtl_result
        latest_verify_result = AgentMessage(role="verifier", content="", artifacts={"testbench": ""}, metadata={})
        latest_sim_result: dict[str, object] = {"status": "FAIL", "log": "", "pass": False}
        rtl_path = project_root / "rtl" / f"{module_name}.v"
        tb_path = project_root / "tb" / f"tb_{module_name}.v"

        for attempt in range(1, max_attempts + 1):
            harness = HarnessLoop(
                rtl_designer,
                verifier,
                max_iterations=max_attempts,
                progress_callback=self.context.console.status,
            )
            self.context.console.status(f"Verifying RTL for {module_name}")
            with self.context.console.spinner(f"Running design-verification harness for {module_name}"):
                latest_verify_result = await harness.run_from_agent_a_response(
                    AgentMessage(
                        role=rtl_result.role,
                        content=rtl_result.content,
                        artifacts={
                            "step_spec": step,
                            "module_spec": step_spec,
                            "project_spec": final_spec,
                            "verilog": rtl_result.artifacts.get("verilog", ""),
                        },
                        metadata={"step": step["step"], "step_id": step["step_id"], "module": module_name},
                    )
                )

            verilog = rtl_result.artifacts.get("verilog", "")
            testbench = latest_verify_result.artifacts.get("testbench", "")
            rtl_path = self.file_manager.write_text(rtl_path, verilog)
            tb_path = self.file_manager.write_text(tb_path, testbench)

            self.context.console.status(f"Running simulation for {module_name}")
            with self.context.console.spinner(f"Running simulator for {module_name}"):
                latest_sim_result = await self._simulate(project_root / "sim" / module_name, [str(rtl_path)], str(tb_path))

            if latest_sim_result["pass"]:
                return verilog, latest_verify_result, latest_sim_result, rtl_path, tb_path

            if attempt == max_attempts:
                break

            self.context.console.status(
                f"Simulation failed for {module_name}; sending sim feedback back to rtl_designer (attempt {attempt + 1}/{max_attempts})"
            )
            with self.context.console.spinner(f"Repairing RTL for {module_name}"):
                rtl_result = await rtl_designer.send(
                    AgentMessage(
                        role="verifier",
                        content="Revise the RTL to resolve the compile or simulation failure and preserve the verified intent.",
                        artifacts={
                            "step_spec": step,
                            "module_spec": step_spec,
                            "project_spec": final_spec,
                            "verilog": verilog,
                            "testbench": testbench,
                            "sim_log": latest_sim_result.get("log", ""),
                            "sim_status": latest_sim_result.get("status", ""),
                            "code_review": latest_verify_result.content,
                            "fix_suggestion": latest_verify_result.artifacts.get("fix_suggestion", ""),
                        },
                        metadata={
                            "step": step["step"],
                            "step_id": step["step_id"],
                            "module": module_name,
                            "repair_attempt": attempt + 1,
                        },
                    )
                )

        return rtl_result.artifacts.get("verilog", ""), latest_verify_result, latest_sim_result, rtl_path, tb_path

    async def _simulate(self, work_dir: Path, rtl_files: list[str], tb_file: str) -> dict[str, object]:
        simulator_settings = self.settings.get("simulator", {})
        simulator_type = simulator_settings.get("type", "icarus")
        timeout = int(simulator_settings.get("timeout_seconds", 30))
        runner = (
            IcarusRunner()
            if simulator_type == "icarus"
            else VivadoRunner(vivado_path=simulator_settings.get("vivado_path"))
        )
        return await runner.run(rtl_files, tb_file, str(work_dir), timeout=timeout)

    def get_ready_steps(self, project_state: dict[str, Any]) -> list[dict[str, Any]]:
        completed_modules = {item["module"] for item in project_state["steps"] if item["status"] == "completed"}
        completed_steps = {item["step"] for item in project_state["steps"] if item["status"] == "completed"}
        completed_step_ids = {item["step_id"] for item in project_state["steps"] if item["status"] == "completed"}
        return [
            step
            for step in project_state["steps"]
            if step["status"] == "pending"
            and all(
                self._dependency_satisfied(dependency, completed_modules, completed_steps, completed_step_ids)
                for dependency in step.get("dependencies", [])
            )
        ]

    def _initialize_project_state(self, project_name: str, final_spec: dict[str, Any], board: str | None) -> dict[str, Any]:
        steps = []
        for index, item in enumerate(final_spec.get("design_steps", []), start=1):
            step_number = int(item.get("step", index))
            steps.append(
                {
                    "step": step_number,
                    "step_id": item.get("step_id", f"step_{step_number}"),
                    "module": item["module"],
                    "description": self._normalize_step_description(item),
                    "dependencies": self._coerce_list(item.get("dependencies", item.get("depends_on", []))),
                    "priority": item.get("priority", "medium"),
                    "verification": self._coerce_list(item.get("verification", item.get("verification_scope", []))),
                    "deliverables": self._coerce_list(item.get("deliverables", [])),
                    "status": "pending",
                    "rtl_file": None,
                    "tb_file": None,
                    "sim_result": None,
                    "sim_log_file": None,
                    "doc_file": None,
                }
            )
        return {
            "project_name": project_name,
            "current_step": 1,
            "total_steps": len(steps),
            "steps": steps,
            "constraints": {"target_board": board or final_spec.get("constraints", {}).get("target_board", "generic"), **final_spec.get("constraints", {})},
            "status": "in_progress",
        }

    def _apply_step_result(self, project_state: dict[str, Any], result: dict[str, Any]) -> None:
        for step in project_state["steps"]:
            if step["step"] == result["step"]:
                step.update(result)
        pending = [step for step in project_state["steps"] if step["status"] != "completed"]
        project_state["current_step"] = pending[0]["step"] if pending else project_state["total_steps"]

    def get_all_rtl_files(self, project_state: dict[str, Any]) -> list[str]:
        return [step["rtl_file"] for step in project_state["steps"] if step["rtl_file"]]

    def get_full_project_data(self, project_root: Path, project_state: dict[str, Any]) -> dict[str, Any]:
        return {
            "project_state": project_state,
            "rtl_files": {Path(path).name: self.file_manager.read_text(path) for path in self.get_all_rtl_files(project_state)},
            "docs": {
                Path(step["doc_file"]).name: self.file_manager.read_text(step["doc_file"])
                for step in project_state["steps"]
                if step.get("doc_file")
            },
            "project_root": str(project_root),
        }

    def resume_project(self, project_name: str) -> dict[str, Any]:
        project_root = self.file_manager.project_root(project_name)
        return self.file_manager.read_json(project_root / "project_state.json", default={})

    def status(self, project_name: str) -> dict[str, Any]:
        return self.resume_project(project_name)

    def cost(self, project_name: str) -> dict[str, Any]:
        project_root = self.file_manager.project_root(project_name)
        return self.file_manager.read_json(project_root / "costs.json", default={"total_cost": 0.0, "breakdown": {}})

    def save_costs(self, project_name: str) -> None:
        project_root = self.file_manager.project_root(project_name)
        self.file_manager.write_json(project_root / "costs.json", self.context.cost_tracker.summary())

    def clean(self, project_name: str | None = None, all_projects: bool = False) -> list[str]:
        removed: list[str] = []
        for target in self._clean_targets(project_name=project_name, all_projects=all_projects):
            if target.exists():
                shutil.rmtree(target)
                removed.append(str(target))
        return removed

    def _find_module_spec(self, final_spec: dict[str, Any], module_name: str) -> dict[str, Any]:
        for module in final_spec.get("modules", []):
            if module.get("name") == module_name:
                return module
        return {"name": module_name, "description": "", "ports": []}

    def _write_onboard_assets(self, project_root: Path, onboard_message: AgentMessage) -> None:
        constraints = onboard_message.artifacts.get("constraints")
        wrapper = onboard_message.artifacts.get("wrapper")
        build_script = onboard_message.artifacts.get("build_script")
        firmware = onboard_message.artifacts.get("firmware")
        if constraints:
            self.file_manager.write_text(project_root / "onboard" / "constraints.xdc", constraints)
        if wrapper:
            self.file_manager.write_text(project_root / "onboard" / "board_wrapper.v", wrapper)
        if build_script:
            self.file_manager.write_text(project_root / "onboard" / "build.tcl", build_script)
        if firmware:
            self.file_manager.write_text(project_root / "onboard" / "firmware.txt", firmware)

    def _clean_targets(self, project_name: str | None = None, all_projects: bool = False) -> list[Path]:
        targets: list[Path] = []
        if all_projects:
            workspace_root = self.root / "workspace"
            if workspace_root.exists():
                targets.extend(path for path in workspace_root.iterdir() if path.is_dir())
            targets.extend(self._legacy_project_roots())
            return self._unique_paths(targets)

        if project_name:
            targets.append(self.file_manager.project_root(project_name))
            legacy_root = self.root / project_name
            if self._looks_like_project_root(legacy_root):
                targets.append(legacy_root)
        return self._unique_paths(targets)

    def _legacy_project_roots(self) -> list[Path]:
        workspace_root = self.root / "workspace"
        legacy_roots: list[Path] = []
        for child in self.root.iterdir():
            if not child.is_dir():
                continue
            if child.name.startswith("."):
                continue
            if child.name in self.PROTECTED_ROOT_DIRS:
                continue
            if child == workspace_root:
                continue
            if self._looks_like_project_root(child):
                legacy_roots.append(child)
        return legacy_roots

    @staticmethod
    def _looks_like_project_root(path: Path) -> bool:
        if not path.exists() or not path.is_dir():
            return False
        if (path / "project_state.json").exists():
            return True
        required_dirs = ("spec", "rtl", "tb")
        return all((path / name).exists() for name in required_dirs)

    @staticmethod
    def _unique_paths(paths: list[Path]) -> list[Path]:
        unique: list[Path] = []
        seen: set[Path] = set()
        for path in paths:
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            unique.append(path)
        return unique

    @staticmethod
    def _coerce_list(value: Any) -> list[Any]:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        return [value]

    @staticmethod
    def _normalize_step_description(item: dict[str, Any]) -> str:
        description = item.get("description")
        if isinstance(description, str) and description.strip():
            return description.strip()
        module = item.get("module", "unnamed_module")
        step_id = item.get("step_id")
        if isinstance(step_id, str) and step_id.strip():
            return f"Implement and verify {module} ({step_id.strip()})"
        return f"Implement and verify {module}"

    @staticmethod
    def _dependency_satisfied(
        dependency: Any,
        completed_modules: set[str],
        completed_steps: set[int],
        completed_step_ids: set[str],
    ) -> bool:
        if isinstance(dependency, int):
            return dependency in completed_steps
        if isinstance(dependency, str):
            if dependency in completed_modules or dependency in completed_step_ids:
                return True
            if dependency.isdigit():
                return int(dependency) in completed_steps
        return False

    @staticmethod
    def _summarize_project_status(project_state: dict[str, Any]) -> str:
        statuses = [step["status"] for step in project_state["steps"]]
        if any(status == "failed" for status in statuses):
            return "failed"
        if statuses and all(status == "completed" for status in statuses):
            return "completed"
        return "in_progress"

    @staticmethod
    def _slugify(text: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").lower()
        return slug[:48]

    @staticmethod
    def _safe_json(text: str) -> dict[str, Any]:
        import json

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {}


async def initialize_system(root: str | Path, console: Console | None = None) -> dict[str, Any]:
    root_path = Path(root)
    file_manager = FileManager(root_path)
    settings_path = root_path / "config" / "settings.yaml"
    env_path = root_path / ".env"
    settings = file_manager.read_yaml(settings_path)
    console = ProgressConsole(console or Console())
    from .utils.oauth_health import check_openai_oauth_proxy

    console.print("Oh_My_HLS_Claw - Initial Setup")
    language_choice = console.input("Select language [en/ko/ja/zh] (default: en): ").strip().lower() or settings["system"].get("language", "en")

    oauth_url = settings.get("openai", {}).get("oauth_proxy_url", "http://127.0.0.1:10531/v1")
    health = await check_openai_oauth_proxy(oauth_url)
    anthropic = ""
    google = ""
    ollama_base_url = ""
    openai_api_key = ""

    if health.get("ok"):
        models = ", ".join(list(health.get("models", []))[:5]) or "unknown"
        console.print(f"OpenAI OAuth proxy detected at {oauth_url}")
        console.print(f"Available models: {models}")
        mode = console.input("Press Enter for recommended OAuth setup, or type [a] for advanced provider setup: ").strip().lower()
        use_oauth_proxy = True
        if mode == "a":
            anthropic = console.input("Anthropic API key (optional): ").strip()
            google = console.input("Google API key (optional): ").strip()
            if console.input("Use local Ollama? [y/N]: ").strip().lower() == "y":
                ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    else:
        console.print(f"OpenAI OAuth proxy not detected at {oauth_url}")
        console.print("Choose setup mode:")
        console.print("  [1] Retry OAuth proxy and use recommended setup")
        console.print("  [2] Configure OpenAI API key")
        console.print("  [3] Advanced provider setup")
        mode = console.input("Select option (default: 2): ").strip() or "2"
        if mode == "1":
            retry_health = await check_openai_oauth_proxy(oauth_url)
            use_oauth_proxy = bool(retry_health.get("ok"))
            if not use_oauth_proxy:
                console.print("OAuth proxy still unavailable. Falling back to API key setup.")
                openai_api_key = console.input("OpenAI API key: ").strip()
        elif mode == "3":
            use_oauth_proxy = False
            openai_api_key = console.input("OpenAI API key (optional): ").strip()
            anthropic = console.input("Anthropic API key (optional): ").strip()
            google = console.input("Google API key (optional): ").strip()
            if console.input("Use local Ollama? [y/N]: ").strip().lower() == "y":
                ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        else:
            use_oauth_proxy = False
            openai_api_key = console.input("OpenAI API key: ").strip()

    simulator_choice = console.input("Simulator [icarus/vivado] (default: icarus): ").strip().lower() or settings["simulator"].get("type", "icarus")
    vivado_path = settings.get("simulator", {}).get("vivado_path")
    if simulator_choice == "vivado":
        console.print("Vivado CLI is supported on Windows, Linux, and WSL wherever xvlog/xelab/xsim are callable.")
        console.print("Linux or WSL2 is recommended for smoother automation, but it is not required.")
        vivado_input = console.input("Vivado bin path (optional, for example C:\\Xilinx\\Vivado\\2024.1\\bin or /tools/Xilinx/Vivado/2024.1/bin): ").strip()
        vivado_path = vivado_input or vivado_path

    settings["system"]["language"] = language_choice
    settings["openai"]["use_oauth_proxy"] = use_oauth_proxy
    settings["simulator"]["type"] = simulator_choice
    settings["simulator"]["vivado_path"] = vivado_path
    file_manager.write_yaml(settings_path, settings)

    env_lines = [
        f"OPENAI_USE_OAUTH_PROXY={'true' if use_oauth_proxy else 'false'}",
        f"OPENAI_API_KEY={openai_api_key if not use_oauth_proxy else ''}",
        f"ANTHROPIC_API_KEY={anthropic}",
        f"GOOGLE_API_KEY={google}",
        f"SIMULATOR={simulator_choice}",
        f"VIVADO_PATH={vivado_path or ''}",
        f"OLLAMA_BASE_URL={ollama_base_url}",
    ]
    file_manager.write_text(env_path, "\n".join(env_lines) + "\n")
    console.print("Configuration saved.")
    console.print("Next step: run `python -m src.main new --desc \"8-bit RISC CPU\"`")
    return settings
