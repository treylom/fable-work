from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from test_support import EXAMPLE_CWD, GATES, blocked, run_hook

LEDGER = GATES / "post_tool_use.py"
STOP = GATES / "stop_gate.py"


class CodexVerifyLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="tofable-codex-ledger-")
        self.env = {"FABLE_STATE_DIR": self.tmp.name}
        self.session = {"session_id": "verify-sess", "cwd": EXAMPLE_CWD}

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def record_change(self, path: str, tool: str = "Write") -> None:
        proc = run_hook(LEDGER, {**self.session, "tool_name": tool, "tool_input": {"file_path": path}}, self.env)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def record_verify(self, command: str, output: str = "1 passed, process exited with code 0") -> None:
        proc = run_hook(
            LEDGER,
            {**self.session, "tool_name": "Bash", "tool_input": {"command": command}, "tool_response": {"stdout": output, "exit_code": 0}},
            self.env,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def stop(self, extra: dict | None = None, env: dict[str, str] | None = None):
        return run_hook(STOP, {**self.session, **(extra or {})}, env or self.env)

    def test_nominal_change_plus_verify_passes(self) -> None:
        self.record_change(f"{EXAMPLE_CWD}/src/app.py")
        self.record_verify("python3 -m unittest tests/test_app.py")
        self.assertFalse(blocked(self.stop()))

    def test_deep_failed_verify_and_stale_verify_still_block(self) -> None:
        self.record_change(f"{EXAMPLE_CWD}/src/app.py")
        run_hook(
            LEDGER,
            {**self.session, "tool_name": "Bash", "tool_input": {"command": "pytest tests/ -q"}, "tool_response": {"stderr": "1 failed", "exit_code": 1}},
            self.env,
        )
        self.assertTrue(blocked(self.stop()))

        stale = {"session_id": "stale", "cwd": EXAMPLE_CWD}
        run_hook(LEDGER, {**stale, "tool_name": "Bash", "tool_input": {"command": "pytest tests/ -q"}, "tool_response": {"stdout": "1 passed", "exit_code": 0}}, self.env)
        run_hook(LEDGER, {**stale, "tool_name": "apply_patch", "tool_input": {"command": "*** Begin Patch\n*** Update File: src/later.py\n@@\n+x\n*** End Patch"}}, self.env)
        self.assertTrue(blocked(run_hook(STOP, stale, self.env)))

    def test_deep_apply_patch_path_parsing_records_change(self) -> None:
        patch = "*** Begin Patch\n*** Update File: src/service.py\n@@\n-old\n+new\n*** End Patch"
        run_hook(LEDGER, {**self.session, "tool_name": "apply_patch", "tool_input": {"command": patch}}, self.env)
        self.assertTrue(blocked(self.stop()))

    def test_boundary_docs_only_malformed_and_kill_switch_pass(self) -> None:
        self.record_change(f"{EXAMPLE_CWD}/docs/notes.md")
        self.assertFalse(blocked(self.stop()))
        self.record_change(f"{EXAMPLE_CWD}/src/config.py")
        self.assertFalse(blocked(self.stop(env={**self.env, "FABLE_GATE_OFF": "1"})))
        self.assertFalse(blocked(run_hook(LEDGER, "{not json", self.env)))
        self.assertFalse(blocked(run_hook(STOP, "{not json", self.env)))


if __name__ == "__main__":
    unittest.main()
