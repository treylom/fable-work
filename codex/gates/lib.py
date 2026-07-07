#!/usr/bin/env python3
"""Shared library for the bundled tofable Codex gate hooks.

Gate logic is ported from this repository's `hooks/` implementation. Codex
event wiring follows the same four-event shape used by fable-ish-codex, but no
upstream classifier or gate logic is copied here.
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
from typing import Any, Callable

MAX_STOP_BLOCKS = 2
MAX_ABSENCE_BLOCKS = 1
MAX_CLAIM_BLOCKS = 1
MAX_SUBAGENT_BLOCKS = 1
MAX_RETRY_BLOCKS = 5
MAX_SURFACING_BLOCKS = 5
MAX_CONTINUATION_BLOCKS = 1

DEFAULT_LEDGER: dict[str, Any] = {
    "changed_files_seen": False,
    "changed_paths": [],
    "change_kinds": [],
    "verification_commands": [],
    "verification_results": [],
    "failures": [],
    "stop_blocks": 0,
    "continuation_blocks": 0,
    "surfacing_blocks": 0,
    "surfaced_ops": [],
    "git_commands": [],
    "boundary_expansion_seen": False,
    "absence_blocks": 0,
    "claim_blocks": 0,
    "last_bash_cmd_hash": "",
    "last_bash_failed": False,
    "retry_bounced": [],
    "retry_blocks": 0,
    "subagent_seq": 0,
    "delegate_report_seq": 0,
    "subagent_blocks": 0,
    "event_seq": 0,
    "last_gated_seq": 0,
    "last_updated": "",
}

SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*['\"]?[^'\"\s]+"),
    re.compile(r"sk-[A-Za-z0-9_-]{12,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9_]{12,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{12,}"),
]

CODE_EXTS = {".py", ".sh", ".js", ".mjs", ".ts", ".tsx", ".jsx", ".rb", ".go", ".rs", ".c", ".cc", ".cpp", ".java", ".swift", ".sql", ".css", ".scss"}
CONFIG_EXTS = {".json", ".jsonc", ".toml", ".yaml", ".yml", ".ini", ".cfg", ".conf", ".plist", ".lock"}
DOC_EXTS = {".md", ".mdx", ".rst", ".txt", ".adoc"}

HARNESS_SURFACE_RE = re.compile(
    r"(^|/)(?:\.codex-plugin/|codex/gates/|hooks/|scripts/|\.codex/|settings(\.local)?\.json$|AGENTS\.md$)"
)
PATCH_PATH_RE = re.compile(r"(?im)^\*\*\* (?:Add|Update|Delete) File: (.+)$")

VERIFY_RE = re.compile(
    r"(?i)\b("
    r"pytest|unittest|go\s+test|cargo\s+test|npm\s+test|pnpm\s+test|yarn\s+test|bun\s+test|"
    r"mvn\s+test|gradle\s+test|rspec|vitest|jest|playwright|cypress|"
    r"lint|eslint|ruff|flake8|mypy|pyright|tsc|typecheck|"
    r"bash\s+-n|zsh\s+-n|sh\s+-n|py_compile|json\.tool|python3?\s+-m\s+unittest|python3?\s+(?:[^\s]*/)?test_[a-z0-9_]+\.py|"
    r"build|check|validate|verify|diff|shasum|sha256sum|md5|grep\s+-c|wc\s+-l|curl"
    r")\b"
)
FAILURE_RE = re.compile(
    r"(?i)(command not found|no such file or directory|traceback|syntaxerror|"
    r"\berror:|\b[1-9][0-9]*\s+errors?\b|exit code\s*:?\s*[1-9]|exited with code\s*:?\s*[1-9]|"
    r"tests? failed|build failed|lint failed|assertion(?:error)? failed|\b[1-9][0-9]*\s+failed\b)"
)
EXIT_ZERO_RE = re.compile(r"(?i)\b(exit code|exited with code|process exited with code)\s*:?\s*0\b")
SUCCESS_RE = re.compile(r"(?i)\b(passed|success(?:fully)?|succeeded|0 failed|compiled successfully|built successfully|build succeeded|ok|green|valid)\b")
MUTATING_BASH_RE = re.compile(r"(?i)\b(chmod|mkdir|mv|cp|rm|touch|tee|sed\s+-i|launchctl|npm\s+run\s+build|git\s+(add|commit|push|reset))\b")
GIT_USAGE_RE = re.compile(r"(?i)(?:^|[|;&`(\s])git\s+\S")
BOUNDARY_EXPANSION_RE = re.compile(
    r"(?i)\bgit\b[^\n|;&]{0,140}?(?:--all\b|\bbranch\s+-(?:a|av|avv|va|r)\b|\bbranch\s+--all\b|\bls-files\b|\bshow-ref\b|\bfor-each-ref\b|\bstash\s+list\b|\breflog\b)"
)

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

_COUNT_NOUN = r"(?:lines?|rows?|files?|entries|messages?|records?|matches|occurrences?|commits?|tests?|items?|줄|행|파일|건|개(?:의)?\s*(?:파일|메시지|줄|행|기록|항목|테스트|커밋)?)"
_NUM_GE3 = r"(?:[3-9]|[1-9][0-9][0-9,]*|[1-9][0-9])"
_ADJ1 = r"(?:[A-Za-z가-힣-]+\s+)?"
COUNT_CLAIM_RE = re.compile(
    r"(?i)(?:"
    rf"(?:총|전체|모두\s*합쳐|정확히|exactly|in\s+total|a\s+total\s+of)\s*[0-9][0-9,]*\s*{_ADJ1}{_COUNT_NOUN}"
    rf"|\b{_NUM_GE3}\s+{_ADJ1}{_COUNT_NOUN}"
    rf"|\b{_NUM_GE3}\s*(?=[가-힣]){_COUNT_NOUN}"
    r")"
)
IDENTITY_CLAIM_RE = re.compile(
    r"(?i)(?:byte[- ]?(?:for[- ]?byte|identical)|identical\s+to|exact\s+match(?:es)?|"
    r"완전히\s*동일|정확히\s*일치|바이트\s*단위로?\s*동일|동일함이?\s*확인)"
)
MECH_EVIDENCE_RE = re.compile(
    r"(?i)\b(wc\s+-[lwc]|grep\s+-[a-z]*c|diff|cmp|comm|shasum|sha256sum|md5(?:sum)?|"
    r"uniq\s+-c|sort\s+.*\|\s*uniq|find\s+.*\|\s*wc|ls\s+.*\|\s*wc|len\()"
)

SUBAGENT_TOOLS = {"Task", "Agent", "subagent", "multi_agent"}
DELEGATE_REPORT_PATH_RE = re.compile(r"(?i)(?:worker|delegate|subagent)[-_]?report")
COMPLETION_CLAIM_RE = re.compile(
    r"(?i)(?:\b(?:done|complete[d]?|finished|delivered|shipped|all\s+set)\b"
    r"|✅|\bGREEN\b|\bCLEAN\b|완료|끝났|마쳤|마무리|성공적으로|반영(?:됐|되었)|처리(?:됐|되었))"
)

CMD_ANCHOR = r"(?:^|[;&|]\s*|\$\(\s*|`\s*)"
DESTRUCTIVE_PATTERNS = [
    CMD_ANCHOR + r"rm\s+(?:-[a-zA-Z]*\s+)*-[a-zA-Z]*[rfRF][a-zA-Z]*\b",
    CMD_ANCHOR + r"git\s+push\b[^\n;|&]*(?:--force(?:-with-lease)?|\s-f\b)",
    CMD_ANCHOR + r"git\s+reset\s+--hard\b",
    CMD_ANCHOR + r"git\s+clean\b[^\n;|&]*-[a-zA-Z]*f",
    CMD_ANCHOR + r"git\s+branch\s+(?:-D|--delete\s+--force)\b",
    CMD_ANCHOR + r"find\b[^\n;|&]*\s-delete\b",
    CMD_ANCHOR + r"(?:rmdir|shred|mkfs\.[a-z0-9]+)\b",
    CMD_ANCHOR + r"truncate\s+-s\s*0\b",
    r"\bshutil\.rmtree\s*\(",
    r"\bDROP\s+(?:TABLE|DATABASE|SCHEMA)\b",
    CMD_ANCHOR + r"rsync\b[^\n]*--delete\b",
]
DESTRUCTIVE_RE = re.compile("|".join(DESTRUCTIVE_PATTERNS), re.IGNORECASE)

DEFERRAL_PATTERNS = [
    r"\b(?:i'?ll|we'?ll|will|let'?s)\s+(?:finish|continue|resume|complete|tackle|revisit|do)\b[^.\n]{0,60}\b(?:tomorrow|next\s+(?:session|time|turn)|later)\b",
    r"\b(?:pick|picking)\s+(?:this|it|that)\s+(?:back\s+)?up\s+(?:tomorrow|later|next)\b",
    r"\b(?:stopping|stop)\s+here\s+for\s+(?:now|today|tonight)\b",
    r"\bwrap(?:ping)?\s+(?:this\s+|it\s+)?up\s+(?:here|for\s+(?:now|today|tonight))\b",
    r"\bleave\s+(?:this|the\s+rest|it)\s+for\s+(?:now|later|tomorrow|next\s+session)\b",
    r"\bcall(?:ing)?\s+it\s+(?:a\s+(?:day|night)|here)\b",
    r"\bdefer(?:ring)?\s+(?:this|the\s+rest|it)\b",
    r"내일\s*(?:이어|계속|마저|다시|아침에\s*(?:이어|계속|마저|다시))",
    r"다음\s*(?:세션|턴|기회)\s*(?:에|으로)",
    r"오늘은\s*여기까지",
    r"여기서\s*(?:마무리|정리하|멈추)",
    r"나중에\s*(?:이어|계속|마저)",
    r"이월(?:하|했|됨|된|시키|시켜|할)",
]
DEFERRAL_RE = re.compile("|".join(DEFERRAL_PATTERNS), re.IGNORECASE)

SUCCESS_STATUSES = {"success", "succeeded", "completed", "complete", "ok", "passed", "pass"}
FAILURE_STATUSES = {"failed", "failure", "error", "errored", "fatal", "timeout", "timed_out"}


def emit_json(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")


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
    env = os.environ.get("FABLE_STATE_DIR") or os.environ.get("PLUGIN_DATA")
    if env:
        return Path(env).expanduser().resolve()
    state_home = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")).expanduser()
    return (state_home / "tofable" / "codex-gates").resolve()


def ledger_key(input_data: dict[str, Any]) -> str:
    cwd = input_data.get("cwd") or os.getcwd()
    session_id = input_data.get("session_id") or "no-session"
    return hashlib.sha256(f"{session_id}|{cwd}".encode("utf-8", "replace")).hexdigest()[:24]


def ledger_path(input_data: dict[str, Any]) -> Path:
    return data_root() / "ledgers" / f"{ledger_key(input_data)}.json"


def default_ledger() -> dict[str, Any]:
    return copy.deepcopy(DEFAULT_LEDGER)


def load_ledger(input_data: dict[str, Any]) -> dict[str, Any]:
    path = ledger_path(input_data)
    if not path.exists():
        return default_ledger()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default_ledger()
    ledger = default_ledger()
    if isinstance(data, dict):
        ledger.update({key: data.get(key, value) for key, value in ledger.items()})
    for key in ("changed_paths", "change_kinds", "verification_commands", "verification_results", "failures", "surfaced_ops", "git_commands", "retry_bounced"):
        if not isinstance(ledger.get(key), list):
            ledger[key] = []
    for key in ("event_seq", "last_gated_seq", "stop_blocks", "continuation_blocks", "surfacing_blocks", "absence_blocks", "claim_blocks", "retry_blocks", "subagent_seq", "delegate_report_seq", "subagent_blocks"):
        if not isinstance(ledger.get(key), int):
            ledger[key] = 0
    for key in ("boundary_expansion_seen", "last_bash_failed"):
        if not isinstance(ledger.get(key), bool):
            ledger[key] = False
    if not isinstance(ledger.get("last_bash_cmd_hash"), str):
        ledger["last_bash_cmd_hash"] = ""
    return ledger


def save_ledger(input_data: dict[str, Any], ledger: dict[str, Any]) -> Path:
    path = ledger_path(input_data)
    path.parent.mkdir(parents=True, exist_ok=True)
    ledger["last_updated"] = utc_now()
    for key in ("changed_paths", "change_kinds"):
        seen: list[str] = []
        for value in ledger.get(key, []):
            if value not in seen:
                seen.append(value)
        ledger[key] = seen[:40]
    for key in ("verification_commands", "verification_results", "failures", "git_commands", "retry_bounced", "surfaced_ops"):
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
    return path


def update_ledger(input_data: dict[str, Any], updater: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    ledger = load_ledger(input_data)
    updater(ledger)
    save_ledger(input_data, ledger)
    return ledger


def add_unique(ledger: dict[str, Any], key: str, values: list[str]) -> None:
    existing = list(ledger.get(key, []))
    for value in values:
        if value and value not in existing:
            existing.append(value)
    ledger[key] = existing


def read_stdin_json() -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def gate_enabled() -> bool:
    if os.environ.get("FABLE_GATE_OFF") == "1":
        return False
    pilot = os.environ.get("FABLE_GATE_PILOT", "").strip()
    if not pilot:
        return True
    return os.environ.get("FABLE_SESSION_NAME", "").strip() == pilot


def command_from_input(input_data: dict[str, Any]) -> str:
    tool_input = input_data.get("tool_input")
    if isinstance(tool_input, dict):
        for key in ("command", "patch", "description"):
            if tool_input.get(key):
                return str(tool_input.get(key) or "")
    if isinstance(tool_input, str):
        return tool_input
    return ""


def command_hash(command: str) -> str:
    return hashlib.sha256(command.strip().encode("utf-8", "replace")).hexdigest()[:16]


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


def classify_path_kind(path_value: str) -> str:
    p = path_value.replace("\\", "/")
    if p in {"patch", "edit"}:
        return "code"
    if HARNESS_SURFACE_RE.search(p):
        return "harness"
    path = Path(p)
    suffix = path.suffix.lower()
    parts = {part.lower() for part in path.parts}
    if suffix in DOC_EXTS or "docs" in parts:
        return "docs"
    if suffix in CODE_EXTS:
        return "code"
    if suffix in CONFIG_EXTS or path.name.startswith(".env"):
        return "config"
    return "docs"


def changed_paths(input_data: dict[str, Any]) -> list[str]:
    tool_name = str(input_data.get("tool_name") or "")
    tool_input = input_data.get("tool_input")
    paths: list[str] = []
    if tool_name == "apply_patch":
        if isinstance(tool_input, dict):
            command = str(tool_input.get("command") or tool_input.get("patch") or "")
            paths.extend(PATCH_PATH_RE.findall(command))
        elif isinstance(tool_input, str):
            paths.extend(PATCH_PATH_RE.findall(tool_input))
        return paths or ["patch"]
    if tool_name in {"Edit", "Write", "MultiEdit", "NotebookEdit"}:
        if isinstance(tool_input, dict):
            file_path = tool_input.get("file_path")
            if file_path:
                paths.append(str(file_path))
        return paths or ["edit"]
    return []


def changed_kinds(input_data: dict[str, Any]) -> list[str]:
    paths = changed_paths(input_data)
    if paths:
        return sorted({classify_path_kind(path.strip()) for path in paths})
    tool_name = str(input_data.get("tool_name") or "")
    command = command_from_input(input_data)
    if tool_name == "Bash" and MUTATING_BASH_RE.search(command) and HARNESS_SURFACE_RE.search(command):
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
    return {"command": redact(command, 220), "success": bool(success) if success is not None else None, "summary": redact(text, 220)}


def detect_failure(input_data: dict[str, Any]) -> dict[str, Any] | None:
    text = response_text(input_data.get("tool_response", input_data))
    success = exit_success(input_data, text)
    if success is False or (success is None and FAILURE_RE.search(text)):
        return {"kind": "tool-result", "summary": redact(text or command_from_input(input_data), 240)}
    return None


def git_usage_record(input_data: dict[str, Any]) -> dict[str, Any] | None:
    if str(input_data.get("tool_name") or "") != "Bash":
        return None
    command = command_from_input(input_data)
    if not command or not GIT_USAGE_RE.search(command):
        return None
    return {"command": redact(command, 220), "boundary": bool(BOUNDARY_EXPANSION_RE.search(command))}


def delegate_report_read(input_data: dict[str, Any]) -> bool:
    if str(input_data.get("tool_name") or "") != "Read":
        return False
    tool_input = input_data.get("tool_input")
    file_path = tool_input.get("file_path") if isinstance(tool_input, dict) else None
    return bool(DELEGATE_REPORT_PATH_RE.search(str(file_path or "")))


def last_assistant_text_from_transcript(transcript_path: str) -> str:
    try:
        lines = Path(transcript_path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
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


def final_text_from_input(input_data: dict[str, Any]) -> str:
    for key in ("final_text", "assistant_text", "assistant_response", "response", "text"):
        value = input_data.get(key)
        if isinstance(value, str) and value.strip():
            return value
    message = input_data.get("message")
    if isinstance(message, dict):
        text = response_text(message, 4000)
        if text:
            return text
    transcript = input_data.get("transcript_path")
    if isinstance(transcript, str) and transcript:
        return last_assistant_text_from_transcript(transcript)
    return ""


def gated_kinds(ledger: dict[str, Any]) -> set[str]:
    return {kind for kind in ledger.get("change_kinds", []) if kind in {"harness", "code", "config"}}


def has_successful_verification(ledger: dict[str, Any]) -> bool:
    last_gated = int(ledger.get("last_gated_seq") or 0)
    return any(
        isinstance(record, dict)
        and record.get("success") is True
        and int(record.get("seq") or 0) >= last_gated
        for record in ledger.get("verification_results", [])
    )


def should_block_unverified_change(ledger: dict[str, Any]) -> tuple[bool, str]:
    if int(ledger.get("stop_blocks") or 0) >= MAX_STOP_BLOCKS:
        return False, ""
    gated = gated_kinds(ledger)
    if not gated or has_successful_verification(ledger):
        return False, ""
    paths = [path for path in ledger.get("changed_paths", []) if path != "edit"][:5]
    reason = (
        "tofable-codex-gate: this turn changed harness/code/config surface files ("
        + (", ".join(paths) if paths else ", ".join(sorted(gated)))
        + ") but no successful verification was recorded after the latest gated change. "
        "Run the narrowest relevant check and cite it before stopping."
    )
    return True, reason


def should_block_absence(ledger: dict[str, Any], final_text: str) -> tuple[bool, str]:
    if int(ledger.get("absence_blocks") or 0) >= MAX_ABSENCE_BLOCKS:
        return False, ""
    if not final_text or not ABSENCE_CLAIM_RE.search(final_text):
        return False, ""
    if not ledger.get("git_commands") or ledger.get("boundary_expansion_seen"):
        return False, ""
    return True, (
        "tofable-codex-gate(absence): the final answer asserts an artifact does not exist "
        "after git was consulted, but no all-refs boundary check was recorded. Run an all-refs "
        "check such as `git log --oneline --all` plus `git branch -a`, then cite the checked boundary."
    )


def has_mechanical_evidence(ledger: dict[str, Any]) -> bool:
    for record in ledger.get("verification_commands", []):
        command = record.get("command", "") if isinstance(record, dict) else str(record)
        if MECH_EVIDENCE_RE.search(command):
            return True
    return False


def should_block_claim_evidence(ledger: dict[str, Any], final_text: str) -> tuple[bool, str]:
    if int(ledger.get("claim_blocks") or 0) >= MAX_CLAIM_BLOCKS:
        return False, ""
    if not final_text:
        return False, ""
    count_claim = bool(COUNT_CLAIM_RE.search(final_text))
    identity_claim = bool(IDENTITY_CLAIM_RE.search(final_text))
    if not (count_claim or identity_claim) or has_mechanical_evidence(ledger):
        return False, ""
    parts = []
    if count_claim:
        parts.append("count")
    if identity_claim:
        parts.append("identity")
    return True, (
        "tofable-codex-gate(claim-evidence): the final answer makes a "
        + " and ".join(parts)
        + " claim without a mechanical count/compare command in the ledger. Run `wc`, `grep -c`, `diff`, `cmp`, or a checksum and cite the output."
    )


def has_verification_after(ledger: dict[str, Any], seq: int) -> bool:
    for record in ledger.get("verification_results", []):
        if not isinstance(record, dict):
            continue
        try:
            if int(record.get("seq") or 0) > seq:
                return True
        except (TypeError, ValueError):
            continue
    return False


def should_block_subordinate_evidence(ledger: dict[str, Any], final_text: str) -> tuple[bool, str]:
    if int(ledger.get("subagent_blocks") or 0) >= MAX_SUBAGENT_BLOCKS:
        return False, ""
    subagent_seq = max(int(ledger.get("subagent_seq") or 0), int(ledger.get("delegate_report_seq") or 0))
    if subagent_seq <= 0:
        return False, ""
    if not final_text or not COMPLETION_CLAIM_RE.search(final_text):
        return False, ""
    if has_verification_after(ledger, subagent_seq):
        return False, ""
    return True, (
        "tofable-codex-gate(subordinate-evidence): a delegate report was consumed and the final answer "
        "declares completion, but no verification command ran after the delegate reported. Independently "
        "re-derive one load-bearing claim from the delegate output before stopping."
    )


def should_block_continuation(ledger: dict[str, Any], final_text: str) -> tuple[bool, str]:
    if int(ledger.get("continuation_blocks") or 0) >= MAX_CONTINUATION_BLOCKS:
        return False, ""
    if not final_text or not DEFERRAL_RE.search(final_text):
        return False, ""
    return True, (
        "tofable-codex-gate(continuation): the final answer reads like an early stop or deferral. "
        "Before stopping, state whether this is a real blocker, whose decision it is, and how it was reported."
    )


def deny_payload(reason: str) -> dict[str, Any]:
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": reason}}


def block_payload(reason: str) -> dict[str, Any]:
    return {"decision": "block", "reason": reason}
