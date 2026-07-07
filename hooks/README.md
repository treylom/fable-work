# Installing the fable verification hooks

These hooks are the mechanical half of `tofable`: an evidence ledger that
records what actually ran, and a stop-gate that won't let a turn end
claiming "done" on a harness/code change it never verified. They are plain
Python scripts driven over stdin/stdout — no dependencies beyond Python 3.

This guide is for **Claude Code**. The same two scripts work in any harness
that can run a command on a post-tool event and on a turn-end event; only
the wiring syntax differs. If you're on **Codex**, prefer the upstream
plugin instead — see [`../codex/README.md`](../codex/README.md).

## Design principle: every modification is attemptable

No gate in this directory hard-forbids an edit — not to code, not to config,
not to the agent's own instruction files (`CLAUDE.md`, rules, hooks,
`settings.json`). What the gates do instead:

- **surface** — a destructive command bounces once and passes when re-issued
  after the agent states what it destroys and why that's safe;
- **verify** — a harness/code-surface change (including rule/hook files)
  must show verification evidence before the turn may end;
- **expand** — an absence claim made after consulting only the checked-out
  view bounces once with the boundary-expansion checklist.

Every bounce is capped and fail-open, and the identical action goes through
on the follow-up. If you ever find a path where a gate says "no" with no
way through, that's a bug in the gate — file it.

## The files

| File | Role | Hook event |
|---|---|---|
| `fable_lib.py` | shared library (surface heuristic, ledger, gate logic, kill switch). The other two import it. | — |
| `verify-ledger.py` | records real verifications (test run / scan / cross-check) plus git-usage/boundary-expansion evidence as an ordered ledger. Records only, never blocks. Fail-open. | `PostToolUse` |
| `stop-verify-gate.py` | four checks: (1) if the turn changed a code/harness surface with no verification recorded since, bounce the stop; (2) if the final message asserts something doesn't exist after consulting git without an all-refs check (`git log --all` / `branch -a`), bounce once with the boundary-expansion checklist; (3) if it states a precise count / identity claim with no mechanical check in the tool log, bounce once; (4) if it declares completion after a subagent (Task/Agent) ran with no verification recorded **after** the delegate returned, bounce once — a delegate's "done" is a claim, not evidence. All capped, fail-open. | `Stop` |
| `continuation-gate.py` | if the final message declares an early stop or deferral ("I'll finish tomorrow") while work may remain, bounces the stop once with the three questions from [`../rules/continuation.md`](../rules/continuation.md). Capped at 1/session, fail-open. | `Stop` |
| `surfacing-gate.py` | if a Bash command carries a destructive token (recursive/forced `rm`, force-push, `reset --hard`, `find -delete`, `rsync --delete`, …), bounces it once and asks for the op, targets, and safety rationale in the visible reply; the identical command passes on retry. Capped per command + 5/session, fail-open. | `PreToolUse` |
| `blind-retry-gate.py` | if the immediately preceding Bash command failed and the incoming call re-runs it byte-identical, bounces once: name the failure cause, run one probe, or change the command. The identical re-run passes after the bounce (a deliberate transient-flake retry costs one bounce); any different command resets the chain. Capped 5/session, fail-open. | `PreToolUse` |

## Install (Claude Code)

**1. Get the files onto your machine.**

```bash
git clone https://github.com/treylom/tofable
```

(Or copy just the `hooks/` directory somewhere — if you do, adjust the
`tofable/hooks/...` paths in the commands below to wherever you put it.)

Pick a stable absolute path for the hook files — e.g. `~/.claude/fable-hooks/`:

```bash
mkdir -p ~/.claude/fable-hooks
cp tofable/hooks/fable_lib.py tofable/hooks/verify-ledger.py \
   tofable/hooks/stop-verify-gate.py \
     tofable/hooks/continuation-gate.py \
     tofable/hooks/surfacing-gate.py \
     tofable/hooks/blind-retry-gate.py ~/.claude/fable-hooks/
```

**2. Wire them into `~/.claude/settings.json`.**

Add the two hooks to the `hooks` block (merge with anything already there —
don't overwrite existing hooks). Use the **absolute path** from step 1:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          { "type": "command", "command": "python3 $HOME/.claude/fable-hooks/surfacing-gate.py" },
          { "type": "command", "command": "python3 $HOME/.claude/fable-hooks/blind-retry-gate.py" }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Write|Edit|Bash|Task|Agent|Read",
        "hooks": [
          { "type": "command", "command": "python3 $HOME/.claude/fable-hooks/verify-ledger.py" }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          { "type": "command", "command": "python3 $HOME/.claude/fable-hooks/stop-verify-gate.py" },
          { "type": "command", "command": "python3 $HOME/.claude/fable-hooks/continuation-gate.py" }
        ]
      }
    ]
  }
}
```

`verify-ledger.py` goes on `PostToolUse` (matched to the tools that change
state or delegate work — `Write|Edit|Bash|Task|Agent|Read`; the `Task|Agent`
part anchors the subordinate-evidence check, so include it even if your
sessions rarely delegate. `Read` anchors that check's file-mediated
variant: reading a delegate-report file — a path matching
`worker-report` / `delegate_report` / `subagent-report` — counts as
consuming a delegate's claim, since much real delegation reports back
through a file rather than a Task/Agent return value; ordinary reads
never arm it); `stop-verify-gate.py` goes on `Stop`, which
takes no matcher — it always fires on every turn-end. All scripts find
`fable_lib.py` next to themselves, so keep them together.

> **If you already have `PostToolUse` or `Stop` hooks**, don't paste this
> block over the existing key — that silently clobbers them. `PostToolUse`
> and `Stop` are *arrays* of matcher-groups, so **append a new object** into
> the array you already have. E.g. adding to an existing `PostToolUse`:
>
> ```json
> "PostToolUse": [
>   { "matcher": "...", "hooks": [ /* your existing hook */ ] },
>   { "matcher": "Write|Edit|Bash|Task|Agent|Read", "hooks": [
>       { "type": "command", "command": "python3 $HOME/.claude/fable-hooks/verify-ledger.py" } ] }
> ]
> ```

**3. Confirm it's actually wired (don't assume).**

```bash
python3 tofable/hooks/tests/test_gate.py
```

This drives the hooks as real subprocesses and asserts the gate blocks when
it should and passes when it should. A green run is the runnable proof the
gate is live — which is the whole point (a rule you can't see fire isn't
enforcement).

## Turning it off / scoping it

Environment variables, read by `fable_lib.py`:

| Env var | Effect |
|---|---|
| `FABLE_GATE_OFF=1` | kill switch — disables the stop-gate entirely (the ledger still records; nothing blocks). |
| `FABLE_GATE_PILOT=<name>` + `FABLE_SESSION_NAME=<name>` | scope the gate to **one** named session, so you can pilot it on a single bot/agent before enabling it everywhere. With neither set, the gate is active for every session. |
| `FABLE_STATE_DIR=<dir>` | where the evidence ledger is written (default: outside the project tree, so verification bookkeeping never gets committed). |

The gate is deliberately narrow: it only fires on harness/code-surface
changes, never on plain notes/markdown, and it's capped at
`MAX_STOP_BLOCKS` bounces so it can't loop forever on genuinely-stuck work.
It fails open — any exception in the hook exits cleanly rather than wedging
your session.
