import sys
import types
import unittest
from pathlib import Path
import shutil
import uuid

if "yaml" not in sys.modules:
    sys.modules["yaml"] = types.SimpleNamespace(safe_load=lambda *_args, **_kwargs: {}, safe_dump=lambda *_args, **_kwargs: None)

from src.utils.file_manager import FileManager
from src.orchestrator import Orchestrator


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


if __name__ == "__main__":
    unittest.main()
