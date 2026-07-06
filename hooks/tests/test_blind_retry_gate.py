#!/usr/bin/env python3
"""blind-retry-gate 3-tier tests (nominal/deep/boundary).

Run: python3 hooks/tests/test_blind_retry_gate.py
The retry gate reads the (last command hash, failed?) pair that
verify-ledger records, so each scenario drives verify-ledger first (as the
harness would via PostToolUse) and then the PreToolUse gate as a subprocess.
Deny contract = stdout JSON hookSpecificOutput.permissionDecision == "deny".
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[1]
GATE = HOOKS / "blind-retry-gate.py"
LEDGER = HOOKS / "verify-ledger.py"
EXAMPLE_CWD = "/workspace/example-project"


def run_hook(script: Path, payload: dict, extra_env: dict | None = None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    for key in ("FABLE_GATE_OFF", "FABLE_GATE_PILOT", "FABLE_SESSION_NAME"):
        env.pop(key, None)
    env.update(extra_env or {})
    return subprocess.run(
        [sys.executable, str(script)], input=json.dumps(payload), capture_output=True, text=True, env=env, timeout=30
    )


def denied(proc: subprocess.CompletedProcess) -> bool:
    if not proc.stdout.strip():
        return False
    try:
        out = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return False
    return out.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"


class BlindRetryGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="fable-retry-"))
        self.env = {"FABLE_STATE_DIR": str(self.tmp / "state")}

    def bash_post(self, command: str, output: str, session: str = "s1") -> dict:
        return {
            "tool_name": "Bash",
            "tool_input": {"command": command},
            "tool_response": {"output": output},
            "cwd": EXAMPLE_CWD,
            "session_id": session,
        }

    def bash_pre(self, command: str, session: str = "s1") -> dict:
        return {
            "tool_name": "Bash",
            "tool_input": {"command": command},
            "cwd": EXAMPLE_CWD,
            "session_id": session,
        }

    def record(self, command: str, output: str, session: str = "s1") -> None:
        proc = run_hook(LEDGER, self.bash_post(command, output, session), self.env)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    # --- nominal ---
    def test_identical_retry_after_failure_denied_once_then_passes(self) -> None:
        cmd = "python3 scripts/build.py --all"
        self.record(cmd, "Traceback (most recent call last): error: boom")
        first = run_hook(GATE, self.bash_pre(cmd), self.env)
        self.assertTrue(denied(first), first.stdout)
        second = run_hook(GATE, self.bash_pre(cmd), self.env)  # intentional retry
        self.assertFalse(denied(second), second.stdout)

    def test_retry_after_success_passes(self) -> None:
        cmd = "python3 scripts/build.py --all"
        self.record(cmd, "build succeeded exit code: 0")
        proc = run_hook(GATE, self.bash_pre(cmd), self.env)
        self.assertFalse(denied(proc), proc.stdout)

    def test_different_command_after_failure_passes(self) -> None:
        self.record("python3 scripts/build.py --all", "error: no such file or directory")
        probe = run_hook(GATE, self.bash_pre("ls -la scripts/"), self.env)
        self.assertFalse(denied(probe), probe.stdout)

    # --- deep ---
    def test_diagnose_then_same_command_passes(self) -> None:
        cmd = "curl -s http://localhost:8787/state.json"
        self.record(cmd, "curl: (7) Failed to connect — exit code: 7 error:")
        blocked = run_hook(GATE, self.bash_pre(cmd), self.env)
        self.assertTrue(denied(blocked), blocked.stdout)
        # a diagnostic probe runs and RESETS the chain (different last command)
        self.record("lsof -i :8787", "python3 61234 tofu ... exit code: 0")
        after = run_hook(GATE, self.bash_pre(cmd), self.env)
        self.assertFalse(denied(after), after.stdout)

    def test_whitespace_variant_is_same_command(self) -> None:
        self.record("pytest tests/ -q", "1 errors")
        proc = run_hook(GATE, self.bash_pre("  pytest tests/ -q  "), self.env)
        self.assertTrue(denied(proc), proc.stdout)  # strip() before hashing

    def test_sessions_isolated(self) -> None:
        cmd = "make check"
        self.record(cmd, "error: target not found", session="sA")
        other = run_hook(GATE, self.bash_pre(cmd, session="sB"), self.env)
        self.assertFalse(denied(other), other.stdout)

    # --- boundary ---
    def test_kill_switch(self) -> None:
        cmd = "pytest -q"
        self.record(cmd, "error: assertion failed")
        env = dict(self.env, FABLE_GATE_OFF="1")
        proc = run_hook(GATE, self.bash_pre(cmd), env)
        self.assertFalse(denied(proc), proc.stdout)

    def test_session_cap_bounds_friction(self) -> None:
        for i in range(7):
            cmd = f"python3 flaky_{i}.py"
            self.record(cmd, "error: flaky")
            proc = run_hook(GATE, self.bash_pre(cmd), self.env)
            if i < 5:
                self.assertTrue(denied(proc), f"cmd {i}: {proc.stdout}")
            else:
                self.assertFalse(denied(proc), f"cap exceeded should pass: {i}")

    def test_non_bash_tool_ignored(self) -> None:
        payload = {"tool_name": "Read", "tool_input": {"file_path": "/tmp/x"}, "cwd": EXAMPLE_CWD, "session_id": "s1"}
        proc = run_hook(GATE, payload, self.env)
        self.assertFalse(denied(proc), proc.stdout)

    def test_malformed_stdin_fail_open(self) -> None:
        env = os.environ.copy()
        env.update(self.env)
        proc = subprocess.run([sys.executable, str(GATE)], input="{not json", capture_output=True, text=True, env=env, timeout=30)
        self.assertEqual(proc.returncode, 0)
        self.assertFalse(denied(proc))


if __name__ == "__main__":
    unittest.main(verbosity=2)
