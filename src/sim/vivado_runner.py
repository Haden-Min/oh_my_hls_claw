from __future__ import annotations

import asyncio
import os
from pathlib import Path


class VivadoRunner:
    def __init__(self, vivado_path: str | None = None) -> None:
        self.vivado_path = vivado_path

    def _resolve_executable(self, name: str) -> str:
        if not self.vivado_path:
            return name
        candidate = Path(self.vivado_path) / f"{name}.bat"
        if candidate.exists():
            return str(candidate)
        candidate = Path(self.vivado_path) / name
        if candidate.exists():
            return str(candidate)
        return name

    def _build_env(self) -> dict[str, str]:
        env = os.environ.copy()
        if self.vivado_path:
            env["PATH"] = str(self.vivado_path) + os.pathsep + env.get("PATH", "")
        return env

    async def run(self, rtl_files: list[str], tb_file: str, work_dir: str, timeout: int = 60) -> dict[str, object]:
        work_path = Path(work_dir)
        work_path.mkdir(parents=True, exist_ok=True)
        env = self._build_env()
        for file_path in [*rtl_files, tb_file]:
            process = await asyncio.create_subprocess_exec(
                self._resolve_executable("xvlog"),
                file_path,
                cwd=str(work_path),
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()
            if process.returncode != 0:
                return {"status": "COMPILE_ERROR", "log": (stdout + stderr).decode(), "pass": False}

        tb_module = Path(tb_file).stem
        elab = await asyncio.create_subprocess_exec(
            self._resolve_executable("xelab"),
            tb_module,
            "-s",
            "sim_snapshot",
            cwd=str(work_path),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        elab_stdout, elab_stderr = await elab.communicate()
        if elab.returncode != 0:
            return {"status": "ELAB_ERROR", "log": (elab_stdout + elab_stderr).decode(), "pass": False}

        tcl_path = work_path / "run.tcl"
        tcl_path.write_text("run all\nexit\n", encoding="utf-8")
        sim = await asyncio.create_subprocess_exec(
            self._resolve_executable("xsim"),
            "sim_snapshot",
            "-tclbatch",
            str(tcl_path),
            cwd=str(work_path),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            sim_stdout, sim_stderr = await asyncio.wait_for(sim.communicate(), timeout=timeout)
        except TimeoutError:
            sim.kill()
            await sim.wait()
            return {"status": "TIMEOUT", "log": f"Simulation timed out after {timeout}s", "pass": False}

        sim_log = (sim_stdout + sim_stderr).decode()
        passed = "PASS" in sim_log and "FAIL" not in sim_log
        return {"status": "PASS" if passed else "FAIL", "log": sim_log, "pass": passed}
