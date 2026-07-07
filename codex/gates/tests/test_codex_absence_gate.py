from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from test_support import EXAMPLE_CWD, GATES, block_reason, blocked, run_hook, write_transcript

LEDGER = GATES / "post_tool_use.py"
STOP = GATES / "stop_gate.py"


class CodexAbsenceGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="tofable-codex-absence-")
        self.root = self.tmp.name
        self.env = {"FABLE_STATE_DIR": self.root}
        self.session = {"session_id": "absence-sess", "cwd": EXAMPLE_CWD}

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def git(self, command: str) -> None:
        run_hook(LEDGER, {**self.session, "tool_name": "Bash", "tool_input": {"command": command}, "tool_response": {"stdout": "ok", "exit_code": 0}}, self.env)

    def stop(self, text: str, extra: dict | None = None):
        transcript = write_transcript(Path(self.root), text)
        return run_hook(STOP, {**self.session, "transcript_path": str(transcript), **(extra or {})}, self.env)

    def test_nominal_absence_after_plain_git_blocks_and_boundary_passes(self) -> None:
        self.git("git log --oneline")
        proc = self.stop("There are no other implementations anywhere.")
        self.assertTrue(blocked(proc), proc.stdout)
        self.assertIn("absence", block_reason(proc))

        self.session = {"session_id": "absence-boundary", "cwd": EXAMPLE_CWD}
        self.git("git log --oneline --all && git branch -a")
        self.assertFalse(blocked(self.stop("There are no other implementations anywhere.")))

    def test_deep_korean_absence_and_priority(self) -> None:
        self.git("git status")
        self.assertTrue(blocked(self.stop("다른 구현은 존재하지 않습니다.")))

        self.session = {"session_id": "absence-priority", "cwd": EXAMPLE_CWD}
        run_hook(LEDGER, {**self.session, "tool_name": "Write", "tool_input": {"file_path": f"{EXAMPLE_CWD}/src/x.py"}}, self.env)
        self.git("git status")
        proc = self.stop("There are no other files anywhere.")
        self.assertTrue(blocked(proc))
        self.assertNotIn("absence", block_reason(proc))

    def test_boundary_no_git_generic_no_issues_missing_transcript_pass(self) -> None:
        self.assertFalse(blocked(self.stop("There are no other implementations anywhere.")))
        self.git("git status")
        self.assertFalse(blocked(self.stop("No issues found.")))
        self.assertFalse(blocked(run_hook(STOP, {**self.session, "transcript_path": f"{self.root}/missing.jsonl"}, self.env)))


if __name__ == "__main__":
    unittest.main()
