#!/usr/bin/env bash
# substrate-check — one-line deterministic snapshot of the gate substrate.
#
# The model-transition rehearsal: run this BEFORE and AFTER switching the
# reasoning model (or upgrading the harness). The substrate metrics must be
# identical (delta 0) — the gates don't know which model is driving. If any
# number moves, "model-independent harness" is a claim, not a measurement.
#
# Usage:   bash bench/substrate-check.sh            # print snapshot JSON
#          bash bench/substrate-check.sh > before.json
#          ...switch model / upgrade...
#          bash bench/substrate-check.sh > after.json && diff before.json after.json
#
# Output fields:
#   replay_blocked / replay_total — violation corpus block coverage
#   probes_pass / probes_total    — pipeline contract probes
#   hooks_present                 — gate scripts present in hooks/
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

replay_out="$(python3 "$ROOT/hooks/tests/replay/run.py" 2>/dev/null | tail -1)"
replay_blocked="$(printf '%s' "$replay_out" | sed -n 's/^replay: \([0-9]*\)\/\([0-9]*\).*/\1/p')"
replay_total="$(printf '%s' "$replay_out" | sed -n 's/^replay: \([0-9]*\)\/\([0-9]*\).*/\2/p')"

probe_out="$(python3 "$ROOT/hooks/tests/probes/run.py" 2>/dev/null | tail -1)"
probes_pass="$(printf '%s' "$probe_out" | sed -n 's/^probes: \([0-9]*\)\/\([0-9]*\).*/\1/p')"
probes_total="$(printf '%s' "$probe_out" | sed -n 's/^probes: \([0-9]*\)\/\([0-9]*\).*/\2/p')"

hooks_present="$(ls "$ROOT/hooks/"*.py 2>/dev/null | wc -l | tr -d ' ')"

printf '{"replay_blocked": %s, "replay_total": %s, "probes_pass": %s, "probes_total": %s, "hooks_present": %s}\n' \
  "${replay_blocked:-0}" "${replay_total:-0}" "${probes_pass:-0}" "${probes_total:-0}" "${hooks_present:-0}"
