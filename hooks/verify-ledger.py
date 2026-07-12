#!/usr/bin/env python3
"""PostToolUse + PostToolUseFailure — fable verification-evidence ledger recorder.

fail-open: any exception exits 0 with no output (never blocks the work).
This hook only records; the Stop hook (stop-verify-gate.py) does the judging.

Wire it on BOTH PostToolUse and PostToolUseFailure: current Claude Code
routes failing tool calls to PostToolUseFailure only (verified empirically
2026-07-12 on 2.1.207 — a `bash -c 'exit 3'` never reached PostToolUse), so
a PostToolUse-only wiring is blind to failures: `failures[]` stays empty and
the blind-retry gate never arms on genuinely failed commands.

Origin: fable-ish-codex hooks/post_tool_use.py, adapted for Claude Code hooks.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from fable_lib import (
        SUBAGENT_TOOLS,
        add_unique,
        changed_kinds,
        changed_paths,
        classify_path_kind,
        command_from_input,
        delegate_report_read,
        detect_failure,
        git_usage_record,
        is_prose_path,
        load_ledger,
        read_stdin_json,
        redact,
        response_text,
        save_ledger,
        verification_record,
    )
    import hashlib
except Exception:
    sys.exit(0)


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
        if not failure and str(input_data.get("hook_event_name") or "") == "PostToolUseFailure":
            # Failure-event payloads don't always carry a parseable exit code —
            # the event itself is the failure signal (see module docstring).
            failure = {
                "kind": "tool-failure-event",
                "summary": redact(
                    response_text(input_data.get("tool_response", input_data), 240)
                    or command_from_input(input_data),
                    240,
                ),
            }
        git_use = git_usage_record(input_data)  # ledger v2 — absence-gate evidence
        bash_command = command_from_input(input_data) if tool_name == "Bash" else ""
        # ledger v4 — subordinate-evidence anchor. SubagentStop (the moment a
        # delegate actually returns) also arms it on harnesses that emit that
        # event — a strictly better anchor than the Task/Agent tool call.
        subagent = (
            tool_name in SUBAGENT_TOOLS
            or str(input_data.get("hook_event_name") or "") == "SubagentStop"
        )
        delegate_read = delegate_report_read(input_data)  # ledger v4.1 — file-mediated delegation
        if not kinds and not verification and not failure and not git_use and not bash_command and not subagent and not delegate_read:
            return 0  # nothing worth recording — ledger untouched

        ledger = load_ledger(input_data)
        ledger["event_seq"] = int(ledger.get("event_seq") or 0) + 1
        seq = ledger["event_seq"]
        if kinds:
            ledger["changed_files_seen"] = True
            add_unique(ledger, "changed_paths", [p.strip() for p in paths if p])
            add_unique(ledger, "change_kinds", kinds)
            if any(k in {"harness", "code", "config"} for k in kinds):
                ledger["last_gated_seq"] = seq
                # ledger v5.1 — only *executable* gated changes stale prior
                # verifications. Prose harness edits (.md rules/skills) keep
                # the audit trail but don't move the ordering anchor.
                if paths:
                    exec_gated = any(
                        classify_path_kind(p.strip()) in {"code", "config"}
                        or (classify_path_kind(p.strip()) == "harness" and not is_prose_path(p.strip()))
                        for p in paths if p
                    )
                else:
                    exec_gated = True  # mutating bash on harness surface — no path, stay conservative
                if exec_gated:
                    ledger["last_gated_exec_seq"] = seq
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
            # ledger v4 — blind-retry anchor: every Bash outcome updates the
            # (command hash, failed?) pair the PreToolUse retry gate reads.
            ledger["last_bash_cmd_hash"] = hashlib.sha256(
                bash_command.strip().encode("utf-8", "replace")
            ).hexdigest()[:16]
            ledger["last_bash_failed"] = bool(failure)
        if subagent:
            ledger["subagent_seq"] = seq  # ledger v4 — subordinate-evidence anchor
        if delegate_read:
            ledger["delegate_report_seq"] = seq  # ledger v4.1 — file-mediated delegation anchor
        save_ledger(input_data, ledger)
        return 0
    except Exception:
        return 0  # fail-open


if __name__ == "__main__":
    raise SystemExit(main())
