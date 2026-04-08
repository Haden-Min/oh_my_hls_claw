from __future__ import annotations

import asyncio
from pathlib import Path


class IcarusRunner:
    async def run(self, rtl_files: list[str], tb_file: str, work_dir: str, timeout: int = 30) -> dict[str, object]:
        work_path = Path(work_dir)
        work_path.mkdir(parents=True, exist_ok=True)
        output_vvp = work_path / "sim.vvp"

        compile_process = await asyncio.create_subprocess_exec(
            "iverilog",
            "-o",
            str(output_vvp),
            *rtl_files,
            tb_file,
            cwd=str(work_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await compile_process.communicate()
        if compile_process.returncode != 0:
            return {"status": "COMPILE_ERROR", "log": (stdout + stderr).decode(), "pass": False}

        sim_process = await asyncio.create_subprocess_exec(
            "vvp",
            str(output_vvp),
            cwd=str(work_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            sim_stdout, sim_stderr = await asyncio.wait_for(sim_process.communicate(), timeout=timeout)
        except TimeoutError:
            sim_process.kill()
            await sim_process.wait()
            return {"status": "TIMEOUT", "log": f"Simulation timed out after {timeout}s", "pass": False}

        sim_log = (sim_stdout + sim_stderr).decode()
        passed = "PASS" in sim_log and "FAIL" not in sim_log
        return {"status": "PASS" if passed else "FAIL", "log": sim_log, "pass": passed}
