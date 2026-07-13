# Gate audit playbook — decide which gates each bot/agent actually needs

This is the reusable form of a live audit we ran on 2026-07-13 across a
6-bot Claude Code fleet plus two Codex bots (7 days of transcripts, 94 real
gate blocks labeled one by one). The question it answers: **"is this harness
too heavy, and which gates should THIS agent run?"** — with measurements,
not vibes. Every step below names the trap we actually fell into before
finding the working method.

The five steps: **inventory → measure → label → rank → per-bot set.**

## Step 1 — Inventory: what is wired, and WHERE does it apply

List every hook wiring from every settings layer:

- user-global (`~/.claude/settings.json`) — applies to every session;
- project (`<cwd>/.claude/settings.json`) — **cwd-scoped**;
- per-agent working directories that carry their own `.claude/settings.json`.

**Trap (measured):** Claude Code does *not* merge parent-directory project
settings. A bot whose working directory is a subfolder of your repo does NOT
inherit the repo root's `.claude/settings.json` — our root "full stack"
turned out to apply to exactly one bot. If your fleet assumes shared hooks,
verify with a controlled probe: add a no-op hook (append-to-file, no stdout,
exit 0) to the parent settings, run one headless session from the child cwd
(`claude -p "say ok"`), check whether the probe file got written, then
remove the probe. Two minutes, decisive, no side effects.

Note the layer split in your inventory: instruction files (CLAUDE.md chains,
rules) DO walk up to the repo root — hooks don't. "Rules apply to everyone,
gates apply per-cwd" was the single most decision-relevant fact of our audit.

## Step 2 — Measure: real events only

Run `scripts/audit/scan_gate_events.py` over your transcripts. It counts
only **real** gate events:

- Stop-gate blocks: `"Stop hook feedback:" + <reason text>` records;
- PreToolUse denies: `is_error:true` tool results carrying the reason text.

**Traps (all measured):**
- Grepping gate *names* counts your own documentation. Sessions that read or
  discuss hook source re-quote every string you search for. Match on the
  block-reason text, and treat any hit inside a code-read as contamination.
- Silent passes leave no transcript trace. Transcripts measure *blocks*;
  fire/pass rates need hook-side logging. Don't present block counts as fire
  counts.
- Hook-side audit logs over-count visible friction (one bounced stop cycle
  can log several hook fires — we measured 118 log lines vs 20 model-visible
  bounces for the same gate). Say which side each number comes from.
- If your hook log lines carry a meta/automation marker (ours: `isMeta`),
  anchor on it — naive grep inflated one gate's count 4x.

Also worth measuring, cheap: per-hook latency (pipe a dummy payload into
each hook, time it — ours ran 16–30ms each) and session-start context cost
(first assistant turn's `cache_creation_input_tokens` in a fresh transcript
— separates "gates are heavy" from "the prompt front-load is heavy"; for us
the front-load dwarfed every gate).

## Step 3 — Label: read what the agent did NEXT

For each real event, read the following turn and label:

- **true positive** — the agent changed behavior for the better (ran the
  missing verification, corrected an unverified count, caught a real gap);
- **false positive** — the agent argued the gate was wrong and was right
  (stale state, misattribution), or just re-issued the same thing;
- **friction** — technically correct but useless (re-bounce of something
  already answered, double-deny of a re-worded command).

Labels are the audit's value — counts alone can't tell a gate that saves
you from one that nags you. Our labeling flipped the intuitive conclusion:
the "heavy" verification gates were 70–100% true-positive, while the
lightest-looking gate (a workflow reminder) was ~0/8 useful — and the fixes
that mattered were *false-positive repairs*, not removals.

## Step 4 — Rank: cost × value × noise

Put every gate/injector in one table: fire cost (tokens injected, latency),
block count, TP/FP/friction split, and a disposition:

- **keep** — high TP, low noise;
- **keep + repair** — high TP but a measured friction pattern (fix the
  pattern: scope the bounce message to the current turn, dedupe repeat
  bounces, let a re-worded command pass once when token AND target match);
- **narrow** — fires in contexts where it can't add value (exempt those
  contexts explicitly rather than turning it off);
- **off / owner decision** — no measured value; if the gate encodes an
  owner's explicit workflow contract, narrowing/off is the owner's call.

Repairs should be red-first: reproduce the measured friction as a failing
test, fix, keep the full battery green.

## Step 5 — Per-bot set: classify gates by TRIGGER, not by bot

Classify each gate before assigning it:

- **A. bot-exclusive** — only one bot's domain can trigger it (an
  orchestrator's dispatch check, one persona's writing gate). Bot-guard
  early-exit is safe and recommended.
- **B. content-triggered** — the *content* triggers it (a destructive
  command, an unverified count, a completion claim). Any bot can produce
  that content, and the gate is already self-scoping (silent-pass cost
  ≈ tens of ms). **Do not bot-guard these** — excluding bots creates silent
  coverage holes exactly where cross-domain work happens.
- **C. universal discipline** — applies to all bots by definition.

Then the per-bot matrix almost writes itself: B and C gates go everywhere
(the surprise of our audit: the "weight" fear pointed at gates that cost
nothing when idle); A gates go to their owners; the real decisions left are
(1) which bots were missing the safety-core B gates entirely, (2) automation
carve-outs — headless/cron sessions should skip stop-gates, and the env vars
that do that are **layer-specific** (check what each hook layer actually
reads; we found a documented env var that no layer implemented), and (3)
platform adapters (our Codex port shares the gate logic but needs its own
reply/turn-boundary adapters — share the rules as a single source of truth,
never fork their text per bot).

Pilot before fleet-wide: enable per bot behind a pilot flag
(`FABLE_GATE_PILOT`) for a week, re-run steps 2–3 on the new bot's
transcripts, then decide. False-positive rates measured on one bot do not
transfer automatically — work distributions differ.

## Outputs

A finished audit produces: the layer inventory, the labeled event set, the
ranking table with dispositions, red-first repair commits, and the per-bot
gate matrix. Ours took one focused day for a 9-bot fleet; the scanner and
the discriminators above were the whole trick.
