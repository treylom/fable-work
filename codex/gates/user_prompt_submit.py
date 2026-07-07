#!/usr/bin/env python3
"""Codex UserPromptSubmit hook: lightweight ledger seeding for tofable gates."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from lib import default_ledger, gate_enabled, read_stdin_json, save_ledger
except Exception:
    raise SystemExit(0)


def main() -> int:
    try:
        input_data = read_stdin_json()
        if input_data and gate_enabled():
            save_ledger(input_data, default_ledger())
        return 0
    except Exception:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
