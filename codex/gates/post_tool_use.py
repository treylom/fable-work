#!/usr/bin/env python3
"""Codex PostToolUse hook: record tofable gate evidence only."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from lib import (
        SUBAGENT_TOOLS,
        add_unique,
        changed_kinds,
        changed_paths,
        command_from_input,
        command_hash,
        delegate_report_read,
        detect_failure,
        git_usage_record,
        load_ledger,
        read_stdin_json,
        save_ledger,
        verification_record,
    )
except Exception:
    raise SystemExit(0)


def main() -> int:
    try:
        input_data = read_stdin_json()
        if not input_data:
            return 0
        tool_name = str(input_data.get("tool_name") or "")
        kinds = changed_kinds(input_data)
        paths = changed_paths(input_data)
        verification = verification_record(input_data)
        failure = detect_failure(input_data)
        git_use = git_usage_record(input_data)
        bash_command = command_from_input(input_data) if tool_name == "Bash" else ""
        subagent = tool_name in SUBAGENT_TOOLS
        delegate_read = delegate_report_read(input_data)
        if not kinds and not verification and not failure and not git_use and not bash_command and not subagent and not delegate_read:
            return 0

        ledger = load_ledger(input_data)
        ledger["event_seq"] = int(ledger.get("event_seq") or 0) + 1
        seq = ledger["event_seq"]
        if kinds:
            ledger["changed_files_seen"] = True
            add_unique(ledger, "changed_paths", [path.strip() for path in paths if path])
            add_unique(ledger, "change_kinds", kinds)
            if any(kind in {"harness", "code", "config"} for kind in kinds):
                ledger["last_gated_seq"] = seq
        if verification:
            verification["seq"] = seq
            ledger["verification_results"].append(verification)
            ledger["verification_commands"].append(verification["command"])
        if failure:
            ledger["failures"].append(failure)
        if git_use:
            add_unique(ledger, "git_commands", [git_use["command"]])
            if git_use["boundary"]:
                ledger["boundary_expansion_seen"] = True
        if bash_command:
            ledger["last_bash_cmd_hash"] = command_hash(bash_command)
            ledger["last_bash_failed"] = bool(failure)
        if subagent:
            ledger["subagent_seq"] = seq
        if delegate_read:
            ledger["delegate_report_seq"] = seq
        save_ledger(input_data, ledger)
        return 0
    except Exception:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
