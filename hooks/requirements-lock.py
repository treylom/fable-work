#!/usr/bin/env python3
"""Stop — requirements-lock guard (optional gate).

Catches *completion bias*: "fixing" an error by quietly deleting the feature
that produced it. You lock a requirement by declaring a code signature that
must keep existing; if a locked signature disappears from the tree, the Stop
is bounced with the list of missing signatures.

Opt-in: create `requirements.lock` (JSON) at the project root. No file =
no-op (zero install friction). Format:

    {
      "requirements": [
        {"id": "gate-blocks-stop", "path": "hooks/stop-verify-gate.py",
         "pattern": "decision\\\"?:\\s*\\\"?block"},
        {"id": "ledger-atomic-write", "path": "hooks/fable_lib.py",
         "pattern": "os\\.replace\\("}
      ]
    }

- `path` — file relative to project root; missing file = requirement missing.
- `pattern` — regex searched in that file; no match = requirement missing.

Same Stop contract as stop-verify-gate.py: block via stdout JSON
{"decision":"block"} + exit 0, capped by stop_hook_active loop guard,
fail-open on internal errors (a broken guard must not brick the session).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

LOCK_NAME = "requirements.lock"


def main() -> int:
    try:
        input_data = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return 0
    if input_data.get("stop_hook_active"):
        return 0  # loop guard: never bounce twice in a row
    root = Path(input_data.get("cwd") or ".")
    lock_file = root / LOCK_NAME
    if not lock_file.exists():
        return 0  # opt-in gate: no lock file, no opinion
    try:
        lock = json.loads(lock_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0  # corrupt lock = fail-open (report path: fix the lock file)
    missing: list[str] = []
    for req in lock.get("requirements", []):
        rid = str(req.get("id") or "unnamed")
        target = root / str(req.get("path") or "")
        pattern = str(req.get("pattern") or "")
        if not target.is_file():
            missing.append(f"{rid} (file gone: {req.get('path')})")
            continue
        try:
            text = target.read_text(encoding="utf-8", errors="replace")
        except OSError:
            missing.append(f"{rid} (unreadable: {req.get('path')})")
            continue
        if pattern and not re.search(pattern, text):
            missing.append(f"{rid} (signature gone in {req.get('path')})")
    if not missing:
        return 0
    print(json.dumps({
        "decision": "block",
        "reason": (
            "requirements-lock: locked feature signatures are missing — "
            + "; ".join(missing[:5])
            + ". If a requirement was intentionally retired, remove it from "
            f"{LOCK_NAME} in the same change and say so; otherwise restore the feature. "
            "Deleting a feature to silence an error is not a fix."
        ),
    }))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)  # fail-open by design
