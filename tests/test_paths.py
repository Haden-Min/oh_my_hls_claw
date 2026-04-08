import sys
import types
import unittest
from pathlib import Path
import shutil
import uuid
import asyncio
from unittest import mock

if "yaml" not in sys.modules:
    sys.modules["yaml"] = types.SimpleNamespace(safe_load=lambda *_args, **_kwargs: {}, safe_dump=lambda *_args, **_kwargs: None)

from src.agents.base import AgentMessage
from src.llm.openai_client import OpenAIClient
from src.utils.checkpoint import CheckpointManager
from src.utils.file_manager import FileManager
from src.orchestrator import Orchestrator
from src import main as main_module


class PathTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_root = Path(__file__).resolve().parent / f".tmp_paths_{uuid.uuid4().hex}"
        self.temp_root.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_root, ignore_errors=True)

    def test_project_root_lives_under_workspace(self):
        file_manager = FileManager(self.temp_root)
        project_root = file_manager.project_root("alu8_basic")
        self.assertEqual(project_root, self.temp_root / "workspace" / "alu8_basic")

    def test_ensure_project_creates_all_artifacts_under_workspace_only(self):
        file_manager = FileManager(self.temp_root)
        project_root = file_manager.ensure_project("alu8_basic")
        file_manager.write_text(project_root / "rtl" / "alu8_basic.v", "module alu8_basic; endmodule\n")
        file_manager.write_text(project_root / "tb" / "tb_alu8_basic.v", "module tb_alu8_basic; endmodule\n")
        file_manager.write_json(project_root / "project_state.json", {"project_name": "alu8_basic"})

        self.assertEqual(project_root, self.temp_root / "workspace" / "alu8_basic")
        self.assertTrue((self.temp_root / "workspace" / "alu8_basic" / "rtl" / "alu8_basic.v").exists())
        self.assertTrue((self.temp_root / "workspace" / "alu8_basic" / "tb" / "tb_alu8_basic.v").exists())
        self.assertTrue((self.temp_root / "workspace" / "alu8_basic" / "project_state.json").exists())
        self.assertFalse((self.temp_root / "alu8_basic").exists())

    def test_clean_removes_workspace_and_legacy_project_outputs(self):
        file_manager = FileManager(self.temp_root)
        workspace_project = file_manager.ensure_project("alu8_basic")
        file_manager.write_json(workspace_project / "project_state.json", {"project_name": "alu8_basic"})

        legacy_project = self.temp_root / "alu8_basic"
        (legacy_project / "rtl").mkdir(parents=True, exist_ok=True)
        (legacy_project / "project_state.json").write_text('{"project_name":"alu8_basic"}', encoding="utf-8")

        orchestrator = Orchestrator.__new__(Orchestrator)
        orchestrator.root = self.temp_root
        orchestrator.file_manager = file_manager

        removed = orchestrator.clean(project_name="alu8_basic")

        self.assertIn(str(workspace_project), removed)
        self.assertIn(str(legacy_project), removed)
        self.assertFalse(workspace_project.exists())
        self.assertFalse(legacy_project.exists())

    def test_clean_all_does_not_remove_protected_source_directories(self):
        file_manager = FileManager(self.temp_root)
        workspace_project = file_manager.ensure_project("alu8_basic")
        file_manager.write_json(workspace_project / "project_state.json", {"project_name": "alu8_basic"})

        protected_src = self.temp_root / "src"
        (protected_src / "sim").mkdir(parents=True, exist_ok=True)
        (protected_src / "main.py").write_text("print('safe')\n", encoding="utf-8")

        orchestrator = Orchestrator.__new__(Orchestrator)
        orchestrator.root = self.temp_root
        orchestrator.file_manager = file_manager

        removed = orchestrator.clean(all_projects=True)

        self.assertIn(str(workspace_project), removed)
        self.assertFalse(workspace_project.exists())
        self.assertTrue(protected_src.exists())
        self.assertTrue((protected_src / "main.py").exists())
        self.assertNotIn(str(protected_src), removed)

    def test_initialize_project_state_normalizes_description_and_scalar_lists(self):
        orchestrator = Orchestrator.__new__(Orchestrator)
        spec = {
            "design_steps": [
                {
                    "step": 1,
                    "step_id": "step_01_regfile_8x8",
                    "module": "regfile_8x8",
                    "verification": "Check reset behavior",
                    "deliverables": "RTL file",
                }
            ],
            "constraints": {},
        }

        state = orchestrator._initialize_project_state("regfile", spec, None)
        step = state["steps"][0]

        self.assertEqual(step["description"], "Implement and verify regfile_8x8 (step_01_regfile_8x8)")
        self.assertEqual(step["verification"], ["Check reset behavior"])
        self.assertEqual(step["deliverables"], ["RTL file"])

    def test_ready_steps_accept_numeric_and_named_dependencies(self):
        orchestrator = Orchestrator.__new__(Orchestrator)
        project_state = {
            "steps": [
                {"step": 1, "step_id": "step_01_alu", "module": "alu", "status": "completed", "dependencies": []},
                {"step": 2, "step_id": "step_02_regfile", "module": "register_file", "status": "completed", "dependencies": []},
                {"step": 3, "step_id": "step_03_top", "module": "cpu_top", "status": "pending", "dependencies": [1, "register_file"]},
            ]
        }
        ready = orchestrator.get_ready_steps(project_state)
        self.assertEqual([step["module"] for step in ready], ["cpu_top"])

    def test_project_status_summary_reflects_failures(self):
        orchestrator = Orchestrator.__new__(Orchestrator)
        self.assertEqual(orchestrator._summarize_project_status({"steps": [{"status": "completed"}]}), "completed")
        self.assertEqual(orchestrator._summarize_project_status({"steps": [{"status": "failed"}, {"status": "pending"}]}), "failed")
        self.assertEqual(orchestrator._summarize_project_status({"steps": [{"status": "completed"}, {"status": "pending"}]}), "in_progress")

    def test_audit_returns_first_incomplete_step(self):
        orchestrator = Orchestrator.__new__(Orchestrator)
        project_root = self.temp_root / "workspace" / "demo"
        (project_root / "spec").mkdir(parents=True, exist_ok=True)
        (project_root / "spec" / "final_spec.json").write_text("{}", encoding="utf-8")
        project_state = {
            "steps": [
                {"step": 1, "step_id": "step_01_a", "module": "a", "status": "completed", "sim_result": "PASS", "rtl_file": __file__, "tb_file": __file__, "sim_log_file": __file__, "doc_file": __file__},
                {"step": 2, "step_id": "step_02_b", "module": "b", "status": "pending", "sim_result": None, "rtl_file": None, "tb_file": None, "sim_log_file": None, "doc_file": None},
            ]
        }

        audit = orchestrator._audit_project_state(project_root, project_state)

        self.assertFalse(audit["ok"])
        self.assertEqual(audit["step"], 2)
        self.assertEqual(audit["module"], "b")

    def test_reset_step_and_dependents_rewinds_downstream_steps(self):
        orchestrator = Orchestrator.__new__(Orchestrator)
        project_state = {
            "total_steps": 3,
            "steps": [
                {"step": 1, "step_id": "step_01_alu", "module": "alu", "status": "completed", "dependencies": [], "rtl_file": "a", "tb_file": "a", "sim_result": "PASS", "sim_log_file": "a", "doc_file": "a", "elapsed_seconds": 1.0},
                {"step": 2, "step_id": "step_02_regfile", "module": "register_file", "status": "failed", "dependencies": [], "rtl_file": "b", "tb_file": "b", "sim_result": "FAIL", "sim_log_file": "b", "doc_file": "b", "elapsed_seconds": 2.0, "error": "boom"},
                {"step": 3, "step_id": "step_03_top", "module": "cpu_top", "status": "completed", "dependencies": [2], "rtl_file": "c", "tb_file": "c", "sim_result": "PASS", "sim_log_file": "c", "doc_file": "c", "elapsed_seconds": 3.0},
            ],
        }

        orchestrator._reset_step_and_dependents(project_state, 2, "step_02_regfile", "register_file")

        self.assertEqual(project_state["current_step"], 2)
        self.assertEqual(project_state["steps"][1]["status"], "pending")
        self.assertIsNone(project_state["steps"][1]["rtl_file"])
        self.assertIsNone(project_state["steps"][1]["error"])
        self.assertEqual(project_state["steps"][2]["status"], "pending")
        self.assertIsNone(project_state["steps"][2]["tb_file"])

    def test_repair_loop_feeds_sim_log_back_to_rtl_designer(self):
        class DummyConsole:
            def status(self, _message):
                pass

            class _Spinner:
                def __enter__(self):
                    return None

                def __exit__(self, exc_type, exc, tb):
                    return False

            def spinner(self, _message):
                return self._Spinner()

        class FakeRTLDesigner:
            def __init__(self):
                self.name = "rtl_designer"
                self.calls = []

            async def send(self, message):
                self.calls.append(message)
                if len(self.calls) == 1:
                    return AgentMessage(role="rtl_designer", content="draft", artifacts={"verilog": "module demo; assign y = a &lt; b; endmodule"})
                return AgentMessage(role="rtl_designer", content="repaired", artifacts={"verilog": "module demo; assign y = (a < b); endmodule"})

        class FakeVerifier:
            def __init__(self):
                self.name = "verifier"

            async def send(self, _message):
                return AgentMessage(
                    role="verifier",
                    content="found issue",
                    artifacts={"testbench": "module tb; endmodule", "fix_suggestion": "replace escaped operators"},
                    metadata={"approved": True, "score": 100},
                )

        orchestrator = Orchestrator.__new__(Orchestrator)
        orchestrator.settings = {"system": {"harness_max_iterations": 3}}
        orchestrator.context = types.SimpleNamespace(console=DummyConsole())
        orchestrator.file_manager = FileManager(self.temp_root)

        simulate_calls = []

        async def fake_simulate(_work_dir, _rtl_files, _tb_file):
            simulate_calls.append(True)
            if len(simulate_calls) == 1:
                return {"status": "COMPILE_ERROR", "log": "syntax error near &lt;=", "pass": False}
            return {"status": "PASS", "log": "FINAL PASS", "pass": True}

        orchestrator._simulate = fake_simulate

        rtl_designer = FakeRTLDesigner()
        verifier = FakeVerifier()
        step = {"step": 1, "step_id": "step_01_demo", "module": "demo"}
        initial_rtl = asyncio.run(rtl_designer.send(AgentMessage(role="manager", content="x")))

        verilog, verify_result, sim_result, _rtl_path, _tb_path = asyncio.run(
            orchestrator._run_step_with_repair_loop(
                step=step,
                step_spec={"name": "demo"},
                final_spec={"modules": [{"name": "demo"}]},
                project_root=self.temp_root / "workspace" / "demo_project",
                rtl_designer=rtl_designer,
                verifier=verifier,
                initial_rtl_result=initial_rtl,
            )
        )

        self.assertEqual(sim_result["status"], "PASS")
        self.assertIn("module demo; assign y = (a < b); endmodule", verilog)
        self.assertEqual(verify_result.artifacts["fix_suggestion"], "replace escaped operators")
        self.assertEqual(len(rtl_designer.calls), 2)
        repair_message = rtl_designer.calls[-1]
        self.assertIn("syntax error near &lt;=", repair_message.artifacts["sim_log"])
        self.assertEqual(repair_message.artifacts["sim_status"], "COMPILE_ERROR")

    def test_run_single_step_uses_repaired_testbench_for_documentation(self):
        class DummyConsole:
            def status(self, _message):
                pass

            class _Spinner:
                def __enter__(self):
                    return None

                def __exit__(self, exc_type, exc, tb):
                    return False

            def spinner(self, _message):
                return self._Spinner()

            def format_duration(self, seconds):
                return f"{seconds:.1f}s"

        class FakeGuideWriter:
            def __init__(self):
                self.messages = []

            async def send(self, message):
                self.messages.append(message)
                return AgentMessage(role="guide_writer", content="doc", artifacts={"document": "doc"})

        class FakeRTLDesigner:
            async def send(self, _message):
                return AgentMessage(role="rtl_designer", content="draft", artifacts={"verilog": "module demo; endmodule"})

        orchestrator = Orchestrator.__new__(Orchestrator)
        orchestrator.context = types.SimpleNamespace(console=DummyConsole())
        orchestrator.file_manager = FileManager(self.temp_root)

        async def fake_repair_loop(**_kwargs):
            rtl_path = self.temp_root / "workspace" / "demo_project" / "rtl" / "demo.v"
            tb_path = self.temp_root / "workspace" / "demo_project" / "tb" / "tb_demo.v"
            return (
                "module demo; endmodule",
                AgentMessage(role="verifier", content="review", artifacts={"testbench": "module tb_demo; endmodule"}),
                {"status": "PASS", "log": "FINAL PASS", "pass": True},
                rtl_path,
                tb_path,
            )

        orchestrator._run_step_with_repair_loop = fake_repair_loop

        guide_writer = FakeGuideWriter()
        result = asyncio.run(
            orchestrator.run_single_step(
                project_state={"steps": []},
                step={"step": 1, "step_id": "step_01_demo", "module": "demo", "status": "pending"},
                rtl_designer=FakeRTLDesigner(),
                verifier=None,
                guide_writer=guide_writer,
                project_root=self.temp_root / "workspace" / "demo_project",
                final_spec={"modules": [{"name": "demo"}]},
            )
        )

        self.assertEqual(result["status"], "completed")
        self.assertEqual(guide_writer.messages[0].artifacts["tb"], "module tb_demo; endmodule")

    def test_checkpoint_manager_can_auto_approve(self):
        class DummyLocale:
            def t(self, key, **kwargs):
                return key.format(**kwargs) if kwargs else key

        class DummyConsole:
            def __init__(self):
                self.messages = []

            def success(self, message):
                self.messages.append(message)

            def print(self, *_args, **_kwargs):
                raise AssertionError("print should not be called when auto_approve is enabled")

            def input(self, *_args, **_kwargs):
                raise AssertionError("input should not be called when auto_approve is enabled")

        manager = CheckpointManager(locale=DummyLocale(), console=DummyConsole(), auto_approve=True)
        approved = asyncio.run(manager.prompt("Spec Review", {"x": 1}))
        self.assertTrue(approved)

    def test_openai_client_omits_temperature_for_gpt5_models(self):
        captured = {}

        class FakeResponse:
            status_code = 200
            headers = {}

            def raise_for_status(self):
                return None

            def json(self):
                return {"choices": [{"message": {"content": "ok"}}]}

        class FakeHttpClient:
            async def post(self, _url, headers=None, json=None):
                captured["headers"] = headers
                captured["json"] = json
                return FakeResponse()

        client = OpenAIClient(api_key="x", model="gpt-5.4", use_oauth_proxy=False)
        client.client = FakeHttpClient()
        result = asyncio.run(client.chat("sys", [{"role": "user", "content": "hi"}], temperature=0.7))
        self.assertEqual(result, "ok")
        self.assertNotIn("temperature", captured["json"])

    def test_openai_client_keeps_temperature_for_non_reasoning_models(self):
        captured = {}

        class FakeResponse:
            status_code = 200
            headers = {}

            def raise_for_status(self):
                return None

            def json(self):
                return {"choices": [{"message": {"content": "ok"}}]}

        class FakeHttpClient:
            async def post(self, _url, headers=None, json=None):
                captured["json"] = json
                return FakeResponse()

        client = OpenAIClient(api_key="x", model="gpt-4o-mini", use_oauth_proxy=False)
        client.client = FakeHttpClient()
        asyncio.run(client.chat("sys", [{"role": "user", "content": "hi"}], temperature=0.7))
        self.assertEqual(captured["json"]["temperature"], 0.7)

    def test_start_new_project_prints_not_done_panel_for_incomplete_runs(self):
        printed = []

        class FakeProgressConsole:
            def __init__(self, _console):
                pass

            def input(self, _message):
                return "unused"

            def print(self, panel):
                printed.append(panel)

        class FakeOrchestrator:
            def __init__(self, _root):
                self.context = types.SimpleNamespace(checkpoint_manager=types.SimpleNamespace(auto_approve=False))

            async def run_project(self, _user_input, project_name=None, board=None):
                return {
                    "project_name": project_name or "demo",
                    "status": "failed",
                    "final_audit": {"step": 2, "module": "register_file", "reason": "simulation result is COMPILE_ERROR"},
                }

            def save_costs(self, _project_name):
                return None

        args = types.SimpleNamespace(desc="demo", ref=None, project="cpu", board=None, approve_all=False)
        with mock.patch.object(main_module, "ProgressConsole", FakeProgressConsole), mock.patch("src.orchestrator.Orchestrator", FakeOrchestrator):
            asyncio.run(main_module.start_new_project(args))

        rendered = str(printed[0])
        self.assertIn("Not Done", rendered)
        self.assertIn("Blocked at step 2 (register_file)", rendered)


if __name__ == "__main__":
    unittest.main()
