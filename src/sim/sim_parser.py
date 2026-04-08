from __future__ import annotations


def parse_simulation_log(log: str) -> dict[str, object]:
    passed = "PASS" in log and "FAIL" not in log
    compile_error = "error" in log.lower() and "PASS" not in log
    return {"passed": passed, "compile_error": compile_error, "log": log}
