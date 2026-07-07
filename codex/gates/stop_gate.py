#!/usr/bin/env python3
"""Codex Stop hook: single dispatcher for tofable stop-time gates."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from lib import (
        block_payload,
        emit_json,
        final_text_from_input,
        gate_enabled,
        load_ledger,
        read_stdin_json,
        save_ledger,
        should_block_absence,
        should_block_claim_evidence,
        should_block_continuation,
        should_block_subordinate_evidence,
        should_block_unverified_change,
    )
except Exception:
    raise SystemExit(0)


def main() -> int:
    try:
        input_data = read_stdin_json()
        if not input_data or input_data.get("stop_hook_active") is True or not gate_enabled():
            return 0
        ledger = load_ledger(input_data)
        final_text = final_text_from_input(input_data)

        checks = (
            ("stop_blocks", should_block_unverified_change),
            ("absence_blocks", lambda led: should_block_absence(led, final_text)),
            ("claim_blocks", lambda led: should_block_claim_evidence(led, final_text)),
            ("subagent_blocks", lambda led: should_block_subordinate_evidence(led, final_text)),
            ("continuation_blocks", lambda led: should_block_continuation(led, final_text)),
        )
        for counter, check in checks:
            block, reason = check(ledger)
            if block:
                ledger[counter] = int(ledger.get(counter) or 0) + 1
                save_ledger(input_data, ledger)
                emit_json(block_payload(reason))
                return 0
        return 0
    except Exception:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
