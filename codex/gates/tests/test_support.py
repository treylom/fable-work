from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

GATES = Path(__file__).resolve().parents[1]
EXAMPLE_CWD = "/workspace/project"


def run_hook(script: Path, payload: dict[str, Any] | str, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    for key in ("FABLE_GATE_OFF", "FABLE_GATE_PILOT", "FABLE_SESSION_NAME"):
        env.pop(key, None)
    if extra_env:
        env.update(extra_env)
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run([sys.executable, str(script)], input=raw, capture_output=True, text=True, env=env, timeout=30)


def json_stdout(proc: subprocess.CompletedProcess) -> dict[str, Any]:
    if not proc.stdout.strip():
        return {}
    return json.loads(proc.stdout)


def blocked(proc: subprocess.CompletedProcess) -> bool:
    try:
        return json_stdout(proc).get("decision") == "block"
    except json.JSONDecodeError:
        return False


def block_reason(proc: subprocess.CompletedProcess) -> str:
    try:
        return str(json_stdout(proc).get("reason") or "")
    except json.JSONDecodeError:
        return ""


def denied(proc: subprocess.CompletedProcess) -> bool:
    try:
        return json_stdout(proc).get("hookSpecificOutput", {}).get("permissionDecision") == "deny"
    except json.JSONDecodeError:
        return False


def write_transcript(tmp: Path, text: str) -> Path:
    transcript = tmp / "transcript.jsonl"
    transcript.write_text(
        json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}) + "\n",
        encoding="utf-8",
    )
    return transcript
