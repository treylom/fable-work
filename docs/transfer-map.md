# Transfer map — which part of the working style goes where

Design doc, 2026-07-12. The question this answers, end to end ("from the
trees to the forest"): **take each role the source model actually played in
real work, and pin it to the harness surface that can carry it** — a hook
event, a rules-layer file, or the `/tofable` skill — on both Claude Code and
Codex. The role inventory below is grounded in a full-corpus readout of real
session logs (31,727 session transcripts deterministically swept; 317
digest chunks deep-read across ~380 grader subagent passes; 542 gate ledgers aggregated), not
in introspection.

## Placement principle (the forest)

A role goes to the **strongest surface that can actually carry it**:

| If the role is… | it belongs in | why |
|---|---|---|
| checkable by machine against evidence (a command ran, a file changed, a count exists) | a **hook** (gate) | prose can be skimmed; a bounced Stop cannot. "A written rule is not enforcement." |
| a judgment call that needs situation context (when to stop, whose call a decision is) | a **rules file** (situation-keyed, routed by an index) | judgment can't be mechanized without false positives; rules put the criteria in front of the model at the moment they apply |
| a procedure — an ordering of steps the model should walk through | the **skill** (`/tofable`) | skills are invocable checklists; they make the evidence *exist* before the gate ever has to demand it |
| a property of the model's weights (raw judgment under ambiguity) | **not portable** — measure it in `bench/` instead | the harness scaffolds behavior; it does not add reasoning capability |

The skill and the gates are deliberately twinned: the skill is the proactive
form (walk the discipline), the gates are the reactive form (bounce a stop
that skipped it). Rules sit between: always-routable judgment criteria.

## Surfaces available (the trees)

Verified against a live install of each harness (2026-07-12):

| Lifecycle point | Claude Code | Codex | Gate(s) riding it |
|---|---|---|---|
| session start | `SessionStart` | `SessionStart` | rules/index injection (Claude side is where always-loaded rules arrive) |
| prompt submitted | `UserPromptSubmit` | `UserPromptSubmit` | fresh per-session ledger init (Codex port); situation-rule routing |
| before a tool runs | `PreToolUse` (matcher, can deny) | `PreToolUse` (matcher, can deny) | surfacing-gate, blind-retry-gate, prompt-advance |
| after a tool returns | `PostToolUse` (matcher) | `PostToolUse` (matcher) | verify-ledger (records only) |
| agent wants to stop | `Stop` (can block) | `Stop` (can block) | stop-verify (3 checks), subordinate-evidence, continuation-gate |
| subagent stops | `SubagentStop` | — | verify-ledger (delegate anchor — records the delegate's return so the subordinate-evidence check demands verification *after* it) |
| pre-compaction | `PreCompact` | — | state-of-truth flush (keeps discipline context across compaction) |
| session end | `SessionEnd` | — | (unused) |

Codex lacks the last three; the degradations are acceptable because nothing
gate-critical rides them (see `adapters.md` for the general contract, which
also covers runtimes with fewer interception points).

## Role × surface matrix

Roles are ordered by how often the readout saw them carry real work. ✅ =
implemented in this repo today; ◻ = rules/skill guidance only (no mechanical
check possible or wanted).

| # | Role the source model played | Hook (mechanical) | Rules layer | `/tofable` skill step |
|---|---|---|---|---|
| 1 | verify before claiming done | ✅ `verify-ledger` + `stop-verify` (Stop) | `verification.md` (grade ladder, verify-the-verifier) | step 2 & 4 |
| 2 | honest completion — gaps stay listed, numbers need mechanical checks | ✅ claim-evidence check (Stop) | `verification.md` | step 4 |
| 3 | complete-HOW delegation; a delegate's "done" is a claim | ✅ subordinate-evidence check (Stop) | `delegation.md` | step 2 |
| 4 | don't conclude absence from a shallow look | ✅ absence check (Stop) | (write your own — boundary expansion) | step 2 |
| 5 | surface destructive actions before running them | ✅ `surfacing-gate` (PreToolUse) | — | step 2 |
| 6 | diagnose before re-attacking a failure | ✅ `blind-retry-gate` (PreToolUse) | — | step 2 |
| 7 | refine the task into a real prompt/spec before executing | ✅ `prompt-advance` (PreToolUse — Claude Code only today; no Codex port yet, registered under Codex parity rules) | — | step 1 (+ `/prompt` integration with plain-prompting fallback) |
| 8 | no silent deferral while work remains | ✅ `continuation-gate` (Stop) | `continuation.md` (waiting / hung / dead triage) | step 3 |
| 9 | honest decomposition into verifiable units | ◻ (not mechanizable without false positives) | — | step 0 |
| 10 | report blockers immediately, with whose-decision routing | ◻ | `continuation.md` | step 3 |
| 11 | judgment under ambiguity (gating a risky step, honoring a constraint) | — not portable; measured in `bench/` (orchestration 96.3 vs 88.3, constrained-writing 93.3 vs 76.7) | | |

Mined rows from the 2026-07-12 full-corpus readout (317 digest chunks →
564 style patterns + 371 incidents → 24 rule candidates → 9 survived
adversarial verification against existing assets):

| # | Mined role / failure axis | Surface it landed on |
|---|---|---|
| 12 | quote/attribution fidelity in delegated or transcript-based output (9+ recurrences) | `rules/verification.md` ("quotes are verified mechanically") — gate upgrade candidate for claim-evidence |
| 13 | batch deliverables verified per-item, not by sample (4 recurrences) | `rules/verification.md` ("a sample is not a batch") |
| 14 | parallel delegations tracked per-delegate — the subordinate-evidence gate's single session watermark is a **verified mechanical gap** (any one verification passes the whole parallel set) | `rules/delegation.md`; per-delegate anchors = next gate work (see cycle-2 runbook) |
| 15 | required-reading lists diffed against actual Read history (3 recurrences) | `rules/delegation.md` |
| 16 | watchers self-tested on real data variants; silent states proven silent (5 incidents, 2 false-stale storms) | `rules/automation.md` (new) |
| 17 | shared structured values checked against their consumer's schema (4 incidents, incl. a 128-reinjection loop) | `rules/automation.md` (new) |
| 18 | ambiguous option labels / conflicting directives restated before costly work (3 redos) | `rules/instruction-fidelity.md` (new) |
| 19 | literal paths used literally (3 incidents) | `rules/instruction-fidelity.md` (new) |

15 further candidates were **rejected** by the adversarial pass — mostly
because an existing rule or memory already covered them more precisely, in
two cases because the cited evidence didn't survive source-checking. The
kill list is part of the method: a rule layer that only ever grows collects
duplicates, and duplicates dilute attention.

## Ledger v5.1 — a tuning example of the same principle

The 542-ledger aggregation found the stop-verify ordering anchor bouncing
~96% of change sessions, **all** of which already carried verification
evidence — the dominant real pattern was "verify the code, then edit a
rules .md last". Fix: only *executable* gated changes (code/config/settings,
non-prose harness files) stale prior verifications; prose harness edits stay
gated but keep already-earned evidence. That is the placement principle
applied to the gate itself: the mechanical check must track what evidence
can actually exist for a given change kind.

## Codex parity rules

- Every gate that lands in `hooks/` (Claude) must land in `codex/gates/`
  (Codex) in the same change, or state why not — the two ports share ledger
  schema and the parity test suite (`codex/gates/tests/`).
- Registered exceptions (stated per the rule above): `prompt-advance-gate`
  has no Codex port yet (its trigger reads Claude-transcript plan/interview
  markers that need a Codex-side equivalent first); the opt-in gates
  (`cutover-review`, `requirements-lock`, `branch-stray-guard`) are
  Claude-side only until someone actually opts in on Codex.
- Registered gap (2026-07-13 weight-audit ②): ledger v5.2 (`changed_path_seqs`
  current-turn scoping, `stop_bounced_sets` re-bounce dedup,
  `surfacing_pending_token/paths` recomposition pass) landed on the Claude
  side only — the Codex-side equivalent is owned by the Codex adapter track
  from the same meeting (per-owner boundary: Claude hooks vs Codex gates were
  deliberately split to avoid concurrent edits; see
  `meetings/2026-07-13-tofable-weight-audit/02-progress.md`).
- Codex skill form: the same skill directory ships in a plugin with a
  `.codex-plugin/plugin.json` (`"skills": "./skills/"`); slash commands do
  not exist on Codex, so anything shipped as a Claude `commands/*.md` needs
  a skill-form wrapper to be invocable there.

## Changelog

- 2026-07-12 — initial map; ledger v5.1 tuning; `/tofable` skill (dual
  platform) introduced; roles 1–10 verified against the full-corpus readout.
- 2026-07-13 — mined rows 12–19 landed (2 rule files extended, 2 new rule
  files); PostToolUseFailure wiring (failing tool calls fire a separate
  event on current Claude Code — without it the blind-retry gate never
  arms); SubagentStop as delegate anchor; known gap registered: per-delegate
  verification anchors for parallel delegation (subordinate-evidence
  currently session-scoped).
- 2026-07-13 (rereview) — line-by-line rereview fixes: bare "N개" Korean
  phrasing no longer reads as a count claim; ledger load→save serialized
  with flock; Stop-time transcript reads capped to a 400KB tail; Codex
  `UserPromptSubmit` now seeds the ledger on first touch only (it was
  wiping pending obligations every user turn); prompt-advance parity gap
  registered above.
- 2026-07-13 (weight-audit ②, ledger v5.2) — friction repairs measured from a
  7-day live-transcript audit of every gate event (94 real blocks labeled):
  stop-verify bounces now name only paths changed since the last successful
  verification and the same unverified set bounces at most once per session;
  surfacing-gate's one-shot pass survives benign recomposition of the same
  token+target (double-deny pairs measured live, target-overlap guarded);
  prompt-advance narrowed to substantial solo starts (meeting-SoT-engaged
  sessions exempt — measured 0-1/8 value ratio came entirely from
  meeting-dispatched sessions). Red-first: 11 new tests
  (`hooks/tests/test_weight_audit_repairs.py`), full battery green.
