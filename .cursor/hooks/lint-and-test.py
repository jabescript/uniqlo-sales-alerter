#!/usr/bin/env python3
"""Stop hook: run ruff + pytest when code files were modified.

Checks git for unstaged/staged changes in src/ and tests/.  If none are
found the agent is allowed to stop immediately.  If code was touched,
ruff and pytest run; failures produce a followup message asking the
agent to fix them.
"""

import json
import subprocess
import sys


def _changed_code_files() -> list[str]:
    """Return .py files in src/ or tests/ that have been modified."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD", "--", "src/", "tests/"],
            capture_output=True, text=True, timeout=10,
        )
        tracked = [f for f in result.stdout.splitlines() if f.endswith(".py")]

        result2 = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard", "--", "src/", "tests/"],
            capture_output=True, text=True, timeout=10,
        )
        untracked = [f for f in result2.stdout.splitlines() if f.endswith(".py")]

        return tracked + untracked
    except Exception:
        return []


def _run(cmd: list[str]) -> tuple[bool, str]:
    """Run a command and return (success, output)."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        return result.returncode == 0, result.stdout + result.stderr
    except Exception as exc:
        return False, str(exc)


def main() -> None:
    changed = _changed_code_files()
    if not changed:
        json.dump({"decision": "stop"}, sys.stdout)
        return

    failures: list[str] = []

    lint_ok, lint_out = _run(["python", "-m", "ruff", "check", "src/", "tests/"])
    if not lint_ok:
        failures.append(f"ruff check failed:\n{lint_out.strip()}")

    test_ok, test_out = _run(["python", "-m", "pytest", "tests/", "--tb=short", "-q"])
    if not test_ok:
        last_lines = "\n".join(test_out.strip().splitlines()[-30:])
        failures.append(f"pytest failed:\n{last_lines}")

    if failures:
        msg = (
            "Code files were modified but checks failed. "
            "Fix the issues below before finishing.\n\n"
            + "\n\n".join(failures)
        )
        json.dump({"decision": "continue", "followup_message": msg}, sys.stdout)
    else:
        json.dump({"decision": "stop"}, sys.stdout)


if __name__ == "__main__":
    main()
