#!/usr/bin/env python3
"""Codex PreToolUse hook: surface destructive ops, then block blind retries."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from lib import (
        DESTRUCTIVE_RE,
        MAX_RETRY_BLOCKS,
        MAX_SURFACING_BLOCKS,
        command_from_input,
        command_hash,
        deny_payload,
        emit_json,
        gate_enabled,
        load_ledger,
        read_stdin_json,
        save_ledger,
    )
except Exception:
    raise SystemExit(0)

SURFACING_REASON = (
    "tofable-codex-gate(surfacing): this command contains a destructive operation ({token}). "
    "State the operation, targets, and safety rationale, then re-run the same command; the identical retry passes."
)
RETRY_REASON = (
    "tofable-codex-gate(blind-retry): this exact command just failed and is being re-run unchanged. "
    "Name the failure cause, run one probe, or change the command. If it is truly transient, re-run after this bounce."
)


def main() -> int:
    try:
        input_data = read_stdin_json()
        if not input_data:
            return 0
        if str(input_data.get("tool_name") or "") != "Bash" or not gate_enabled():
            return 0
        command = command_from_input(input_data)
        if not command:
            return 0
        ledger = load_ledger(input_data)

        match = DESTRUCTIVE_RE.search(command)
        if match:
            surfaced = ledger.get("surfaced_ops")
            if not isinstance(surfaced, list):
                surfaced = []
            digest = command_hash(command)
            if digest not in surfaced and int(ledger.get("surfacing_blocks") or 0) < MAX_SURFACING_BLOCKS:
                surfaced.append(digest)
                ledger["surfaced_ops"] = surfaced[-40:]
                ledger["surfacing_blocks"] = int(ledger.get("surfacing_blocks") or 0) + 1
                save_ledger(input_data, ledger)
                emit_json(deny_payload(SURFACING_REASON.format(token=match.group(0).strip()[:60])))
                return 0

        if ledger.get("last_bash_failed"):
            digest = command_hash(command)
            bounced = ledger.get("retry_bounced")
            if not isinstance(bounced, list):
                bounced = []
            if digest == str(ledger.get("last_bash_cmd_hash") or "") and digest not in bounced and int(ledger.get("retry_blocks") or 0) < MAX_RETRY_BLOCKS:
                bounced.append(digest)
                ledger["retry_bounced"] = bounced[-40:]
                ledger["retry_blocks"] = int(ledger.get("retry_blocks") or 0) + 1
                save_ledger(input_data, ledger)
                emit_json(deny_payload(RETRY_REASON))
        return 0
    except Exception:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
