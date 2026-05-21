from __future__ import annotations

import re


PASS_RE = re.compile(r"(?im)^\s*(?:FINAL\s+)?PASS(?:ED)?\s*$")
FAIL_RE = re.compile(r"(?im)^\s*FAIL(?:ED)?\b")


def simulation_passed(log: str) -> bool:
    return bool(PASS_RE.search(log)) and not FAIL_RE.search(log)


def parse_simulation_log(log: str) -> dict[str, object]:
    passed = simulation_passed(log)
    compile_error = "error" in log.lower() and "PASS" not in log
    return {"passed": passed, "compile_error": compile_error, "log": log}
