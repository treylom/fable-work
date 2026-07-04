# Case study: closing the loop — from one day's friction to two hooks

This is a worked example of the fable-work cycle: **measure friction →
map it against a benchmark → find where discipline exists only as prose →
harden the gap into a hook.** The whole cycle ran in one day, and the two
hooks that came out of it ship in this repo (`hooks/cutover-review-gate.py`,
`hooks/branch-stray-guard.sh`).

## 1. Inputs

**Friction log.** One working day across a multi-agent setup produced five
recorded frictions:

1. a deliverable bounced because the builder verified against its own spec,
   not the requester's original wording;
2. two verification blind spots — a `grep` for a marker string returned a
   false miss (the renderer had split the string across comment chunks), and
   an asset check greened on "reference exists" while the URL actually
   served a 307 redirect to an HTML login page;
3. a UI change went live with the designated reviewer's verdict recorded
   nowhere (solo deploy);
4. a delivery pipeline's failure exit was masked by a trailing `tail` pipe
   (the safety check read the pipe's exit, not the command's);
5. a dispatch message quoted a file path that no longer existed — a
   compaction summary had preserved the path but not the fact that it was
   stale (phantom path).

**Benchmark.** A published harness experiment (the "one-year roadmap in one
session" run) demonstrates five enforcement points worth stealing:
tri-gated completion (order / provenance / re-run verify, each `exit 2`),
content-marker verification instead of existence checks (`test -s` is
touch-gameable), closed-loop proof by resolvable links, revision-log gates
at phase boundaries, and honest NA reporting.

## 2. The mapping

Each friction was mapped to the benchmark axis that would have prevented
it, then checked against the *actually installed* rules and hooks (by file
and line, not by memory):

| friction | benchmark axis | installed? |
|---|---|---|
| requester-intent mismatch | tri-gated completion | rule existed (recently added) — needed hardening only |
| grep false-green ×2 | content-marker verification | **prose only** — no rule or hook mentioned final-status/content-type checks |
| solo deploy | completion gate | gate existed **for a different artifact class only** |
| pipe exit masking | verify exit integrity | a memory note existed; no rule, no hook |
| phantom path | closed-loop link resolution | three prose rules in the same spirit; nothing enforced at dispatch time |

The headline: **four of five frictions had the discipline written down
somewhere and enforced nowhere.** Knowing ≠ enforcing — the exact gap the
benchmark's `exit 2` culture closes.

## 3. What got built

- **`cutover-review-gate.py`** (from friction 3): a Stop-hook that bounces a
  turn declaring "cutover/deploy complete" when no reviewer verdict
  (PASS/GREEN) exists in the session transcript. Completion declarations
  become evidence-bearing, like every other "done".
- **`branch-stray-guard.sh`** (from a sixth friction found *while testing*
  the phantom-path hook — see below): a warn-only guard for unattended
  commits that land knowledge files on a feature branch, where they later
  read as mysteriously deleted.
- A dispatch-time phantom-path check (friction 5) was installed in the
  private harness; its generalization is the simplest of the three — extract
  path-like tokens from an outgoing dispatch message when they appear in a
  "read this first" context, and warn if they don't resolve.

## 4. The loop actually closed

Two details make this a closed loop rather than a checklist exercise:

- The phantom-path hook's **first test run caught a real incident**: two
  files the team believed existed were absent — not deleted, but stranded
  on a feature branch by an unattended auto-commit. That discovery *is*
  friction 6, and it became `branch-stray-guard.sh` the same day. A hook
  built from friction found the next friction.
- Every adopted hardening links back to the friction record that motivated
  it (the benchmark's closed-loop criterion: proof is a link that
  resolves, not a narrative). Anything that mapped to no real friction was
  explicitly *not* built — two benchmark axes stayed unadopted for lack of
  a motivating incident, recorded as such.

## 5. Reusable heuristics

- Audit your day against someone else's enforcement culture: list frictions
  first, benchmark second, and refuse forced mappings.
- Grep is a pre-filter, not a verifier: check final HTTP status,
  content-type and bytes, or a rendered view — a 30x is not a GREEN.
- Before declaring a file "gone", check the branch axis: `git log --all`.
- Prose rules that keep being violated are hook candidates; hooks should be
  fail-open, warn-first, and capped so they never eat work.
