#!/usr/bin/env python3
"""continuation-gate 3-tier tests (nominal/deep/boundary).

Run: python3 hooks/tests/test_continuation_gate.py
Same conventions as test_gate.py: drives the hook as a real subprocess,
block contract = stdout JSON {"decision":"block"} + exit 0.
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
GATE = HOOKS / "continuation-gate.py"
EXAMPLE_CWD = "/workspace/example-project"


def write_transcript(tmp: Path, assistant_text: str) -> Path:
    path = tmp / "transcript.jsonl"
    lines = [
        json.dumps({"type": "user", "message": {"content": "keep going"}}),
        json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": assistant_text}]}}),
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def run_gate(payload: dict | str, extra_env: dict | None = None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    for key in ("FABLE_GATE_OFF", "FABLE_GATE_PILOT", "FABLE_SESSION_NAME"):
        env.pop(key, None)
    env.update(extra_env or {})
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run(
        [sys.executable, str(GATE)], input=raw, capture_output=True, text=True, env=env, timeout=30
    )


def blocked(proc: subprocess.CompletedProcess) -> bool:
    if not proc.stdout.strip():
        return False
    try:
        return json.loads(proc.stdout).get("decision") == "block"
    except json.JSONDecodeError:
        return False


class ContinuationGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="fable-cont-"))
        self.state = self.tmp / "state"
        self.env = {"FABLE_STATE_DIR": str(self.state)}

    def payload(self, text: str, session: str = "s1") -> dict:
        transcript = write_transcript(self.tmp, text)
        return {"cwd": EXAMPLE_CWD, "session_id": session, "transcript_path": str(transcript)}

    # --- nominal ---
    def test_english_deferral_blocks(self) -> None:
        proc = run_gate(self.payload("Good progress today. I'll finish the migration tomorrow."), self.env)
        self.assertTrue(blocked(proc), proc.stdout)

    def test_clean_completion_passes(self) -> None:
        proc = run_gate(self.payload("All tasks verified and complete. Tests pass."), self.env)
        self.assertFalse(blocked(proc), proc.stdout)

    # --- deep ---
    def test_korean_deferral_blocks_then_cap_passes(self) -> None:
        first = run_gate(self.payload("남은 검증은 내일 이어서 진행하겠습니다.", session="s2"), self.env)
        self.assertTrue(blocked(first), first.stdout)
        second = run_gate(self.payload("사용자 지시로 여기서 마무리합니다.", session="s2"), self.env)
        self.assertFalse(blocked(second), second.stdout)  # bounce cap = 1 per session

    def test_wrap_up_phrase_blocks(self) -> None:
        proc = run_gate(self.payload("That's a solid milestone — wrapping up here for tonight."), self.env)
        self.assertTrue(blocked(proc), proc.stdout)

    def test_bare_tomorrow_mention_passes(self) -> None:
        proc = run_gate(self.payload("The deploy window opens tomorrow at 9am; monitoring is armed."), self.env)
        self.assertFalse(blocked(proc), proc.stdout)  # not a first-person deferral

    def test_february_date_passes(self) -> None:
        # reviewer-found false positive: 이월(February) in a date is not a deferral
        proc = run_gate(self.payload("배포는 이월 15일로 잡혀 있습니다."), self.env)
        self.assertFalse(blocked(proc), proc.stdout)

    def test_carry_over_verb_blocks(self) -> None:
        proc = run_gate(self.payload("남은 검증은 다음 주로 이월하겠습니다."), self.env)
        self.assertTrue(blocked(proc), proc.stdout)

    def test_tomorrow_morning_meeting_passes(self) -> None:
        # reviewer-found false positive: a plain schedule mention is not a deferral
        proc = run_gate(self.payload("내일 아침에 회의가 있어요."), self.env)
        self.assertFalse(blocked(proc), proc.stdout)

    def test_tomorrow_morning_continue_blocks(self) -> None:
        proc = run_gate(self.payload("남은 작업은 내일 아침에 이어서 하겠습니다."), self.env)
        self.assertTrue(blocked(proc), proc.stdout)

    # --- boundary ---
    def test_stop_hook_active_passes(self) -> None:
        payload = self.payload("I'll finish this tomorrow.")
        payload["stop_hook_active"] = True
        proc = run_gate(payload, self.env)
        self.assertFalse(blocked(proc), proc.stdout)

    def test_kill_switch_passes(self) -> None:
        env = dict(self.env, FABLE_GATE_OFF="1")
        proc = run_gate(self.payload("I'll finish this tomorrow."), env)
        self.assertFalse(blocked(proc), proc.stdout)

    def test_missing_transcript_fail_open(self) -> None:
        proc = run_gate({"cwd": EXAMPLE_CWD, "session_id": "s3", "transcript_path": str(self.tmp / "nope.jsonl")}, self.env)
        self.assertFalse(blocked(proc), proc.stdout)
        self.assertEqual(proc.returncode, 0)

    def test_garbage_stdin_fail_open(self) -> None:
        proc = run_gate("not-json{{", self.env)
        self.assertFalse(blocked(proc), proc.stdout)
        self.assertEqual(proc.returncode, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
