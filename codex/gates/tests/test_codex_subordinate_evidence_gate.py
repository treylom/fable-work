from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from test_support import EXAMPLE_CWD, GATES, block_reason, blocked, run_hook, write_transcript

LEDGER = GATES / "post_tool_use.py"
STOP = GATES / "stop_gate.py"


class CodexSubordinateEvidenceGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="tofable-codex-subagent-")
        self.env = {"FABLE_STATE_DIR": self.tmp.name}
        self.session = {"session_id": "sub-sess", "cwd": EXAMPLE_CWD}

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def record(self, payload: dict) -> None:
        proc = run_hook(LEDGER, payload, self.env)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def stop(self, text: str, extra: dict | None = None):
        transcript = write_transcript(Path(self.tmp.name), text)
        return run_hook(STOP, {**self.session, "transcript_path": str(transcript), **(extra or {})}, self.env)

    def test_nominal_delegate_completion_blocks_and_later_verify_passes(self) -> None:
        self.record({**self.session, "tool_name": "Task", "tool_input": {"description": "worker"}})
        self.assertTrue(blocked(self.stop("Worker finished; all set.")))

        self.session = {"session_id": "sub-verified", "cwd": EXAMPLE_CWD}
        self.record({**self.session, "tool_name": "Agent", "tool_input": {"description": "worker"}})
        self.record({**self.session, "tool_name": "Bash", "tool_input": {"command": "pytest tests/ -q"}, "tool_response": {"stdout": "1 passed", "exit_code": 0}})
        self.assertFalse(blocked(self.stop("Worker result verified; complete.")))

    def test_deep_verify_before_delegate_and_delegate_report_read(self) -> None:
        self.record({**self.session, "tool_name": "Bash", "tool_input": {"command": "pytest tests/ -q"}, "tool_response": {"stdout": "1 passed", "exit_code": 0}})
        self.record({**self.session, "tool_name": "Task", "tool_input": {"description": "worker"}})
        self.assertTrue(blocked(self.stop("Worker finished; complete.")))

        self.session = {"session_id": "sub-report", "cwd": EXAMPLE_CWD}
        self.record({**self.session, "tool_name": "Read", "tool_input": {"file_path": "worker-report.md"}})
        self.assertTrue(blocked(self.stop("워커 보고 검토 완료했습니다.")))

    def test_boundary_ordinary_read_loop_guard_and_absence_priority(self) -> None:
        self.record({**self.session, "tool_name": "Read", "tool_input": {"file_path": "notes.md"}})
        self.assertFalse(blocked(self.stop("문서 확인 완료했습니다.")))
        self.record({**self.session, "tool_name": "Agent", "tool_input": {"description": "worker"}})
        self.assertFalse(blocked(self.stop("완료했습니다.", {"stop_hook_active": True})))

        self.session = {"session_id": "sub-absence", "cwd": EXAMPLE_CWD}
        self.record({**self.session, "tool_name": "Task", "tool_input": {"description": "worker"}})
        self.record({**self.session, "tool_name": "Bash", "tool_input": {"command": "git status"}, "tool_response": {"stdout": "ok", "exit_code": 0}})
        proc = self.stop("There are no other implementations anywhere. Done.")
        self.assertTrue(blocked(proc))
        self.assertIn("absence", block_reason(proc))


if __name__ == "__main__":
    unittest.main()
