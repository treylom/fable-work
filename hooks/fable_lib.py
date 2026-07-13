#!/usr/bin/env python3
"""fable verification-gate hooks — shared library.

Adapted from fable-ish-codex (Apache-2.0, Pandoll-AI)
scripts/ledger.py / parse_tool_result.py / verify_state.py, ported to run as
Claude Code hooks (PostToolUse + Stop).

Adaptation notes:
- No task classifier ported. Instead a lightweight "harness/code surface"
  heuristic (see HARNESS_SURFACE_RE / CODE_EXTS / CONFIG_EXTS below) decides
  which changed files require verification evidence. Plain docs (e.g. notes,
  markdown content outside the harness surface) are exempt.
- FAILURE_RE deliberately excludes the bare words `failed`/`failure` — an
  earlier version matched those and produced false positives on ordinary
  tool output that merely mentions "failed" in prose.
- Ledger state lives outside the project working tree by default (see
  data_root()) so verification bookkeeping never gets committed or synced
  alongside the project's own content.
- Pilot gate: disabled entirely via FABLE_GATE_OFF=1 (kill switch).
  Optionally scoped to one named session via FABLE_GATE_PILOT=<name>
  together with FABLE_SESSION_NAME=<name> on the session side, so a project
  can pilot the gate on a single bot/session before enabling it broadly.
  With neither env var set, the gate is active for every session.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MAX_STOP_BLOCKS = 2
MAX_ABSENCE_BLOCKS = 1
MAX_CLAIM_BLOCKS = 1
MAX_SUBAGENT_BLOCKS = 1
MAX_RETRY_BLOCKS = 5  # session-wide cap for the blind-retry gate (false-positive friction bound)

DEFAULT_LEDGER: dict[str, Any] = {
    "changed_files_seen": False,
    "changed_paths": [],
    "change_kinds": [],
    "verification_commands": [],
    "verification_results": [],
    "failures": [],
    "stop_blocks": 0,
    "continuation_blocks": 0,  # continuation-gate bounce count (deferral-language check)
    "surfacing_blocks": 0,     # surfacing-gate bounce count (destructive-op check)
    "surfaced_ops": [],        # hashes of destructive commands already bounced once
    "git_commands": [],        # git usage this session (absence-gate evidence — ledger v2)
    "boundary_expansion_seen": False,  # git looked beyond the checked-out tree (--all / branch -a / …)
    "absence_blocks": 0,       # absence-gate bounce count
    "claim_blocks": 0,         # claim-evidence gate bounce count (ledger v3)
    # --- ledger v4 (fable log-mining, 2026-07-07: C3 blind-retry / C5 subordinate-evidence) ---
    "last_bash_cmd_hash": "",  # hash of the most recent Bash command (retry-chain anchor)
    "last_bash_failed": False, # whether that command's output carried a failure signal
    "retry_bounced": [],       # command hashes already bounced once by the blind-retry gate
    "retry_blocks": 0,         # blind-retry-gate bounce count
    "subagent_seq": 0,         # event_seq of the most recent Task/Agent (subagent) call
    "delegate_report_seq": 0,  # event_seq of the most recent delegate-report file Read (v4.1)
    "subagent_blocks": 0,      # subordinate-evidence gate bounce count
    # --- ledger v5 (2026-07-08: prompt-advance gate — interview→prompt→execute) ---
    "prompt_gate_bounced": False,  # the single prompt-advance bounce already spent
    "event_seq": 0,          # monotonic event counter (code-review feedback — closes the
                              # "verify succeeds, then code changes" ordering bypass)
    "last_gated_seq": 0,     # event_seq of the most recent gated (harness/code) change
    # --- ledger v5.1 (2026-07-12 log-mining: 542-ledger readout) ---
    "last_gated_exec_seq": 0,  # event_seq of the most recent *executable* gated change
                               # (code/config/settings, or non-prose harness file) —
                               # the ordering anchor verification staleness is judged
                               # against; prose harness edits (.md rules/skills) no
                               # longer stale prior verifications
    # --- ledger v5.2 (2026-07-13 weight-audit ② — measured re-bounce / double-deny friction) ---
    "changed_path_seqs": {},   # path -> event_seq of its most recent change (current-turn scoping)
    "stop_bounced_sets": [],   # digests of unverified path-sets already bounced once
    "surfacing_pending_token": "",  # just-surfaced destructive token — one recomposition passes
    "surfacing_pending_paths": [],  # path args of the bounced command (target-overlap guard)
    "last_updated": "",
}

SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*['\"]?[^'\"\s]+"),
    re.compile(r"sk-[A-Za-z0-9_-]{12,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9_]{12,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{12,}"),
]

CODE_EXTS = {".py", ".sh", ".js", ".mjs", ".ts", ".tsx", ".jsx", ".rb", ".go", ".rs", ".c", ".cc", ".cpp", ".java", ".swift", ".sql", ".css", ".scss", ".php", ".kt", ".kts", ".dart", ".cs", ".ex", ".exs", ".hs", ".scala", ".tf", ".proto", ".html"}
CONFIG_EXTS = {".json", ".jsonc", ".toml", ".yaml", ".yml", ".ini", ".cfg", ".conf", ".plist", ".lock"}

# Harness surface = changes here are gated regardless of extension (rules,
# hooks, scripts, skills, commands, agents, and the settings files).
HARNESS_SURFACE_RE = re.compile(r"(^|/)\.claude/(hooks|scripts|skills|rules|commands|agents)/|(^|/)settings(\.local)?\.json$")

VERIFY_RE = re.compile(
    r"(?i)\b("
    r"pytest|unittest|go\s+test|cargo\s+test|npm\s+test|pnpm\s+test|yarn\s+test|vitest|jest|playwright|"
    r"lint|eslint|ruff|flake8|mypy|pyright|tsc|typecheck|"
    # test_*.py counts as verification only when *executed* (python3 anchor) —
    # `cat`/`grep` of a test file is reading, not verifying. `./test_x.py`
    # direct-exec is not matched (the leading \b can't sit before a dot);
    # rare enough to leave out rather than weaken the anchor.
    r"bash\s+-n|zsh\s+-n|sh\s+-n|py_compile|json\.tool|python3?\s+-m\s+unittest|python3?\s+(?:[^\s]*/)?test_[a-z0-9_]+\.py|"
    r"build|check|validate|verify|diff|shasum|md5|grep\s+-c|wc\s+-l|curl"
    r")\b"
)
DIRECT_TEST_RE = re.compile(r"(?i)(pytest|unittest|vitest|jest|playwright|go\s+test|cargo\s+test)")
# bare `failed|failure` intentionally excluded — see module docstring.
FAILURE_RE = re.compile(
    r"(?i)(command not found|no such file or directory|traceback|syntaxerror|"
    r"\berror:|\b[1-9][0-9]*\s+errors?\b|exit code\s*:?\s*[1-9]|exited with code\s*:?\s*[1-9]|"
    r"tests? failed|build failed|lint failed|assertion(?:error)? failed)"
)
EXIT_ZERO_RE = re.compile(r"(?i)\b(exit code|exited with code|process exited with code)\s*:?\s*0\b")
SUCCESS_RE = re.compile(r"(?i)\b(passed|success(?:fully)?|succeeded|0 failed|compiled successfully|built successfully|build succeeded|ok|green|valid)\b")
MUTATING_BASH_RE = re.compile(r"(?i)\b(chmod|mkdir|mv|cp|rm|touch|tee|sed\s+-i|launchctl|npm\s+run\s+build|git\s+(add|commit|push|reset))\b")
# --- absence-gate evidence (ledger v2) ---
# Any git invocation counts as "consulted repository state"; the boundary
# pattern marks the subset that looked beyond the checked-out tree. The gate
# only arms when the first is present without the second (see
# should_block_absence) — sessions that never touch git are out of scope.
# `git\s+\S` (not `[a-z]`): real investigation commands often lead with
# global options (`git -C repo log …`) — an alpha anchor missed exactly the
# command shape observed in cycle3 runs.
GIT_USAGE_RE = re.compile(r"(?i)(?:^|[|;&`(\s])git\s+\S")
BOUNDARY_EXPANSION_RE = re.compile(
    r"(?i)\bgit\b[^\n|;&]{0,140}?(?:--all\b|\bbranch\s+-(?:a|av|avv|va|r)\b|\bbranch\s+--all\b|\bls-files\b|\bshow-ref\b|\bfor-each-ref\b|\bstash\s+list\b|\breflog\b)"
)
# Absence claims about repository/corpus artifacts (not generic "no issues").
_ABSENCE_ART = r"(?:files?|branch(?:es)?|commits?|history|implementations?|modules?|versions?|cop(?:y|ies)|logic|code|codebase|tests?|references?|mentions?|records?|definitions?|configs?|handlers?|handling|usages?|occurrences?|functions?|classes?)"
ABSENCE_CLAIM_RE = re.compile(
    r"(?i)(?:"
    rf"there\s+(?:is|are|was|were)\s+no[\w\s,'-]{{0,40}}?\b{_ABSENCE_ART}\b"
    rf"|\bno\s+(?:other|prior|existing|such|additional|further|hidden|remaining)\b[\w\s,'-]{{0,30}}?\b{_ABSENCE_ART}\b"
    rf"|\b{_ABSENCE_ART}\b[^.\n]{{0,40}}?(?:doesn'?t|does\s+not|do\s+not|don'?t)\s+exist"
    r"|\bnothing\s+(?:else|hiding|more\s+to|beyond|prior)\b"
    r"|\bnot\s+(?:present|found)\s+anywhere\b"
    r"|(?:파일|브랜치|코드|구현|이력|기록|모듈|버전|사본|테스트|참조)[^.\n]{0,25}(?:없|존재하지\s*않)"
    r")"
)
# --- claim-evidence gate (ledger v3 — cycle4 defect readout) ---
# Two claim shapes that cycle4 judges repeatedly dinged when made without a
# mechanical check in the tool log: (a) precise COUNT claims about measured
# artifacts (digest off-by-one: "84 body messages" from a manual read-through),
# (b) IDENTITY claims ("byte-for-byte identical" with no diff/checksum run).
# Kept deliberately narrow: bare small numbers in prose ("3단계로 진행")
# don't match — the count shape requires a measured-artifact noun, and the
# 총/exactly/정확히 qualifiers or N>=3 anchor the "this was counted" reading.
# The Korean generic counter 개 alone is everyday phrasing ("카드 3개"), not a
# measurement claim (2026-07-13 rereview C1): it needs a specific noun
# attached ("3개의 파일") — except under an explicit total/exact qualifier,
# which anchors the counted reading by itself ("총 83개").
_COUNT_NOUN_CORE = r"lines?|rows?|files?|entries|messages?|records?|matches|occurrences?|commits?|tests?|items?|줄|행|파일|건"
_COUNT_NOUN = rf"(?:{_COUNT_NOUN_CORE}|개(?:의)?\s*(?:파일|메시지|줄|행|기록|항목|테스트|커밋))"
_COUNT_NOUN_QUALIFIED = rf"(?:{_COUNT_NOUN_CORE}|개(?:의)?\s*(?:파일|메시지|줄|행|기록|항목|테스트|커밋)?)"
_NUM_GE3 = r"(?:[3-9]|[1-9][0-9][0-9,]*|[1-9][0-9])"  # 3+ (1–2 in prose is usually self-knowledge, not a measurement)
_ADJ1 = r"(?:[A-Za-z가-힣-]+\s+)?"  # one optional adjective — "84 body messages", "87 timestamped lines"
COUNT_CLAIM_RE = re.compile(
    r"(?i)(?:"
    rf"(?:총|전체|모두\s*합쳐|정확히|exactly|in\s+total|a\s+total\s+of)\s*[0-9][0-9,]*\s*{_ADJ1}{_COUNT_NOUN_QUALIFIED}"
    rf"|\b{_NUM_GE3}\s+{_ADJ1}{_COUNT_NOUN}"
    rf"|\b{_NUM_GE3}\s*(?=[가-힣]){_COUNT_NOUN}"
    r")"
)
IDENTITY_CLAIM_RE = re.compile(
    r"(?i)(?:byte[- ]?(?:for[- ]?byte|identical)|identical\s+to|exact\s+match(?:es)?|"
    r"완전히\s*동일|정확히\s*일치|바이트\s*단위로?\s*동일|동일함이?\s*확인)"
)
# Mechanical evidence = a counting/compare command in this session's recorded
# verification_commands (VERIFY_RE already admits these shapes into the ledger).
MECH_EVIDENCE_RE = re.compile(
    r"(?i)\b(wc\s+-[lwc]|grep\s+-[a-z]*c|diff|cmp|comm|shasum|sha256sum|md5(?:sum)?|"
    r"uniq\s+-c|sort\s+.*\|\s*uniq|find\s+.*\|\s*wc|ls\s+.*\|\s*wc|len\()"
)
# --- subordinate-evidence gate (ledger v4 — fable log-mining C5) ---
# Failure axis with the worst recurrence in the incident corpus (2026-07-07,
# 68 incidents): trusting a subagent/tool "done/success" as the completion
# basis — 5 recurrences of tool-less fake "success" text, 3 of "Connected"
# false-greens, 6 days of unverified "✓ sent". The mined fable behavior is
# the inverse: after a delegate reports, re-derive the claim independently
# (re-run the test, stat the artifact, grep the output) before accepting.
SUBAGENT_TOOLS = {"Task", "Agent"}
# File-mediated delegation (ledger v4.1 — the cycle6 coverage gap): much of
# real delegation reports back through a file, not a Task/Agent return value.
# Anchor on Read of a path that names itself a delegate's report — kept
# conservative by convention (worker-report.md, delegate_report.txt, ...) so
# ordinary reads never arm the gate. Read-only on purpose: a Bash command can
# read AND verify in one event (same seq), which the strictly-after
# verification check would then miss.
DELEGATE_REPORT_PATH_RE = re.compile(r"(?i)(?:worker|delegate|subagent)[-_]?report")
# Completion-claim shapes for the final reply (kept light — the mechanical
# anchor is "a subagent ran and nothing was verified after it").
COMPLETION_CLAIM_RE = re.compile(
    r"(?i)(?:\b(?:done|complete[d]?|finished|delivered|shipped|all\s+set)\b"
    r"|✅|\bGREEN\b|\bCLEAN\b"
    r"|완료|끝났|마쳤|마무리|성공적으로|반영(?:됐|되었)|처리(?:됐|되었))"
)

SUCCESS_STATUSES = {"success", "succeeded", "completed", "complete", "ok", "passed", "pass"}
FAILURE_STATUSES = {"failed", "failure", "error", "errored", "fatal", "timeout", "timed_out"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def redact(text: Any, limit: int = 500) -> str:
    value = "" if text is None else str(text)
    value = value.replace("\r", " ").replace("\n", " ").strip()
    for pattern in SECRET_PATTERNS:
        value = pattern.sub("[REDACTED]", value)
    if len(value) > limit:
        return value[: limit - 3] + "..."
    return value


def data_root() -> Path:
    """Ledger storage root.

    Override with FABLE_STATE_DIR. Default: XDG_STATE_HOME (or
    ~/.local/state if unset) / tofable / ledger — i.e. outside any
    project working tree by default.
    """
    env = os.environ.get("FABLE_STATE_DIR")
    if env:
        base = Path(env).expanduser()
    else:
        xdg = os.environ.get("XDG_STATE_HOME")
        state_home = Path(xdg).expanduser() if xdg else Path.home() / ".local" / "state"
        base = state_home / "tofable" / "ledger"
    return base.resolve()


def ledger_key(input_data: dict[str, Any]) -> str:
    cwd = input_data.get("cwd") or os.getcwd()
    session_id = input_data.get("session_id") or "no-session"
    return hashlib.sha256(f"{session_id}|{cwd}".encode("utf-8", "replace")).hexdigest()[:24]


def ledger_path(input_data: dict[str, Any]) -> Path:
    return data_root() / "ledgers" / f"{ledger_key(input_data)}.json"


def default_ledger() -> dict[str, Any]:
    return copy.deepcopy(DEFAULT_LEDGER)


_LEDGER_LOCKS: dict[str, Any] = {}


def _acquire_ledger_lock(path: Path) -> None:
    """Exclusive advisory lock for the load→mutate→save cycle (2026-07-13 C2).

    Without it, two concurrent hook processes on the same ledger both load the
    same snapshot and the later save silently clobbers the earlier append.
    Held from load_ledger until save_ledger (or process exit — hooks are
    short-lived, and the OS releases the flock when the holder dies, so a
    blocking wait is bounded by holder lifetime + the harness's own hook
    timeout). Fail-open: a platform without flock proceeds unlocked rather
    than wedge a hook.
    """
    key = str(path)
    if key in _LEDGER_LOCKS:
        return
    try:
        import fcntl

        path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(f"{path}.lock", "a", encoding="utf-8")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        except OSError:
            handle.close()
            return
        _LEDGER_LOCKS[key] = handle
    except Exception:
        return


def _release_ledger_lock(path: Path) -> None:
    handle = _LEDGER_LOCKS.pop(str(path), None)
    if handle is not None:
        try:
            handle.close()  # closing the descriptor releases the flock
        except OSError:
            pass


LEDGER_TTL_DAYS = 30


def _prune_stale_ledgers(directory: Path) -> None:
    """First-touch housekeeping (2026-07-13 rereview C9c): one ledger file
    accumulates per (session, cwd) and nothing ever removed them. Sweep
    siblings whose mtime is past the TTL — a file that old cannot belong to
    a live session. Fail-open on every path.
    """
    try:
        import time

        cutoff = time.time() - LEDGER_TTL_DAYS * 86400
        for entry in directory.glob("*.json"):
            try:
                if entry.stat().st_mtime < cutoff:
                    entry.unlink(missing_ok=True)
                    Path(f"{entry}.lock").unlink(missing_ok=True)
            except OSError:
                continue
    except Exception:
        pass


def load_ledger(input_data: dict[str, Any]) -> dict[str, Any]:
    path = ledger_path(input_data)
    _acquire_ledger_lock(path)
    if not path.exists():
        _prune_stale_ledgers(path.parent)
        return default_ledger()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default_ledger()  # corrupt ledger = fresh ledger (fail-open)
    ledger = default_ledger()
    if isinstance(data, dict):
        ledger.update({key: data.get(key, value) for key, value in ledger.items()})
    for key in ("changed_paths", "change_kinds", "verification_commands", "verification_results", "failures", "surfaced_ops", "git_commands", "retry_bounced", "stop_bounced_sets", "surfacing_pending_paths"):
        if not isinstance(ledger.get(key), list):
            ledger[key] = []
    seq_map = ledger.get("changed_path_seqs")
    if isinstance(seq_map, dict):
        clean: dict[str, int] = {}
        for k, v in seq_map.items():
            try:
                clean[str(k)] = int(v)
            except (TypeError, ValueError):
                continue
        ledger["changed_path_seqs"] = clean
    else:
        ledger["changed_path_seqs"] = {}
    if not isinstance(ledger.get("surfacing_pending_token"), str):
        ledger["surfacing_pending_token"] = ""
    for key in ("event_seq", "last_gated_seq", "last_gated_exec_seq", "stop_blocks", "continuation_blocks", "surfacing_blocks", "absence_blocks", "claim_blocks", "retry_blocks", "subagent_seq", "delegate_report_seq", "subagent_blocks"):
        if not isinstance(ledger.get(key), int):
            ledger[key] = 0
    for key in ("boundary_expansion_seen", "last_bash_failed", "prompt_gate_bounced"):
        if not isinstance(ledger.get(key), bool):
            ledger[key] = False
    if not isinstance(ledger.get("last_bash_cmd_hash"), str):
        ledger["last_bash_cmd_hash"] = ""
    return ledger


def save_ledger(input_data: dict[str, Any], ledger: dict[str, Any]) -> Path:
    path = ledger_path(input_data)
    path.parent.mkdir(parents=True, exist_ok=True)
    ledger["last_updated"] = utc_now()
    # trim
    for key in ("changed_paths", "change_kinds"):
        seen: list[str] = []
        for v in ledger.get(key, []):
            if v not in seen:
                seen.append(v)
        ledger[key] = seen[:40]
    for key in ("verification_commands", "verification_results", "failures", "git_commands"):
        ledger[key] = ledger.get(key, [])[-40:]
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(ledger, handle, indent=2, sort_keys=True)
        os.replace(tmp, path)
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        _release_ledger_lock(path)
    return path


def add_unique(ledger: dict[str, Any], key: str, values: list[str]) -> None:
    existing = list(ledger.get(key, []))
    for value in values:
        if value and value not in existing:
            existing.append(value)
    ledger[key] = existing


def classify_path_kind(path_value: str) -> str:
    """harness > code > config > docs/other. Harness surface is gated regardless of extension."""
    p = path_value.replace("\\", "/")
    if HARNESS_SURFACE_RE.search(p):
        return "harness"
    suffix = Path(p).suffix.lower()
    if suffix in CODE_EXTS:
        return "code"
    if suffix in CONFIG_EXTS:
        return "config"
    return "docs"  # plain notes/docs/other = exempt kind


PROSE_EXTS = {".md", ".markdown", ".txt"}


def is_prose_path(path_value: str) -> bool:
    """Prose files inside the harness surface (rule/skill/command .md) are
    still gated (a change with no verification at all keeps bouncing), but
    they don't stale prior verifications — see has_successful_verification."""
    return Path(path_value.replace("\\", "/")).suffix.lower() in PROSE_EXTS


def read_stdin_json() -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def response_text(value: Any, limit: int = 4000) -> str:
    parts: list[str] = []

    def walk(item: Any) -> None:
        if len(" ".join(parts)) > limit:
            return
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict):
            for key in ("stdout", "stderr", "output", "message", "text", "content", "error", "summary"):
                if key in item:
                    walk(item[key])
            if not parts:
                for child in item.values():
                    walk(child)
        elif isinstance(item, list):
            for child in item[:20]:
                walk(child)

    walk(value)
    return redact(" ".join(parts), limit)


def command_from_input(input_data: dict[str, Any]) -> str:
    tool_input = input_data.get("tool_input")
    if isinstance(tool_input, dict):
        return str(tool_input.get("command") or "")
    if isinstance(tool_input, str):
        return tool_input
    return ""


def exit_success(input_data: dict[str, Any], text: str) -> bool | None:
    for candidate in (input_data, input_data.get("tool_response")):
        if isinstance(candidate, dict):
            for key in ("success", "ok"):
                if isinstance(candidate.get(key), bool):
                    return bool(candidate[key])
            for key in ("exit_code", "exitCode", "returncode", "status"):
                value = candidate.get(key)
                if isinstance(value, int):
                    return value == 0
                if isinstance(value, str) and value.isdigit():
                    return int(value) == 0
                if isinstance(value, str):
                    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
                    if normalized in SUCCESS_STATUSES:
                        return True
                    if normalized in FAILURE_STATUSES:
                        return False
    if EXIT_ZERO_RE.search(text):
        return True
    if FAILURE_RE.search(text):
        return False
    if SUCCESS_RE.search(text):
        return True
    return None


def changed_paths(input_data: dict[str, Any]) -> list[str]:
    tool_name = str(input_data.get("tool_name") or "")
    # Mutating tools only. Read is on the ledger matcher for delegate-report
    # evidence (v4.1), but its file_path is NOT a change — recording it marked
    # merely-read docs as changed and staled prior verifications on every code
    # read (measured 2026-07-07: stop-verify demanded proof for files the
    # session only Read).
    if tool_name not in {"Edit", "Write", "MultiEdit", "NotebookEdit"}:  # MultiEdit — code-review feedback
        return []
    tool_input = input_data.get("tool_input")
    paths: list[str] = []
    if isinstance(tool_input, dict):
        fp = tool_input.get("file_path")
        if fp:
            paths.append(str(fp))
    return paths or ["edit"]


def changed_kinds(input_data: dict[str, Any]) -> list[str]:
    paths = changed_paths(input_data)
    if paths:
        return sorted({classify_path_kind(p.strip()) for p in paths})
    tool_name = str(input_data.get("tool_name") or "")
    if tool_name == "Bash":
        command = command_from_input(input_data)
        # only record mutating bash that touches the harness surface (plain
        # file moves elsewhere stay "docs")
        if MUTATING_BASH_RE.search(command) and HARNESS_SURFACE_RE.search(command):
            return ["harness"]
    return []


def is_verification_command(command: str) -> bool:
    return bool(VERIFY_RE.search(command or ""))


def verification_record(input_data: dict[str, Any]) -> dict[str, Any] | None:
    command = command_from_input(input_data)
    if not command or not is_verification_command(command):
        return None
    text = response_text(input_data.get("tool_response", input_data), 1000)
    success = exit_success(input_data, text)
    return {
        "command": redact(command, 220),
        "success": bool(success) if success is not None else None,
        "summary": redact(text, 220),
    }


def git_usage_record(input_data: dict[str, Any]) -> dict[str, Any] | None:
    """Bash git usage — investigation evidence consumed by the absence gate.

    Ledger v2: read-only investigation used to leave the ledger untouched,
    which made read-phase disciplines (absence claims) structurally invisible
    to the Stop gate — measured in cycle3 (absence-claim-trap runs had no
    ledger at all). Recording git usage closes that blind spot.
    """
    if str(input_data.get("tool_name") or "") != "Bash":
        return None
    command = command_from_input(input_data)
    if not command or not GIT_USAGE_RE.search(command):
        return None
    return {
        "command": redact(command, 220),
        "boundary": bool(BOUNDARY_EXPANSION_RE.search(command)),
    }


TRANSCRIPT_TAIL_BYTES = 400_000  # same cap as prompt-advance-gate's transcript_tail()


def last_assistant_text(transcript_path: str) -> str:
    """Last assistant message's text from a Claude Code transcript (jsonl).

    Shared by continuation-gate (deferral language) and stop-verify-gate
    (absence claims) — both judge the turn's final message. Reads only the
    last TRANSCRIPT_TAIL_BYTES (2026-07-13 C3): at Stop time that message
    sits at the transcript's tail, and long sessions grow transcripts to
    tens of MB — an unbounded read on every Stop is pure cost.
    """
    try:
        path = Path(transcript_path)
        size = path.stat().st_size
        with open(path, "rb") as handle:
            if size > TRANSCRIPT_TAIL_BYTES:
                handle.seek(size - TRANSCRIPT_TAIL_BYTES)
            raw = handle.read()
    except OSError:
        return ""
    lines = raw.decode("utf-8", errors="replace").splitlines()
    for line in reversed(lines):
        try:
            entry = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if entry.get("type") != "assistant":
            continue
        content = (entry.get("message") or {}).get("content")
        parts: list[str] = []
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(str(block.get("text") or ""))
        if parts:
            return "\n".join(parts)
    return ""


def detect_failure(input_data: dict[str, Any]) -> dict[str, Any] | None:
    text = response_text(input_data.get("tool_response", input_data))
    success = exit_success(input_data, text)
    if success is False or (success is None and FAILURE_RE.search(text)):
        return {"kind": "tool-result", "summary": redact(text or command_from_input(input_data), 240)}
    return None


# --- gate decision ---

def gate_enabled() -> bool:
    """Kill-switch + optional pilot scoping (env-based).

    Default: the gate is ACTIVE for every session.
    - FABLE_GATE_OFF=1        — kill switch, disables the gate entirely.
    - FABLE_GATE_PILOT=<name> — optional scoping: when set, the gate only
      activates for sessions whose FABLE_SESSION_NAME matches <name>. Useful
      for piloting the gate on one bot/session before enabling it broadly,
      without hard-coding any project-specific identity check here.
    """
    if os.environ.get("FABLE_GATE_OFF") == "1":
        return False
    pilot = os.environ.get("FABLE_GATE_PILOT", "").strip()
    if not pilot:
        return True
    return os.environ.get("FABLE_SESSION_NAME", "").strip() == pilot


def gated_kinds(ledger: dict[str, Any]) -> set[str]:
    return {k for k in ledger.get("change_kinds", []) if k in {"harness", "code", "config"}}


def has_successful_verification(ledger: dict[str, Any]) -> bool:
    """Only a successful verification **after** the last *executable* gated
    change counts (closes the "verify first, then change code" ordering
    bypass — code-review feedback).

    Ledger v5.1 refinement: the ordering anchor is last_gated_exec_seq
    (code/config/settings, non-prose harness files), not last_gated_seq.
    Measured across 542 real session ledgers (2026-07-12): 468 sessions
    bounced at stop and ALL 468 already carried verification evidence — the
    dominant pattern was "verify the code, then edit a rules/skills .md
    last", which the strict anchor turned into a near-universal one-bounce
    friction tax (~96% of change sessions). Prose harness edits still gate
    (no verification at all keeps blocking) but no longer stale a
    verification that already succeeded earlier in the session.
    """
    anchor = int(ledger.get("last_gated_exec_seq") or 0)
    return any(
        r.get("success") is True and int(r.get("seq") or 0) >= anchor
        for r in ledger.get("verification_results", [])
    )


def should_block_stop(ledger: dict[str, Any]) -> tuple[bool, str]:
    stop_blocks = int(ledger.get("stop_blocks") or 0)
    if stop_blocks >= MAX_STOP_BLOCKS:
        return False, ""
    gated = gated_kinds(ledger)
    if not gated:  # no changes, or docs-only = exempt
        return False, ""
    if has_successful_verification(ledger):
        return False, ""
    # Ledger v5.2 current-turn scope: name only paths changed after the last
    # successful verification — earlier paths are presumed covered by it.
    # Measured 2026-07-13 (7d live audit): re-bounces re-listed the whole
    # session's file set, so the agent re-argued files it had already
    # verified turns ago. Legacy ledgers without the seq map keep the old
    # full-list behavior.
    seq_map = ledger.get("changed_path_seqs")
    if isinstance(seq_map, dict) and seq_map:
        last_success = max(
            (
                int(r.get("seq") or 0)
                for r in ledger.get("verification_results", [])
                if r.get("success") is True
            ),
            default=0,
        )
        relevant = sorted(
            p for p, s in seq_map.items() if p != "edit" and int(s or 0) > last_success
        )
    else:
        relevant = [p for p in ledger.get("changed_paths", []) if p != "edit"]
    # Ledger v5.2 re-bounce dedup: one bounce per unique unverified path-set
    # per session — the same set bouncing twice adds friction, not safety
    # (the agent already answered it once; MAX_STOP_BLOCKS still caps total).
    digest = hashlib.sha256("\n".join(relevant or sorted(gated)).encode("utf-8")).hexdigest()[:16]
    bounced_sets = ledger.get("stop_bounced_sets")
    if not isinstance(bounced_sets, list):
        bounced_sets = []
    if digest in bounced_sets:
        return False, ""
    ledger["stop_bounced_sets"] = (bounced_sets + [digest])[-20:]
    paths = relevant[:5]
    reason = (
        "fable-gate: this turn changed harness/code surface files ("
        + (", ".join(paths) if paths else ", ".join(sorted(gated)))
        + ") but there's no recorded successful verification (test, `bash -n`,\n"
        "grep confirmation, diff, etc.) for it. Run the narrowest verification "
        "that fits the change and confirm the result before stopping — and say "
        "which layer it ran at (source / build / render / consumer): a check "
        "that never reached where the result is actually consumed only proves "
        "the middle of the pipeline. "
        "If no verification is actually possible, say so explicitly in your "
        "response before stopping."
    )
    return True, reason


def should_block_absence(ledger: dict[str, Any], final_text: str) -> tuple[bool, str]:
    """Absence-claim gate (ledger v2).

    Arms only when ALL hold: the final message asserts that some artifact
    does not exist / there is nothing else; this session consulted git at
    least once (so repository state was part of the investigation); and no
    boundary-expansion command (`git log --all`, `git branch -a`, …) was ever
    run. One bounce per session, with the concrete checklist in the reason —
    cycle3 measured that prose rules alone don't turn into this behavior on
    every model, while mechanical gates do.
    """
    if int(ledger.get("absence_blocks") or 0) >= MAX_ABSENCE_BLOCKS:
        return False, ""
    if not final_text or not ABSENCE_CLAIM_RE.search(final_text):
        return False, ""
    if not ledger.get("git_commands"):
        return False, ""  # v1 scope: git-boundary absence only — non-git sessions pass
    if ledger.get("boundary_expansion_seen"):
        return False, ""
    reason = (
        "fable-gate(absence): your final answer asserts that something does not "
        "exist / there is nothing else, and this session consulted git — but only "
        "the checked-out view (no `git log --all`, `git branch -a`, or equivalent "
        "all-refs check was run). Before an absence claim: "
        "(1) run `git log --oneline --all` and `git branch -a` — unmerged branches "
        "are where 'missing' things live; "
        "(2) re-run your search unfiltered and untruncated (no head/limit), with "
        "synonym vocabulary; "
        "(3) then either cite the boundary you checked, or downgrade the claim "
        "('not in the checked-out tree; other branches/history not checked'). "
        "If the claim is genuinely outside git's scope, say so explicitly and stop "
        "again — this gate bounces once."
    )
    return True, reason


def has_mechanical_evidence(ledger: dict[str, Any]) -> bool:
    """Any recorded verification command that mechanically counts or compares."""
    for rec in ledger.get("verification_commands", []):
        cmd = rec.get("command", "") if isinstance(rec, dict) else str(rec)
        if MECH_EVIDENCE_RE.search(cmd):
            return True
    return False


def should_block_claim_evidence(ledger: dict[str, Any], final_text: str) -> tuple[bool, str]:
    """Claim-evidence gate (ledger v3).

    Arms when the final message makes a precise COUNT claim about measured
    artifacts, or an IDENTITY claim ("byte-for-byte identical"), and no
    mechanical counting/compare command (wc -l / grep -c / diff / cmp /
    shasum / …) was recorded this session. Cycle4 measured this exact gap
    twice with prose rules alone: an off-by-one count from a manual
    read-through, and an identity claim with no diff in the tool log. One
    bounce per session, checklist in the reason — same shape as the absence
    gate, because that shape measurably works where prose doesn't.
    """
    if int(ledger.get("claim_blocks") or 0) >= MAX_CLAIM_BLOCKS:
        return False, ""
    if not final_text:
        return False, ""
    count_claim = bool(COUNT_CLAIM_RE.search(final_text))
    identity_claim = bool(IDENTITY_CLAIM_RE.search(final_text))
    if not (count_claim or identity_claim):
        return False, ""
    if has_mechanical_evidence(ledger):
        return False, ""
    reason = (
        "fable-gate(claim-evidence): your final answer states "
        + ("a precise count" if count_claim else "")
        + (" and " if count_claim and identity_claim else "")
        + ("an identity/equality claim" if identity_claim else "")
        + ", but no mechanical check backs it in this session's tool log. "
        "Numbers and equality are claims to verify, not narrate: "
        "(1) for counts — run the count mechanically (`wc -l`, `grep -c`, "
        "`ls | wc -l`) and show the arithmetic if you derived it; "
        "(2) for identity — run `diff`/`cmp`/`shasum` on the two artifacts; "
        "(3) then either cite the command and its output, or downgrade the "
        "claim ('appears to match; not mechanically verified'). "
        "If a mechanical check is genuinely impossible here, say so "
        "explicitly and stop again — this gate bounces once."
    )
    return True, reason


def has_verification_after(ledger: dict[str, Any], seq: int) -> bool:
    """Any recorded verification whose event_seq is later than `seq`."""
    for record in ledger.get("verification_results", []):
        if not isinstance(record, dict):
            continue
        try:
            if int(record.get("seq") or 0) > seq:
                return True
        except (TypeError, ValueError):
            continue
    return False


def delegate_report_read(input_data: dict[str, Any]) -> bool:
    """Read of a file whose path names it a delegate's report (ledger v4.1)."""
    if str(input_data.get("tool_name") or "") != "Read":
        return False
    tool_input = input_data.get("tool_input")
    file_path = tool_input.get("file_path") if isinstance(tool_input, dict) else None
    return bool(DELEGATE_REPORT_PATH_RE.search(str(file_path or "")))


def should_block_subordinate_evidence(ledger: dict[str, Any], final_text: str) -> tuple[bool, str]:
    """Subordinate-evidence check (ledger v4 — mined behavior C5).

    Arms only when all three hold: (a) a delegate reported this session —
    either a subagent (Task/Agent) ran, or a delegate-report file
    (worker-report.md etc.) was Read (v4.1 anchor: file-mediated
    delegation), (b) NO verification-class command was recorded after the
    last such event, (c) the final reply declares completion. The bounce
    asks for one independent re-derivation of the delegate's claim — stat
    the artifact it says it produced, re-run the check it says passed, grep
    the output it says exists. One bounce per session; sessions that verify
    after delegating (the mined fable pattern) never see this gate.
    """
    if int(ledger.get("subagent_blocks") or 0) >= MAX_SUBAGENT_BLOCKS:
        return False, ""
    subagent_seq = max(
        int(ledger.get("subagent_seq") or 0),
        int(ledger.get("delegate_report_seq") or 0),
    )
    if subagent_seq <= 0:
        return False, ""
    if not final_text or not COMPLETION_CLAIM_RE.search(final_text):
        return False, ""
    if has_verification_after(ledger, subagent_seq):
        return False, ""
    reason = (
        "fable-gate(subordinate-evidence): this session consumed a delegate's "
        "report (a subagent ran, or a worker-report file was read) and the "
        "final answer declares completion, but no "
        "verification command ran AFTER the delegate reported. A delegate's "
        "'done/success' is a claim, not evidence — the worst-recurrence "
        "failure in our incident log is exactly this (fabricated 'success' "
        "text with no tool calls behind it, 'Connected'/'sent' flags that "
        "were false). Independently re-derive one load-bearing claim from "
        "the delegate's report: stat/read the artifact it says it produced, "
        "re-run the test it says passed, or grep/count the output it cites — "
        "then cite that check. If the delegate's output is genuinely "
        "unverifiable here, say so explicitly and stop again — this gate "
        "bounces once."
    )
    return True, reason
