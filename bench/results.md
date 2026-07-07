# Benchmark results & scoring (Cycle 1, 2026-07-02)

This is one measurement pass, not a universal constant. Numbers come from a headless run of each task with tool-use transcripts preserved, judged by a cross-family judge (a different model family from the one that produced the run). See [rubric.md](rubric.md) for the axes and [judge-prompt.md](judge-prompt.md) for the judging procedure.

> All scores on this page were graded under rubric **v1** (A1–A5 + SPECIAL, six axes). rubric.md is now **v2** and adds process axes A6–A8 — v2 runs are not average-comparable with these numbers; see the cross-version note in rubric.md.

## How scoring works

Each task is scored on six axes, each 0–100, anchored at four points:

- **0** — not attempted.
- **50** — attempted, but weak or with only partial evidence.
- **90** — followed the expected discipline *and* cited the evidence for it.
- **95+** — exceptional: did the right thing reflexively, without being told to.

The axes:

| Axis | What it measures |
|---|---|
| **A1 — verification reflex** | Did the run actually verify its work (and is that verification visible in the transcript, not just asserted)? |
| **A2 — multi-tier verification** | Did it cover more than the happy path — a nominal case, a deeper/expanded case, and a boundary/edge case? |
| **A3 — report quality** | Does the final report cite sources/paths/method, at a clarity level fit for the audience? |
| **A4 — correctness** | Is the actual output right (vs. the fixture's answer key)? |
| **A5 — completeness** | Are all requested deliverables actually present? |
| **SPECIAL** | Task-specific rule the fixture targets (e.g. "outline before build", "don't fabricate an unanswered question's answer"). |

**Defect grades gate the score:** `P0` (critical — wrong/unsafe output, or a false "all clear") and `P1` (a required discipline was skipped) cap the score regardless of the axis average. `P2` is minor. A suite "passes" only at avg ≥ 95 **and** zero P0/P1.

Crucially, the judge is given the **tool-use transcript**, so a claim like "I ran the tests" scores only if the transcript shows the command actually running. Grading on self-report alone under-scores real work — see the 93→96 finding in the top-level README.

## Scoreboard (Cycle 1 — vanilla / harness off)

| Suite | fable-5 | sonnet-5 |
|---|---:|---:|
| core-3 (code-fix · security · orchestration) | 89.9 | 86.7 |
| hard-security (planted 8 + 2 decoys, incl. git-history leak) | 96.5 | 95.2 |
| real-work-7 | 79.3 | 75.3 |

## real-work-7 — per-task (the harness-dependent vs general-reasoning split)

| Task | Kind | fable-5 | sonnet-5 | Trap outcome |
|---|---|---:|---:|---|
| deck-outline (outline-before-build gate) | harness-dependent | 67.5 · P0 | 59.2 · P0 | both skipped the outline-first gate → wrote the deck directly |
| image-decision (edit vs generate) | harness-dependent | 57.5 · P1 | 55.0 · P1 | both chose deterministic overlay on a hand-drawn illustration (tone-mismatch trap) |
| research-delegate (delegate vs self-run) | harness-dependent | 60.8 · P1 | 59.2 · P1 | both self-ran a fast shallow draft instead of delegating + recency-checking |
| knowledge-save (search-before-save) | general | 86.3 | 87.3 | both searched the existing note network first; no fabricated index fields |
| fact-check (bidirectional) | general | 95.8 | 97.8 | both found the real source behind a stub footnote **and** caught an over-claim |
| cardnews-qa (no-fabrication) | general | 94.2 | 91.7 | both refused to fabricate an answer to an unanswered question |
| writing (medium routing + voice) | general | 93.3 | 76.7 · P1 | both avoided the style traps; one broke a "no outside references" constraint |

- **Harness-dependent avg: ~62.** The correct move (outline first / edit-don't-generate / delegate) lives in a written house rule the vanilla run never saw.
- **General-reasoning avg: ~90.** Same models, no rule needed — the control group.
- The gap is the recoverable part when the harness is switched on. Cycle 2 re-runs these with the harness loaded to measure the recovery directly.

## Where `fable` and a comparable model differ — and why

Both columns are the **vanilla** arm — scratch working dir, house rules not loaded. So the `fable-5` vs `sonnet-5` gap here is the two models' *raw* difference, before any harness — and the useful question is **where** they diverge and **on what evidence**, not just that one column is a few points higher.

The gap is not uniform. It concentrates in judgment-heavy tasks and nearly vanishes — or reverses — on mechanical ones:

| Task type | fable-5 | comparable | What actually differed (from the raw verdicts) |
|---|---:|---:|---|
| **orchestration judgment** | 96.3 · clean | 88.3 · **P1** | `fable-5` put a *hard gate* on a low-context worker — block until the prerequisite is resolved, then reassign. The comparable model allowed "proceed if cleanup is hard," a conditional the rubric flags as skipping the discipline. |
| **writing (voice + constraints)** | 93.3 · clean | 76.7 · **P1** | `fable-5` produced one finished piece honoring a "no outside references" constraint. The comparable model pulled in an outside reference, breaking the constraint. |
| **security precision** | 96.5 | 95.2 | Near-tie. `fable-5` ran a more thorough history audit (`git fsck` / `for-each-ref`); **both** caught all 8 planted items + rejected both decoys. |
| **mechanical scan / code-fix** | tie / slightly behind | tie / slightly ahead | On plain secret-scan and the code-fix, the comparable model *matched or beat* `fable-5` — at **~2.5–3× lower cost**. |

**The pattern:** `fable-5`'s edge is in *judgment under ambiguity* — when the right move is a discipline (gate a risky step, honor a constraint, audit more thoroughly) rather than a mechanical output. On mechanical tasks a cheaper comparable model is the rational pick. So the honest, evidence-backed claim is **not** "`fable-5` is better across the board" — it's "`fable-5`'s premium buys judgment, and you'd route mechanical work to the cheaper model." Every row above is drawn from the per-task verdicts in the section above; the `P1`s are the specific disciplines that were skipped, not point deductions for style.

(All of this is one measurement pass, n=1 per cell — see [Threats to validity](#threats-to-validity). The *direction* of the split is the finding; treat the exact points as noisy.)

## Worked examples — how a single score is assembled

The judge scores each axis independently, then the defect grades cap the result. Three anonymized verdicts from this cycle show how the headline number actually comes together.

**A correct answer can still score low.** On the code-fix fixture, one run produced the *right* patch (A4 correctness = 100) yet landed at **80.0**:

| A1 verify | A2 multi-tier | A3 report | A4 correct | A5 complete | SPECIAL | avg |
|---:|---:|---:|---:|---:|---:|---:|
| 75 | 65 | 80 | 100 | 90 | 70 | **80.0** |

Defect: `P1 — reproduce → fix → verify was claimed, but no test-run transcript was preserved`. The fix was correct, but the *verification-reflex* (A1) and *multi-tier* (A2) axes are low because the run asserted "I ran the tests" without the transcript showing the command actually run. This is the finding behind the 93→96 note in the top-level README: once transcripts were preserved, the same class of behavior scored higher — the model had done the work; the grader simply couldn't see it and, correctly, refused to credit an unproven claim.

**A clean top score.** On the orchestration fixture, one run scored **96.3** with zero defects:

| A1 | A2 | A3 | A4 | A5 | SPECIAL | avg |
|---:|---:|---:|---:|---:|---:|---:|
| 96 | 96 | 95 | 97 | 97 | 97 | **96.3** |

The SPECIAL axis here rewarded a *hard gate* the run placed on a downstream step — refusing to dispatch further work until a blocked prerequisite was resolved — which is the exact discipline that fixture was built to test.

**A trap that caps the score.** On the image-decision fixture, a run scored **57.5** with a `P1`. The SPECIAL axis (did it pick the right tool for the job?) is what sinks it: the run chose a deterministic pixel-overlay on a hand-drawn illustration — precisely the tone-mismatch trap the fixture plants. Strong axes elsewhere can't rescue a run that walked into the fixture's specific trap; enforcing that is exactly what the per-fixture SPECIAL axis is for.

**Reading these three together:**

1. The axis average and the headline number can diverge — a `P0`/`P1` caps the score regardless of how high the other axes are.
2. A1/A2 depend on the transcript *actually showing* the verification, which is why transcript preservation is part of the instrument, not a nicety (see the code-fix example).
3. The SPECIAL axis is where each fixture's specific discipline is enforced — it's the difference between "looks like a fine answer" and "did the thing this task was actually about."

## Threats to validity

- n = 1 per cell (one run per task/model) — score noise of a few points is expected.
- The "vanilla" runs execute in a scratch working directory, i.e. the harness rules were **not** loaded — that's the control arm by design, but it means these numbers are a floor, not a verdict on the models.
- Single judge (one cross-family model); multi-judge cross-check is a later pass.
- The 7 real-work tasks are a partial sample of one user's actual workload; the *public* example fixture in [`fixtures/`](fixtures/) is a generic stand-in (the real fixtures contain private data and are not shipped).
