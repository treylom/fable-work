from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from test_support import EXAMPLE_CWD, GATES, block_reason, blocked, run_hook, write_transcript

LEDGER = GATES / "post_tool_use.py"
STOP = GATES / "stop_gate.py"


class CodexClaimEvidenceGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="tofable-codex-claim-")
        self.env = {"FABLE_STATE_DIR": self.tmp.name}
        self.session = {"session_id": "claim-sess", "cwd": EXAMPLE_CWD}

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def verify(self, command: str) -> None:
        run_hook(LEDGER, {**self.session, "tool_name": "Bash", "tool_input": {"command": command}, "tool_response": {"stdout": "ok", "exit_code": 0}}, self.env)

    def stop(self, text: str):
        transcript = write_transcript(Path(self.tmp.name), text)
        return run_hook(STOP, {**self.session, "transcript_path": str(transcript)}, self.env)

    def test_nominal_count_and_identity_require_mechanical_evidence(self) -> None:
        self.assertTrue(blocked(self.stop("I found exactly 84 files.")))
        self.session = {"session_id": "claim-wc", "cwd": EXAMPLE_CWD}
        self.verify("find src -type f | wc -l")
        self.assertFalse(blocked(self.stop("I found exactly 84 files.")))

        self.session = {"session_id": "claim-ident", "cwd": EXAMPLE_CWD}
        self.assertTrue(blocked(self.stop("The two files are byte-for-byte identical.")))
        self.session = {"session_id": "claim-diff", "cwd": EXAMPLE_CWD}
        self.verify("diff -u a b")
        self.assertFalse(blocked(self.stop("The two files are byte-for-byte identical.")))

    def test_deep_korean_mixed_claim_and_checksum_evidence(self) -> None:
        proc = self.stop("정확히 12개 파일이고 완전히 동일합니다.")
        self.assertTrue(blocked(proc))
        self.assertIn("count", block_reason(proc))

        self.session = {"session_id": "claim-sha", "cwd": EXAMPLE_CWD}
        self.verify("shasum artifact-a artifact-b")
        self.assertFalse(blocked(self.stop("완전히 동일함이 확인됐습니다.")))

    def test_boundary_small_numbers_steps_and_absence_priority(self) -> None:
        self.assertFalse(blocked(self.stop("I used 2 steps.")))
        self.assertFalse(blocked(self.stop("Step 3 is complete.")))

        self.session = {"session_id": "claim-absence-priority", "cwd": EXAMPLE_CWD}
        run_hook(LEDGER, {**self.session, "tool_name": "Bash", "tool_input": {"command": "git status"}, "tool_response": {"stdout": "ok", "exit_code": 0}}, self.env)
        proc = self.stop("There are no other files, exactly 84 files total.")
        self.assertTrue(blocked(proc))
        self.assertIn("absence", block_reason(proc))


if __name__ == "__main__":
    unittest.main()
