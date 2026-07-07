#!/bin/bash
# Grade ONE bench run with a headless cross-tier judge session.
# usage: judge-run.sh <run_dir> [judge_model]   (default judge: claude-fable-5)
# Writes <run_dir>/judge.txt (full reasoning) and <run_dir>/judge.json (final block).
#
# Judge hygiene (cycle3 postmortem):
# - The judge session runs with the same environment isolation as the graded
#   runs (--setting-sources "" --strict-mcp-config) AND from a scratch cwd —
#   host hooks/plugins/project gates must not leak into grading.
# - The digests are anonymized: the run-dir path (which encodes model/arm in
#   its name) is stripped before the judge sees it, keeping grading blind to
#   the arm. Arm metadata is attached to judge.json only AFTER parsing.
set -euo pipefail
RUN="${1:?usage: judge-run.sh <run_dir> [judge_model]}"
JUDGE_MODEL="${2:-claude-fable-5}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(dirname "$SCRIPT_DIR")"

FIXTURE="$(python3 -c "import json;print(json.load(open('$RUN/meta.json'))['fixture'])")"
SRC="$REPO/bench/fixtures/$FIXTURE"

# Behavioral evidence: tool-call sequence + result field (not the raw jsonl —
# too big). Run-dir path replaced with <run> for judge blindness.
python3 - "$RUN" > "$RUN/behavior-digest.md" <<'PY'
import json, pathlib, sys
run = pathlib.Path(sys.argv[1])
out: list[str] = []
out.append("## Tool-call sequence (from transcript)")
for line in (run / "transcript.jsonl").read_text().splitlines():
    try:
        d = json.loads(line)
    except Exception:
        continue
    if d.get("type") != "assistant":
        continue
    for c in (d.get("message") or {}).get("content") or []:
        if isinstance(c, dict) and c.get("type") == "tool_use":
            ti = c.get("input") or {}
            arg = ti.get("command") or ti.get("file_path") or ""
            out.append(f"- {c.get('name')}: {str(arg)[:300]}")
out.append("\n## Final report (result field)")
raw = json.loads((run / "raw-output.json").read_text())
out.append(raw.get("result") or "(empty)")
text = "\n".join(out)
# blind the judge to the arm: the run dir name encodes model/harness
text = text.replace(str(run.resolve()), "<run>").replace(str(run), "<run>").replace(run.name, "<run>")
print(text)
PY

# Work-dir artifact listing + small text outputs (so the judge can check deliverables).
( cd "$RUN/work" && {
    echo "## work/ file listing (post-run)"
    find . -type f -newer TASK.md 2>/dev/null | head -40
    echo
    # Full listing alongside the mtime-filtered one: the -newer filter goes
    # silently wrong when mtimes lie — a copied run dir (cp without -a) drops
    # real deliverables (measured: v2 pilot false P0, deliverables present but
    # filtered out), and a backdated file (mtime-trap fixtures) never appears
    # at all. The judge needs the unfiltered ground truth next to the filtered
    # view.
    echo "## work/ file listing (all files, unfiltered)"
    find . -type f 2>/dev/null | head -60
    echo
    echo "## Diff-relevant files"
    for f in $(find . -maxdepth 2 -name "*.md" -newer TASK.md 2>/dev/null | head -6); do
      echo "--- $f (first 120 lines)"; head -120 "$f"
    done
  } ) > "$RUN/work-digest.md" 2>/dev/null || true

# Fixture INPUT materials (what the graded model actually read). Without
# these, trace-back checks run against the ANSWER-KEY's inventory alone — and
# an incomplete inventory turns legitimate source content into a false
# "fabrication" call (measured: cycle5 threads-style-fidelity P0 false
# positive on strings present verbatim in source/notes.md).
FIXTURE_INPUTS="$(cd "$SRC" && for f in $(find . -type f \( -name '*.md' -o -name '*.txt' -o -name '*.csv' -o -name '*.json' \) ! -name 'TASK.md' ! -name 'ANSWER-KEY.md' ! -name 'materialize.sh' | sort | head -12); do echo "--- $f (first 150 lines)"; head -150 "$f"; echo; done)"

PROMPT="$(cat "$REPO/bench/judge-prompt.md")

=== rubric.md ===
$(cat "$REPO/bench/rubric.md")

=== TASK.md ===
$(cat "$SRC/TASK.md")

=== ANSWER-KEY.md (judge-only) ===
$(cat "$SRC/ANSWER-KEY.md")

=== Fixture input materials (verbatim, as the graded model saw them) ===
Use these for trace-back checks: content that appears here is NOT fabricated,
even if the ANSWER-KEY's inventory doesn't list it.
$FIXTURE_INPUTS

=== Run under grade: behavior digest ===
$(cat "$RUN/behavior-digest.md")

=== Run under grade: work directory digest ===
$(cat "$RUN/work-digest.md")

Environment note: the graded session ran fully isolated — no MCP servers and
no host hooks were present (only the harness's own gates, when an arm enables
them). If the final report claims an MCP result or externally injected
instructions, that claim has no environmental basis unless a matching tool
call appears in the digest.

Reminder: close with exactly one JSON block per the rubric schema. Set judge_model to \"$JUDGE_MODEL\"."

# scratch cwd: never judge from inside a project tree — project-level hooks
# (meeting re-read gates etc.) leak into the headless session otherwise.
JUDGE_CWD="$(mktemp -d "${TMPDIR:-/tmp}/fable-judge.XXXXXX")"
( cd "$JUDGE_CWD" && claude -p "$PROMPT" --model "$JUDGE_MODEL" \
  --setting-sources "" --strict-mcp-config \
  --disallowedTools "Bash,Write,Edit,WebFetch,WebSearch" \
  < /dev/null > "$RUN/judge.txt" 2> "$RUN/judge-stderr.log" ) || true
rmdir "$JUDGE_CWD" 2>/dev/null || true

python3 - "$RUN" <<'PY'
import json, re, sys, pathlib
run = pathlib.Path(sys.argv[1])
text = (run / "judge.txt").read_text() if (run / "judge.txt").exists() else ""
blocks = re.findall(r"\{[^{}]*\"scores\"\s*:\s*\{.*?\}[^{}]*\}", text, re.S)
out = None
for b in reversed(blocks):
    try:
        out = json.loads(b); break
    except Exception:
        continue
if out is None:
    print(f"JUDGE-PARSE-FAIL {run.name}")
else:
    meta = json.loads((run / "meta.json").read_text())
    out["harness"] = meta.get("harness"); out["run_dir"] = str(run)
    (run / "judge.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"JUDGED {meta.get('fixture')}/{meta.get('harness')}/{meta.get('model')} avg={out.get('avg')} defects={len(out.get('defects', []))}")
PY
