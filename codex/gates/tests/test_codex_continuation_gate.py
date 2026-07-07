from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from test_support import EXAMPLE_CWD, GATES, blocked, run_hook, write_transcript

STOP = GATES / "stop_gate.py"


class CodexContinuationGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="tofable-codex-cont-")
        self.env = {"FABLE_STATE_DIR": self.tmp.name}
        self.session = {"session_id": "cont-sess", "cwd": EXAMPLE_CWD}

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def stop(self, text: str, extra: dict | None = None, env: dict[str, str] | None = None):
        transcript = write_transcript(Path(self.tmp.name), text)
        return run_hook(STOP, {**self.session, "transcript_path": str(transcript), **(extra or {})}, env or self.env)

    def test_nominal_english_deferral_blocks_and_clean_completion_passes(self) -> None:
        self.assertTrue(blocked(self.stop("Good progress. I'll finish the migration tomorrow.")))
        self.session = {"session_id": "cont-clean", "cwd": EXAMPLE_CWD}
        self.assertFalse(blocked(self.stop("All checks are reported above.")))

    def test_deep_korean_deferral_and_false_positives(self) -> None:
        self.assertTrue(blocked(self.stop("남은 작업은 내일 아침에 이어서 하겠습니다.")))
        self.session = {"session_id": "cont-false", "cwd": EXAMPLE_CWD}
        self.assertFalse(blocked(self.stop("내일 아침에 회의가 있습니다.")))
        self.assertFalse(blocked(self.stop("배포는 이월 15일입니다.")))

    def test_boundary_loop_guard_missing_transcript_and_kill_switch(self) -> None:
        self.assertFalse(blocked(self.stop("I'll finish this tomorrow.", {"stop_hook_active": True})))
        self.assertFalse(blocked(run_hook(STOP, {**self.session, "transcript_path": f"{self.tmp.name}/missing.jsonl"}, self.env)))
        self.session = {"session_id": "cont-off", "cwd": EXAMPLE_CWD}
        self.assertFalse(blocked(self.stop("I'll finish this tomorrow.", env={**self.env, "FABLE_GATE_OFF": "1"})))


if __name__ == "__main__":
    unittest.main()
