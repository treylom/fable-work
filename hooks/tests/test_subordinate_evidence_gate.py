#!/usr/bin/env python3
"""subordinate-evidence gate 3-tier tests (nominal/deep/boundary).

Run: python3 hooks/tests/test_subordinate_evidence_gate.py
Drives verify-ledger (PostToolUse events: subagent calls, verifications)
then stop-verify-gate (Stop) as real subprocesses, with the final assistant
text supplied through a minimal transcript file. Block contract = stdout
JSON {"decision": "block"}.
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
STOP_GATE = HOOKS / "stop-verify-gate.py"
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


def blocked(proc: subprocess.CompletedProcess) -> bool:
    if not proc.stdout.strip():
        return False
    try:
        out = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return False
    return out.get("decision") == "block"


class SubordinateEvidenceGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="fable-subev-"))
        self.env = {"FABLE_STATE_DIR": str(self.tmp / "state")}

    def transcript(self, final_text: str) -> str:
        path = self.tmp / "transcript.jsonl"
        entry = {"type": "assistant", "message": {"content": [{"type": "text", "text": final_text}]}}
        path.write_text(json.dumps(entry) + "\n", encoding="utf-8")
        return str(path)

    def subagent_event(self, session: str = "s1", tool: str = "Task") -> dict:
        return {
            "tool_name": tool,
            "tool_input": {"prompt": "collect the report data and write summary.md"},
            "tool_response": {"output": "Done. I created summary.md with 42 rows."},
            "cwd": EXAMPLE_CWD,
            "session_id": session,
        }

    def bash_event(self, command: str, output: str, session: str = "s1") -> dict:
        return {
            "tool_name": "Bash",
            "tool_input": {"command": command},
            "tool_response": {"output": output},
            "cwd": EXAMPLE_CWD,
            "session_id": session,
        }

    def stop_payload(self, final_text: str, session: str = "s1") -> dict:
        return {
            "cwd": EXAMPLE_CWD,
            "session_id": session,
            "transcript_path": self.transcript(final_text),
        }

    def record(self, payload: dict) -> None:
        proc = run_hook(LEDGER, payload, self.env)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    # --- nominal ---
    def test_subagent_then_done_claim_without_verify_blocks_once(self) -> None:
        self.record(self.subagent_event())
        first = run_hook(STOP_GATE, self.stop_payload("서브에이전트 작업까지 전부 완료했습니다."), self.env)
        self.assertTrue(blocked(first), first.stdout)
        self.assertIn("subordinate-evidence", first.stdout)
        second = run_hook(STOP_GATE, self.stop_payload("완료 — 검증은 불가한 환경입니다."), self.env)
        self.assertFalse(blocked(second), second.stdout)  # one bounce per session

    def test_verify_after_subagent_passes(self) -> None:
        self.record(self.subagent_event())
        self.record(self.bash_event("wc -l summary.md", "42 summary.md exit code: 0"))
        proc = run_hook(STOP_GATE, self.stop_payload("Delegate output verified — done."), self.env)
        self.assertFalse(blocked(proc), proc.stdout)

    def test_no_subagent_no_gate(self) -> None:
        proc = run_hook(STOP_GATE, self.stop_payload("작업 완료했습니다."), self.env)
        self.assertFalse(blocked(proc), proc.stdout)

    # --- deep ---
    def test_verify_before_subagent_does_not_count(self) -> None:
        self.record(self.bash_event("pytest -q", "12 passed exit code: 0"))
        self.record(self.subagent_event())
        proc = run_hook(STOP_GATE, self.stop_payload("에이전트가 보고한 대로 완료됐습니다. ✅"), self.env)
        self.assertTrue(blocked(proc), proc.stdout)  # evidence must POSTdate the delegate

    def test_agent_tool_name_also_anchors(self) -> None:
        self.record(self.subagent_event(tool="Agent"))
        proc = run_hook(STOP_GATE, self.stop_payload("All set — the worker finished everything."), self.env)
        self.assertTrue(blocked(proc), proc.stdout)

    def test_non_completion_reply_passes(self) -> None:
        self.record(self.subagent_event())
        proc = run_hook(STOP_GATE, self.stop_payload("중간 상황 공유 — 다음 단계로 넘어가는 중입니다."), self.env)
        self.assertFalse(blocked(proc), proc.stdout)

    # --- boundary ---
    def test_kill_switch(self) -> None:
        self.record(self.subagent_event())
        env = dict(self.env, FABLE_GATE_OFF="1")
        proc = run_hook(STOP_GATE, self.stop_payload("완료했습니다."), env)
        self.assertFalse(blocked(proc), proc.stdout)

    def test_stop_hook_active_loop_guard(self) -> None:
        self.record(self.subagent_event())
        payload = self.stop_payload("완료했습니다.")
        payload["stop_hook_active"] = True
        proc = run_hook(STOP_GATE, payload, self.env)
        self.assertFalse(blocked(proc), proc.stdout)

    def test_absence_gate_priority_preserved(self) -> None:
        # absence claim + subagent both armed: absence must fire first
        self.record(self.bash_event("git log --oneline", "abc123 initial exit code: 0"))
        self.record(self.subagent_event())
        proc = run_hook(STOP_GATE, self.stop_payload("There are no other implementations anywhere. 완료."), self.env)
        self.assertTrue(blocked(proc), proc.stdout)
        self.assertIn("absence", proc.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
