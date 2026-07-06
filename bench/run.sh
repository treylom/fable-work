#!/bin/bash
# fable-bench runner — executes ONE fixture against a specified model in a
# headless Claude Code session and preserves the raw transcript for judging.
#
# usage: run.sh <fixture-name> <model> [run_tag] [harness]
#
#   harness: "vanilla" (default) — stock headless session, no fable material
#            "tofable"           — the A/B arm: injects the three rules files
#                                  via --append-system-prompt AND wires the
#                                  four hooks through a run-local settings
#                                  file, with FABLE_STATE_DIR isolated inside
#                                  the run directory. Everything else is
#                                  identical between arms.
#            "tofable-compact"   — same hooks as "tofable", but injects the
#                                  imperative-checklist rule variant from
#                                  rules/compact/ (arm for models that do
#                                  not translate prose rules into behavior).
#            "tofable-v4"        — "tofable" plus the ledger-v4 gates mined
#                                  from source-model work logs: blind-retry
#                                  (PreToolUse) and the Task|Agent ledger
#                                  matcher that arms the subordinate-evidence
#                                  Stop check. Kept as a separate arm so the
#                                  v4 delta is measurable against "tofable".
#
# Environment isolation: every arm runs with --setting-sources "" and
# --strict-mcp-config, so the host user's settings (hooks, plugins, memory
# injections, global CLAUDE.md) and MCP servers never leak into the session
# under test. Verified empirically (cycle3 postmortem): without these flags
# the session inherits the host's SessionStart hooks and full MCP tool
# surface — one host MCP server ships an instruction block that a model
# under test correctly reported as an injection attempt, and the judge,
# blind to the host environment, mis-graded that report as fabrication.
# A run-local --settings file still applies under --setting-sources ""
# (probed), which is how the tofable hooks get wired.
#
# Env vars:
#   FABLE_BENCH_DIR      Directory containing fixture subfolders
#                        (default: ./fixtures next to this script)
#   FABLE_BENCH_RUNS_DIR Where run artifacts are written
#                        (default: $HOME/.fable-bench/runs)
#
# Output: $FABLE_BENCH_RUNS_DIR/<timestamp>-<fixture>-<tag>/
#   work/             fixture copy the model actually worked in
#                     (ANSWER-KEY.md and materialize.sh are excluded — the
#                     model under test never sees the graded answer or the
#                     trap-planting logic)
#   transcript.jsonl  full stream-json tool-use transcript (behavioral
#                     evidence for judging — not just the final answer)
#   raw-output.json   the transcript's final "result" event, plus a
#                     tool_use_count derived from the transcript
#   stderr.log        stderr from the run
#   meta.json         run metadata (fixture, model, exit code, duration,
#                     cost, turn count, etc.)
set -euo pipefail

FIXTURE="${1:?usage: run.sh <fixture> <model> [run_tag] [harness]}"
MODEL="${2:?usage: run.sh <fixture> <model> [run_tag] [harness]}"
TAG="${3:-run}"
HARNESS="${4:-vanilla}"
case "$HARNESS" in vanilla|tofable|tofable-compact|tofable-v4) ;; *) echo "harness must be vanilla|tofable|tofable-compact|tofable-v4" >&2; exit 1;; esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
FABLE_BENCH_DIR="${FABLE_BENCH_DIR:-$SCRIPT_DIR/fixtures}"
FABLE_BENCH_RUNS_DIR="${FABLE_BENCH_RUNS_DIR:-$HOME/.fable-bench/runs}"

SRC="$FABLE_BENCH_DIR/$FIXTURE"
[ -d "$SRC" ] || { echo "no fixture: $SRC" >&2; exit 1; }

TS="$(date +%Y%m%dT%H%M%S)"
RUN="$FABLE_BENCH_RUNS_DIR/$TS-$FIXTURE-$TAG"
mkdir -p "$RUN"

# Copy the fixture into the run's working dir. Exclude the answer key and
# the materialize script so the model under test never sees the graded
# answer or the trap-planting logic.
rsync -a --exclude 'ANSWER-KEY.md' --exclude 'materialize.sh' "$SRC/" "$RUN/work/"

# Some fixtures plant traps (secrets, decoys, off-limits paths, etc.) at
# runtime instead of storing that content in the repo, so the repo itself
# never contains the planted material. If the fixture ships a
# materialize.sh, run it now against the run's working dir.
if [ -x "$SRC/materialize.sh" ]; then bash "$SRC/materialize.sh" "$RUN/work"; fi

# The tofable arm: same session, plus the three rules injected into the
# system prompt and the four hooks wired via a run-local settings file.
# Ledger state is isolated per run (FABLE_STATE_DIR inside the run dir) so
# arms never share bounce/evidence bookkeeping.
EXTRA_ARGS=()
if [ "$HARNESS" = "tofable" ] || [ "$HARNESS" = "tofable-compact" ] || [ "$HARNESS" = "tofable-v4" ]; then
  RULES_DIR="$REPO_DIR/rules"
  [ "$HARNESS" = "tofable-compact" ] && RULES_DIR="$REPO_DIR/rules/compact"
  RULES="$(cat "$RULES_DIR/verification.md" "$RULES_DIR/delegation.md" "$RULES_DIR/continuation.md")"
  python3 - "$RUN" "$REPO_DIR" "$HARNESS" <<'PY'
import json, sys, pathlib
run, repo, harness = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
hooks = lambda name: f"python3 {repo}/hooks/{name}"
v4 = harness == "tofable-v4"
pre = [{"type": "command", "command": hooks("surfacing-gate.py")}]
if v4:
    pre.append({"type": "command", "command": hooks("blind-retry-gate.py")})
settings = {
    "hooks": {
        "PreToolUse": [{"matcher": "Bash", "hooks": pre}],
        "PostToolUse": [{
            "matcher": "Write|Edit|Bash|Task|Agent" if v4 else "Write|Edit|Bash",
            "hooks": [{"type": "command", "command": hooks("verify-ledger.py")}],
        }],
        "Stop": [{"hooks": [
            {"type": "command", "command": hooks("stop-verify-gate.py")},
            {"type": "command", "command": hooks("continuation-gate.py")},
        ]}],
    }
}
(run / "tofable-settings.json").write_text(json.dumps(settings, indent=2))
PY
  EXTRA_ARGS+=(--append-system-prompt "$RULES" --settings "$RUN/tofable-settings.json")
  export FABLE_STATE_DIR="$RUN/fable-state"
fi

START=$(date +%s)
set +e
# --output-format stream-json preserves the full tool-execution transcript,
# not just the closing message — the judge needs behavioral evidence (what
# was actually run, checked, verified), not only the final self-report.
# --setting-sources "" + --strict-mcp-config: see "Environment isolation"
# in the header. stdin is redirected from /dev/null so the CLI doesn't
# wait 3s probing for piped input on every run.
( cd "$RUN/work" && claude -p "$(cat TASK.md)" \
    --model "$MODEL" \
    --dangerously-skip-permissions \
    --setting-sources "" \
    --strict-mcp-config \
    ${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"} \
    --output-format stream-json --verbose ) < /dev/null > "$RUN/transcript.jsonl" 2> "$RUN/stderr.log"
CODE=$?
set -e
DUR=$(( $(date +%s) - START ))

# Extract the transcript's final "result" event -> raw-output.json. Keeping
# this as a separate, stable file means downstream scoring/judging code
# doesn't need to parse the full transcript format directly.
python3 - "$RUN" <<'PY'
import json, sys, pathlib
run = pathlib.Path(sys.argv[1])
result_obj, tool_uses = None, 0
tr = run / "transcript.jsonl"
if tr.exists():
    for line in tr.read_text().splitlines():
        try:
            d = json.loads(line)
        except Exception:
            continue
        t = d.get("type")
        if t == "result":
            result_obj = d
        elif t == "assistant":
            msg = d.get("message") or {}
            for c in (msg.get("content") or []):
                if isinstance(c, dict) and c.get("type") == "tool_use":
                    tool_uses += 1
if result_obj is not None:
    result_obj["tool_use_count"] = tool_uses
    (run / "raw-output.json").write_text(json.dumps(result_obj, ensure_ascii=False, indent=2))
PY

python3 - "$RUN" "$FIXTURE" "$MODEL" "$CODE" "$DUR" "$HARNESS" <<'PY'
import json, sys, pathlib
run, fixture, model, code, dur, harness = sys.argv[1:7]
meta = {
    "schema_version": 2, "proof_class": "fixture-run",
    "fixture": fixture, "model": model, "harness": harness,
    "exit_code": int(code), "duration_sec": int(dur), "run_dir": run,
}
p = pathlib.Path(run)
raw = p / "raw-output.json"
if raw.exists():
    try:
        d = json.loads(raw.read_text())
        meta["result_chars"] = len(d.get("result", "") or "")
        meta["num_turns"] = d.get("num_turns")
        meta["total_cost_usd"] = d.get("total_cost_usd")
        meta["model_reported"] = (d.get("modelUsage") and list(d["modelUsage"].keys())) or None
    except Exception as e:
        meta["raw_parse_error"] = str(e)
(p / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))
print(json.dumps(meta, ensure_ascii=False))
PY
