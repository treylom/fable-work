# Porting the gates to other harnesses (adapter contract)

Design doc, 2026-07-08. Second-stage goal from the owner: the gates should
run not only on Claude Code and Codex but on any agent runtime that exposes
lifecycle hooks — Hermes-style plugin runners included. This document fixes
the **contract**; concrete adapters stay free to evolve (deliberately not
implemented here so each runtime port can find its own natural shape).

## What a runtime must provide

Three lifecycle interception points, each able to run an external process
and read its verdict:

| event          | when                                  | gate(s) that need it |
|----------------|---------------------------------------|----------------------|
| `pre-tool`     | before a tool/command executes         | surfacing, blind-retry, prompt-advance |
| `post-tool`    | after a tool/command returns           | verify-ledger (recorder — never blocks) |
| `turn-end`     | when the agent wants to end its turn   | stop-verify, continuation |

If a runtime lacks `turn-end`, the stop gates degrade to advisory: run them
on a timer or before the final user-facing message; they lose their
blocking power but keep their audit trail.

## Wire format

Adapters normalize the runtime's native event into the JSON the hooks
already read on stdin (this is the Claude Code shape — the codex/ port
translates to the same fields):

```json
{
  "session_id": "opaque-stable-per-session",
  "cwd": "/abs/working/dir",
  "tool_name": "Bash | Write | Edit | Task | ...",
  "tool_input": { "command": "...", "file_path": "..." },
  "tool_output": "post-tool only",
  "transcript_path": "/abs/path/to/session-transcript.jsonl"
}
```

Verdict channel: stdout JSON. A blocking verdict is
`{"hookSpecificOutput": {"permissionDecision": "deny", "permissionDecisionReason": "..."}}`
for pre-tool, and `{"decision": "block", "reason": "..."}` for turn-end.
Anything else (or exit non-zero, or garbage) MUST be treated as allow —
**fail-open is part of the contract**, not an implementation detail.

## State

All gates share one file-backed ledger keyed by `sha256(session_id|cwd)`
under `FABLE_STATE_DIR` (see `hooks/fable_lib.py:data_root`). Adapters only
need to guarantee: (a) a stable `session_id`, (b) a writable state dir,
(c) the same env var reaches every hook invocation. No database, no daemon.

## Runtime mapping sketches

- **Claude Code** — native `hooks` in settings.json (reference: repo README).
- **Codex** — `codex/gates/` port; events arrive via the gates' own
  wrapper (`hooks.json`), same ledger schema, 20-test parity suite.
- **Hermes-style plugin runners** (plugin.yaml `provides_tools`) — wrap each
  provided tool's entrypoint: call `pre_tool` adapter first (deny → return
  the reason as the tool result instead of executing), execute, then
  `post_tool`. Turn-end maps to the runner's response-finalize callback if
  one exists.
- **Bare CLI loops** (agent frameworks without hooks) — cheapest adapter is
  a PATH shim: a `bash`/`python` wrapper binary that runs pre-tool, then the
  real binary, then post-tool. Turn-end degrades to advisory (see above).

## Non-goals

- No shared daemon, no RPC — hooks stay single-shot subprocesses.
- No runtime-specific logic inside `hooks/*.py`; translation lives in the
  adapter. If a port needs a hook change, it is a contract change and this
  document must be updated first.

## Kill switches

`FABLE_GATE_OFF=1` disables everything; `FABLE_GATE_PILOT=<name>` scopes
enforcement to one session name. Adapters must propagate both.
