#!/usr/bin/env python3
"""surfacing-gate 3-tier tests (nominal/deep/boundary).

Run: python3 hooks/tests/test_surfacing_gate.py
Drives the hook as a real subprocess. Deny contract = stdout JSON
hookSpecificOutput.permissionDecision == "deny" + exit 0.
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
GATE = HOOKS / "surfacing-gate.py"
EXAMPLE_CWD = "/workspace/example-project"


def run_gate(payload: dict | str, extra_env: dict | None = None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    for key in ("FABLE_GATE_OFF", "FABLE_GATE_PILOT", "FABLE_SESSION_NAME"):
        env.pop(key, None)
    env.update(extra_env or {})
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run(
        [sys.executable, str(GATE)], input=raw, capture_output=True, text=True, env=env, timeout=30
    )


def denied(proc: subprocess.CompletedProcess) -> bool:
    if not proc.stdout.strip():
        return False
    try:
        out = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return False
    return out.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"


class SurfacingGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="fable-surf-"))
        self.env = {"FABLE_STATE_DIR": str(self.tmp / "state")}

    def payload(self, command: str, session: str = "s1") -> dict:
        return {
            "tool_name": "Bash",
            "tool_input": {"command": command},
            "cwd": EXAMPLE_CWD,
            "session_id": session,
        }

    # --- nominal ---
    def test_rm_rf_first_denied_then_retry_passes(self) -> None:
        cmd = "rm -rf /workspace/example-project/build"
        first = run_gate(self.payload(cmd), self.env)
        self.assertTrue(denied(first), first.stdout)
        second = run_gate(self.payload(cmd), self.env)
        self.assertFalse(denied(second), second.stdout)  # identical retry passes

    def test_plain_command_passes(self) -> None:
        proc = run_gate(self.payload("python3 -m pytest tests/ -q"), self.env)
        self.assertFalse(denied(proc), proc.stdout)

    # --- deep ---
    def test_force_push_denied(self) -> None:
        proc = run_gate(self.payload("git push --force origin main"), self.env)
        self.assertTrue(denied(proc), proc.stdout)

    def test_reset_hard_in_chain_denied(self) -> None:
        proc = run_gate(self.payload("git fetch origin && git reset --hard origin/main"), self.env)
        self.assertTrue(denied(proc), proc.stdout)

    def test_find_delete_denied(self) -> None:
        proc = run_gate(self.payload("find /tmp/scratch -name '*.tmp' -delete"), self.env)
        self.assertTrue(denied(proc), proc.stdout)

    def test_rsync_delete_denied(self) -> None:
        proc = run_gate(self.payload("rsync -a --delete src/ dest/"), self.env)
        self.assertTrue(denied(proc), proc.stdout)

    def test_grep_for_rm_passes(self) -> None:
        # destructive token inside a search pattern, not at a command position
        proc = run_gate(self.payload("grep -rn 'rm -rf' docs/"), self.env)
        self.assertFalse(denied(proc), proc.stdout)

    def test_echo_prose_passes(self) -> None:
        proc = run_gate(self.payload('echo "never run git reset --hard blindly" >> notes.txt'), self.env)
        # `echo` is the command; the destructive phrase is data. The anchor
        # cannot see quoting, so this documents current behavior: the phrase
        # sits after a quote, not after ; | & or line start — must pass.
        self.assertFalse(denied(proc), proc.stdout)

    def test_different_rm_commands_each_bounce(self) -> None:
        first = run_gate(self.payload("rm -rf /tmp/a", session="s2"), self.env)
        self.assertTrue(denied(first), first.stdout)
        other = run_gate(self.payload("rm -rf /tmp/b", session="s2"), self.env)
        self.assertTrue(denied(other), other.stdout)  # different command = new bounce

    def test_session_cap_stops_bouncing(self) -> None:
        for i in range(5):
            proc = run_gate(self.payload(f"rm -rf /tmp/cap{i}", session="s3"), self.env)
            self.assertTrue(denied(proc), f"bounce {i}: {proc.stdout}")
        sixth = run_gate(self.payload("rm -rf /tmp/cap-final", session="s3"), self.env)
        self.assertFalse(denied(sixth), sixth.stdout)  # cap reached — no more friction

    # --- boundary ---
    def test_non_bash_tool_passes(self) -> None:
        proc = run_gate({"tool_name": "Write", "tool_input": {"file_path": "/tmp/x"}, "cwd": EXAMPLE_CWD, "session_id": "s4"}, self.env)
        self.assertFalse(denied(proc), proc.stdout)

    def test_kill_switch_passes(self) -> None:
        env = dict(self.env, FABLE_GATE_OFF="1")
        proc = run_gate(self.payload("rm -rf /tmp/x"), env)
        self.assertFalse(denied(proc), proc.stdout)

    def test_garbage_stdin_fail_open(self) -> None:
        proc = run_gate("not-json{{", self.env)
        self.assertFalse(denied(proc), proc.stdout)
        self.assertEqual(proc.returncode, 0)

    def test_empty_command_passes(self) -> None:
        proc = run_gate(self.payload(""), self.env)
        self.assertFalse(denied(proc), proc.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
