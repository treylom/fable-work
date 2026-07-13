#!/usr/bin/env python3
"""Scan Claude Code transcripts for REAL gate events (blocks/denies).

The measurement core of docs/gate-audit-playbook.md — extracted from a
live fleet weight audit (2026-07-13), where three naive approaches all
failed before this shape worked:

1. Grepping gate NAMES over-counts by exactly "number of documents that
   mention the gate" — sessions that read/discuss hook source quote every
   string you search for (self-contamination).
2. Silent passes leave NO transcript trace, so transcripts can only measure
   blocks, never fire rates. (Fire rates need hook-side audit logs.)
3. Even hook-side logs over-count visible friction: one bounced stop cycle
   can log several hook fires (measured 118 log lines vs 20 model-visible
   bounces for the same gate) — always label which side you are counting.

Real-event discriminators (measured, Claude Code 2.1.x):
- Stop-gate block  -> a user-type record whose content starts with
  "Stop hook feedback:" followed by the gate's reason text.
- PreToolUse deny  -> a tool_result record with "is_error":true containing
  the gate's reason text.

Usage:
    python3 scan_gate_events.py [--projects ~/.claude/projects] [--days 7]
        [--min-size 10000] [--signatures extra_sigs.json] [--out events.json]

extra_sigs.json: {"label": "distinctive reason-text substring", ...}
Default signatures cover the tofable gates. Add your own hooks' reason
strings — pick a substring of the BLOCK MESSAGE (not the hook's name).
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import time
from collections import defaultdict

# Substrings of the gates' *reason text* — not their names (pitfall 1).
DEFAULT_SIGS = {
    "stop-verify": "fable-gate: this turn changed",
    "absence": "fable-gate(absence)",
    "claim-evidence": "fable-gate(claim-evidence)",
    "subordinate-evidence": "fable-gate(subordinate-evidence)",
    "continuation": "continuation-gate: your final message",
    "surfacing": "surfacing-gate: this command contains",
    "blind-retry": "blind-retry-gate: this exact command",
    "prompt-advance": "prompt-advance-gate: this session crystallized",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--projects", default=os.path.expanduser("~/.claude/projects"))
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--min-size", type=int, default=10_000)
    ap.add_argument("--signatures", help="JSON file of {label: reason-substring}")
    ap.add_argument("--out", default="gate_events.json")
    args = ap.parse_args()

    sigs = dict(DEFAULT_SIGS)
    if args.signatures:
        with open(args.signatures, encoding="utf-8") as fh:
            sigs.update(json.load(fh))

    cutoff = time.time() - args.days * 86400
    counts: dict[tuple[str, str], int] = defaultdict(int)
    events: list[dict] = []

    for f in glob.glob(os.path.join(args.projects, "*", "*.jsonl")):
        if os.path.getmtime(f) < cutoff or os.path.getsize(f) < args.min_size:
            continue
        project = os.path.basename(os.path.dirname(f))
        try:
            with open(f, encoding="utf-8", errors="replace") as fh:
                for idx, line in enumerate(fh):
                    is_stop_block = '"Stop hook feedback:' in line
                    is_deny = '"is_error":true' in line or '"is_error": true' in line
                    if not (is_stop_block or is_deny):
                        continue
                    for label, sig in sigs.items():
                        i = line.find(sig)
                        if i < 0:
                            continue
                        counts[(project, label)] += 1
                        events.append({
                            "project": project,
                            "file": os.path.basename(f),
                            "line": idx + 1,
                            "gate": label,
                            "kind": "stop-block" if is_stop_block else "pretool-deny",
                            "excerpt": line[i:i + 300],
                        })
        except OSError:
            continue

    print(f"{'project':44} {'gate':22} {'events':>6}")
    for (project, label), n in sorted(counts.items()):
        print(f"{project[-44:]:44} {label:22} {n:>6}")
    print(f"\ntotal real events: {len(events)}")
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(events, fh, ensure_ascii=False, indent=1)
    print(f"details -> {args.out} (label each event true/false-positive by "
          f"reading what the agent did next — that is the value/noise ranking input)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
