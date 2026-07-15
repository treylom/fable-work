#!/usr/bin/env python3
"""PreToolUse (Write|Edit|MultiEdit|Task|Agent) — prompt-advance gate.

Workflow contract (owner decision 2026-07-08, interview 2-A "hard"):
    interview / brainstorm / plan  ->  role confirmed
        ->  prompt-engineering pass (/prompt or equivalent)
        ->  execute.

This gate enforces the third step ONCE per session: when the session
transcript shows a requirement-crystallizing phase happened (ouroboros
interview, brainstorming skill, plan mode exit) but NO prompt-engineering
evidence appears after it, the first execution-grade tool call (file
mutation or subagent dispatch) is bounced with a reminder. The identical
retry passes — the gate is a speed bump that makes skipping deliberate,
not a wall (MAX 1 bounce per session).

Natural exemptions:
- sessions with no interview/plan markers (trivial work) never trigger;
- automation/headless sessions are skipped via the same kill switch as the
  other gates (FABLE_GATE_OFF / FABLE_GATE_PILOT — note: no gate reads
  CLAUDE_AUTOMATION; an earlier draft of this docstring mentioned it and the
  2026-07-13 weight-audit D1 review caught the drift);
- fail-open on any exception.

Narrowed conditions (owner decision 2026-07-13, weight-audit ② — the 7-day
live audit measured 8 bounces with 0-1 visible behavior changes, all in
meeting-dispatched sessions where the task spec already arrived complete):
- meeting-SoT-engaged sessions are exempt: if the transcript shows work on a
  `meetings/*/02-progress.md`, the task was spec'd externally (dispatch
  carries the HOW) and a prompt pass adds nothing;
- only substantial calls gate: small edits (< MIN_MUTATION_CHARS of new
  content) and short dispatch prompts (< MIN_DISPATCH_CHARS) are not
  execution-grade starts.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from fable_lib import gate_enabled, load_ledger, read_stdin_json, save_ledger
except Exception:
    sys.exit(0)

GATED_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit", "Task", "Agent"}

# Narrowing thresholds (2026-07-13 weight-audit ②): below these, the call is
# an incidental mutation / probe dispatch, not an execution-grade start.
MIN_MUTATION_CHARS = 1500
MIN_DISPATCH_CHARS = 300

# Meeting-SoT engagement — matches the tool-call JSON for reads/edits of a
# meeting 02-progress file anywhere in the tail (order-independent: bots read
# the meeting SoT before or after the crystallizing marker).
MEETING_SOT_RE = re.compile(r"meetings/[^\"'\s]{0,160}02-progress\.md", re.IGNORECASE)

# Requirement-crystallizing phase happened. Invoke-shaped evidence only:
# loose substrings ("skill...interview") over-fire on injected rule/prose
# text that merely MENTIONS interviews (live-transcript probe, 2026-07-08).
ROLE_CONFIRM_RE = re.compile(
    r"ouroboros[:_]interview"
    r"|<command-name>[^<]{0,30}interview"
    r"|superpowers:brainstorming|\"skill\"\s*:\s*\"brainstorming\""
    r"|ExitPlanMode",
    re.IGNORECASE,
)
# Prompt-engineering pass evidence. Same discipline: only shapes a real
# invocation leaves in the transcript. A harness that injects guidance
# prose mentioning "/prompt" or the guide's filename must not silently
# satisfy the gate (self-pass vector measured live, 2026-07-08) — so we
# match the Read tool-call JSON, the command tag, the Skill-invoke JSON,
# and the batch-mode flag, not bare filenames.
PROMPT_PASS_RE = re.compile(
    r"file_path\"?\s*:\s*\"[^\"]*prompt-engineering-guide"
    r"|<command-name>\s*/?prompt\b"
    r"|\"skill\"\s*:\s*\"(?:prompt|image-prompt)\""
    r"|prompt\s+--batch",
    re.IGNORECASE,
)

# Planning-shaped USER directive (owner extension 2026-07-15, u18 card-art
# omission regression: an inline-authored expansion spec skipped the prompt
# pass and silently dropped an orthogonal axis — visual assets). A user line
# that asks for a plan/spec/expansion is itself requirement-crystallizing.
# Injection discipline: only lines that look like a real user message count,
# and lines carrying injected-guidance markers are stripped so rule-router
# gate text mentioning these words can never self-trigger.
PLANNING_DIRECTIVE_RE = re.compile(
    r"\uae30\ud68d\uc548|\uc124\uacc4\uc548|\uacc4\ud68d\uc11c"
    r"|\uc2a4\ud399\s*(?:\ubb38\uc11c)?\s*(?:\uc791\uc131|\uc0b0\ucd9c|\uc7a1|\uc9dc)"
    r"|\ub85c\ub4dc\ub9f5\s*(?:\uc791\uc131|\uc7a1|\ub9cc\ub4e4)"
    r"|(?:\uc2dc\uc2a4\ud15c|\ucf58\ud150\uce20|\uce74\ub4dc|\uae30\ub2a5)[^\n\"]{0,14}(?:\ud655\uc7a5|\ucd94\uac00)[^\n\"]{0,10}(?:\ud558\uc790|\uae30\ud68d|\uacc4\ud68d|\ub9de\ucd94)"
    r"|\uce74\ub4dc[^\n\"]{0,14}\ub9de\ucd94"
    r"|write\s+(?:a\s+)?(?:spec|design\s+doc|product\s+plan)"
    r"|draft\s+(?:a\s+)?(?:spec|proposal|plan)",
    re.IGNORECASE,
)
USER_LINE_RE = re.compile(r"\"type\"\s*:\s*\"user\"")
INJECTED_MARK_RE = re.compile(
    r"\U0001F6A8|\U0001F534|system-reminder|hook success|rule-router",
)


def _string_values(node: Any, budget: int = 200) -> list[str]:
    """All string leaves of a parsed JSON value (bounded, fail-open)."""
    out: list[str] = []
    stack = [node]
    while stack and len(out) < budget:
        cur = stack.pop()
        if isinstance(cur, str):
            out.append(cur)
        elif isinstance(cur, dict):
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)
    return out


def planning_directive_end(tail: str) -> int | None:
    """Last byte offset of a planning-shaped user directive, or None.

    Lines are json-parsed so escaped (ensure_ascii) and raw-UTF-8 transcripts
    both match. A line counts only if it is user-typed, its text carries no
    injected-guidance marker, and the planning pattern matches.
    """
    last: int | None = None
    offset = 0
    for line in tail.splitlines(keepends=True):
        end = offset + len(line)
        offset = end
        if '"user"' not in line and '\\"user\\"' not in line:
            continue
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(obj, dict) or obj.get("type") != "user":
            continue
        text = "\n".join(_string_values(obj))
        if INJECTED_MARK_RE.search(text):
            continue
        if PLANNING_DIRECTIVE_RE.search(text):
            last = end
    return last


REASON = (
    "prompt-advance-gate: this session crystallized a task (interview/"
    "brainstorm/plan) but no prompt-engineering pass has run since. The "
    "workflow is: role confirmed -> advance the prompt (/prompt or the "
    "prompt-engineering guide: structured prompt, expert priming, research/"
    "fact-check/image templates) -> execute. Run the prompt pass, or if this "
    "task genuinely doesn't need one, repeat the same call — it passes after "
    "this bounce."
)


def substantial(input_data: dict[str, Any]) -> bool:
    """Execution-grade calls only — incidental small edits and short probe
    dispatches never gate (measured friction, 2026-07-13)."""
    tool = str(input_data.get("tool_name") or "")
    tool_input = input_data.get("tool_input")
    if not isinstance(tool_input, dict):
        return True  # unknown shape — stay conservative
    if tool in {"Task", "Agent"}:
        return len(str(tool_input.get("prompt") or "")) >= MIN_DISPATCH_CHARS
    if tool == "Write":
        return len(str(tool_input.get("content") or "")) >= MIN_MUTATION_CHARS
    if tool == "Edit":
        return len(str(tool_input.get("new_string") or "")) >= MIN_MUTATION_CHARS
    if tool == "MultiEdit":
        edits = tool_input.get("edits")
        if not isinstance(edits, list):
            return True
        total = sum(
            len(str(e.get("new_string") or "")) for e in edits if isinstance(e, dict)
        )
        return total >= MIN_MUTATION_CHARS
    if tool == "NotebookEdit":
        return len(str(tool_input.get("new_source") or "")) >= MIN_MUTATION_CHARS
    return True


def transcript_tail(input_data: dict[str, Any], max_bytes: int = 400_000) -> str:
    path = str(input_data.get("transcript_path") or "")
    if not path:
        return ""
    try:
        raw = Path(path).read_bytes()
        return raw[-max_bytes:].decode("utf-8", "replace")
    except OSError:
        return ""


def main() -> int:
    try:
        input_data = read_stdin_json()
        if not input_data:
            return 0
        if str(input_data.get("tool_name") or "") not in GATED_TOOLS:
            return 0
        if not gate_enabled():
            return 0

        ledger = load_ledger(input_data)
        if ledger.get("prompt_gate_bounced"):
            return 0  # MAX 1 per session — retry (or any later call) passes

        tail = transcript_tail(input_data)
        if not tail:
            return 0

        confirm_matches = list(ROLE_CONFIRM_RE.finditer(tail))
        planning_end = planning_directive_end(tail)
        if not confirm_matches and planning_end is None:
            return 0  # no crystallizing phase — trivial work, gate silent

        # Meeting-SoT exemption applies ONLY to the role-confirm path: a
        # dispatched task arrives spec'd. A planning directive means the
        # spec does NOT exist yet (2026-07-15 u18 regression happened
        # inside a meeting-SoT session), so it is never exempt.
        if planning_end is None and MEETING_SOT_RE.search(tail):
            return 0  # meeting-dispatched work — the spec lives in the meeting SoT

        if not substantial(input_data):
            return 0  # incidental mutation / probe dispatch — not a start

        last_confirm = max(
            [m.end() for m in confirm_matches] + ([planning_end] if planning_end is not None else [])
        )
        if PROMPT_PASS_RE.search(tail, last_confirm):
            return 0  # prompt pass already ran after role confirmation

        ledger["prompt_gate_bounced"] = True
        save_ledger(input_data, ledger)
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": REASON,
            }
        }))
        return 0
    except Exception:
        return 0  # fail-open, always


if __name__ == "__main__":
    sys.exit(main())
