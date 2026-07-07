from __future__ import annotations

import tempfile
import unittest

from test_support import EXAMPLE_CWD, GATES, denied, run_hook

PRE = GATES / "pre_tool_use.py"
LEDGER = GATES / "post_tool_use.py"


class CodexPreToolGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="tofable-codex-pre-")
        self.env = {"FABLE_STATE_DIR": self.tmp.name}

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def pre(self, command: str, session: str = "s1", tool: str = "Bash"):
        return run_hook(PRE, {"session_id": session, "cwd": EXAMPLE_CWD, "tool_name": tool, "tool_input": {"command": command}}, self.env)

    def record_bash(self, command: str, output: str, session: str = "s1", exit_code: int = 1) -> None:
        run_hook(LEDGER, {"session_id": session, "cwd": EXAMPLE_CWD, "tool_name": "Bash", "tool_input": {"command": command}, "tool_response": {"stderr": output, "exit_code": exit_code}}, self.env)

    def test_nominal_surfacing_and_blind_retry_deny_once_then_pass(self) -> None:
        cmd = "rm -rf /tmp/demo"
        self.assertTrue(denied(self.pre(cmd)))
        self.assertFalse(denied(self.pre(cmd)))

        retry = "pytest tests/ -q"
        self.record_bash(retry, "1 failed")
        self.assertTrue(denied(self.pre(retry)))
        self.assertFalse(denied(self.pre(retry)))

    def test_deep_destructive_tokens_probe_breaks_retry_and_session_isolation(self) -> None:
        for command in ("git push --force origin main", "git reset --hard HEAD", "find tmp -name '*.x' -delete", "rsync -a --delete a/ b/"):
            self.assertTrue(denied(self.pre(command, session=command)))
        self.assertFalse(denied(self.pre("grep -rn 'rm -rf' docs/")))

        self.record_bash("pytest tests/ -q", "1 failed", session="fail-a")
        self.assertFalse(denied(self.pre("ls -la tests/", session="fail-a")))
        self.assertFalse(denied(self.pre("pytest tests/ -q", session="fail-b")))

    def test_boundary_non_bash_kill_switch_malformed_and_cap(self) -> None:
        self.assertFalse(denied(self.pre("rm -rf /tmp/x", tool="Read")))
        self.assertFalse(denied(run_hook(PRE, "{not json", self.env)))
        self.assertFalse(denied(run_hook(PRE, {"session_id": "off", "cwd": EXAMPLE_CWD, "tool_name": "Bash", "tool_input": {"command": "rm -rf /tmp/x"}}, {**self.env, "FABLE_GATE_OFF": "1"})))
        for i in range(5):
            self.assertTrue(denied(self.pre(f"rm -rf /tmp/cap{i}", session="cap")))
        self.assertFalse(denied(self.pre("rm -rf /tmp/cap-final", session="cap")))


if __name__ == "__main__":
    unittest.main()
