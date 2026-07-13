#!/usr/bin/env python3
"""Weight-audit repairs (2026-07-13 meeting, owner decision ②) — red-first.

Three repairs, each reproducing a friction case measured in a 7-day
live-transcript audit of every gate event (2026-07-13 fleet weight audit):

1. stop-verify: current-turn scope (reason names only paths changed since
   the last successful verification) + re-bounce dedup (one bounce per
   unique unverified path-set per session).
2. surfacing-gate: one-shot pass survives benign recomposition of the same
   destructive token (measured double-deny pairs).
3. prompt-advance-gate: narrowed conditions — meeting-SoT-engaged sessions
   are exempt (task spec lives in the meeting docs), and only substantial
   mutations/dispatches gate (measured 0-1/8 value ratio).

Run: cd hooks/tests && python3 -m unittest test_weight_audit_repairs -v
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
sys.path.insert(0, str(HOOKS))

from fable_lib import should_block_stop  # noqa: E402

SURFACING = HOOKS / "surfacing-gate.py"
PROMPT_GATE = HOOKS / "prompt-advance-gate.py"
EXAMPLE_CWD = "/workspace/example-project"


def run_gate(gate: Path, payload: dict, env_extra: dict) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    for key in ("FABLE_GATE_OFF", "FABLE_GATE_PILOT", "FABLE_SESSION_NAME"):
        env.pop(key, None)
    env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(gate)], input=json.dumps(payload),
        capture_output=True, text=True, env=env, timeout=30,
    )


def denied(proc: subprocess.CompletedProcess) -> bool:
    if not proc.stdout.strip():
        return False
    try:
        out = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return False
    return out.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"


# ---------------------------------------------------------------- stop-verify

def ledger_with(paths_seqs: dict[str, int], verif_success_seqs: list[int],
                stop_blocks: int = 0, with_seq_map: bool = True) -> dict:
    ledger = {
        "change_kinds": ["code"],
        "changed_paths": list(paths_seqs),
        "verification_results": [
            {"command": "pytest", "success": True, "seq": s} for s in verif_success_seqs
        ],
        "stop_blocks": stop_blocks,
        "last_gated_exec_seq": max(paths_seqs.values() or [0]),
    }
    if with_seq_map:
        ledger["changed_path_seqs"] = dict(paths_seqs)
    return ledger


class StopVerifyRebounceDedupTests(unittest.TestCase):
    def test_same_unverified_set_bounces_once(self):
        ledger = ledger_with({"/w/a.py": 1}, [])
        block1, _ = should_block_stop(ledger)
        self.assertTrue(block1)
        ledger["stop_blocks"] = 1  # caller mutation after bounce #1
        block2, _ = should_block_stop(ledger)
        self.assertFalse(block2, "identical unverified path-set must bounce at most once")

    def test_new_change_after_dedup_bounces_again(self):
        ledger = ledger_with({"/w/a.py": 1}, [])
        should_block_stop(ledger)
        ledger["stop_blocks"] = 1
        ledger["changed_path_seqs"]["/w/b.py"] = 2
        ledger["changed_paths"].append("/w/b.py")
        ledger["last_gated_exec_seq"] = 2
        block, reason = should_block_stop(ledger)
        self.assertTrue(block, "a genuinely new unverified change must still gate")
        self.assertIn("/w/b.py", reason)


class StopVerifyScopeTests(unittest.TestCase):
    def test_reason_lists_only_paths_after_last_success(self):
        ledger = ledger_with({"/w/a.py": 1, "/w/b.py": 3}, verif_success_seqs=[2])
        block, reason = should_block_stop(ledger)
        self.assertTrue(block)
        self.assertIn("/w/b.py", reason)
        self.assertNotIn("/w/a.py", reason,
                         "paths already covered by an earlier successful verification "
                         "must not be re-listed (current-turn scope)")

    def test_legacy_ledger_without_seq_map_keeps_old_behavior(self):
        ledger = ledger_with({"/w/a.py": 1, "/w/b.py": 3}, verif_success_seqs=[],
                             with_seq_map=False)
        block, reason = should_block_stop(ledger)
        self.assertTrue(block)
        self.assertIn("/w/a.py", reason)
        self.assertIn("/w/b.py", reason)


# ---------------------------------------------------------------- surfacing

class SurfacingTokenPassTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.env = {"FABLE_STATE_DIR": str(Path(self._tmp.name) / "state")}

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def payload(self, command: str) -> dict:
        return {"tool_name": "Bash", "tool_input": {"command": command},
                "cwd": EXAMPLE_CWD, "session_id": "s-token"}

    def test_recomposed_same_token_passes_once(self):
        first = run_gate(SURFACING, self.payload("rm -rf /tmp/scratch-x"), self.env)
        self.assertTrue(denied(first), first.stdout)
        recomposed = run_gate(
            SURFACING, self.payload("cd /tmp && rm -rf /tmp/scratch-x/sub"), self.env)
        self.assertFalse(
            denied(recomposed),
            "benign recomposition of the just-surfaced token must not re-bounce "
            "(measured double-deny pairs in the live audit)")

    def test_different_token_still_bounces(self):
        run_gate(SURFACING, self.payload("rm -rf /tmp/scratch-x"), self.env)
        other = run_gate(SURFACING, self.payload("git reset --hard HEAD~1"), self.env)
        self.assertTrue(denied(other), "a different destructive class still surfaces")

    def test_exact_rerun_still_passes(self):
        cmd = "rm -rf /tmp/scratch-x"
        run_gate(SURFACING, self.payload(cmd), self.env)
        rerun = run_gate(SURFACING, self.payload(cmd), self.env)
        self.assertFalse(denied(rerun))


# ------------------------------------------------------------ prompt-advance

INTERVIEW_LINE = json.dumps({"type": "assistant",
                             "text": "Skill invoked: ouroboros:interview crystallized the task"})
MEETING_LINE = json.dumps({"type": "assistant", "tool_use": {
    "name": "Edit", "input": {
        "file_path": "/workspace/notes/meetings/2026-07-13-x/02-progress.md"}}})
BIG = "line of substantial deliverable content\n" * 60  # ≥ threshold
TINY = "x"


class PromptAdvanceNarrowingTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.env = {"FABLE_STATE_DIR": str(self.dir / "state")}

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def transcript(self, lines: list[str]) -> Path:
        path = self.dir / "transcript.jsonl"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def payload(self, transcript: Path, tool: str = "Write", content: str = BIG,
                session: str = "s-pa") -> dict:
        tool_input: dict = {"file_path": f"{EXAMPLE_CWD}/app.py"}
        if tool in {"Write", "Edit"}:
            key = "content" if tool == "Write" else "new_string"
            tool_input[key] = content
        if tool in {"Task", "Agent"}:
            tool_input = {"prompt": content}
        return {"session_id": session, "cwd": EXAMPLE_CWD, "tool_name": tool,
                "tool_input": tool_input, "transcript_path": str(transcript)}

    def test_small_mutation_skips(self):
        t = self.transcript([INTERVIEW_LINE])
        proc = run_gate(PROMPT_GATE, self.payload(t, content=TINY, session="s-pa1"), self.env)
        self.assertFalse(denied(proc),
                         "incidental small edits are not execution-grade starts")

    def test_meeting_sot_session_exempt(self):
        t = self.transcript([MEETING_LINE, INTERVIEW_LINE])
        proc = run_gate(PROMPT_GATE, self.payload(t, session="s-pa2"), self.env)
        self.assertFalse(denied(proc),
                         "meeting-dispatched work is externally spec'd — the measured "
                         "0-1/8 value ratio came from exactly these sessions")

    def test_substantial_solo_start_still_gates(self):
        t = self.transcript([INTERVIEW_LINE])
        proc = run_gate(PROMPT_GATE, self.payload(t, session="s-pa3"), self.env)
        self.assertTrue(denied(proc), "the narrowed gate must not be dead")

    def test_short_dispatch_prompt_skips(self):
        t = self.transcript([INTERVIEW_LINE])
        proc = run_gate(PROMPT_GATE,
                        self.payload(t, tool="Agent", content="quick probe", session="s-pa4"),
                        self.env)
        self.assertFalse(denied(proc))


if __name__ == "__main__":
    unittest.main(verbosity=2)
