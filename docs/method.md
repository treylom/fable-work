# Method: transferring a working style into a harness

## The problem

A capable model, used in earnest even for a short while, tends to end up wrapped in a genuinely good working style — goals decomposed honestly, work verified before completion is claimed, blockers reported plainly instead of narrated around. That style lives in accumulated habit and scaffolding *around* the model, not in the model weights. When you move to a different model (a new version, a cheaper tier, a different provider's model), none of that habit carries over automatically. The new model is generally competent, but it doesn't know your house rules, and — separately — even a model that's been told the rules doesn't reliably enforce them on itself under time pressure.

`fable-work` treats "working style" as something you can encode *outside* the model, in three layers, and then measure whether the encoding actually recovers the behavior gap.

## Layer 1 — rule patterns

Rules are written, but not front-loaded. Dumping every house rule into an always-loaded system prompt causes context bloat and, empirically, worse recall of any individual rule — the model has too much to hold onto and nothing tells it which rule is relevant *right now*.

Instead, rules are organized as:

- **An index** of situations → rule files ("when you're about to do X, that's rule Y — go read it now").
- **Trigger-keyed rule files**, each scoped to one situation (editing code, delegating to a sub-agent, reporting completion, writing to shared storage, etc.), read on demand rather than held in context permanently.
- **Rules that encode "how", not just "what".** A rule isn't "be careful when editing" — it's "before editing a function, enumerate its callers and check blast radius; after editing, run these three verification passes before calling it done."

This keeps the always-loaded footprint small while still making the right rule reachable exactly when it's needed.

Copyable examples of this shape — an index plus two rule files mined from real sessions — ship in [`rules/`](../rules/).

## Layer 2 — verification gates

Rule patterns alone are necessary but not sufficient — see the [key finding](../README.md#key-finding) that a rule can sit unenforced even when the model "knows" it. The gate layer makes verification mechanical instead of advisory:

- **Risk classification on new requests.** Not every task needs the same scrutiny; classify quick/normal/deep/blocked and scale the guardrails to the risk, not uniformly to the maximum.
- **A pre-action block-list** for a small, explicit set of destructive or irreversible local actions (destructive deletes, destructive history rewrites, infrastructure teardown). Deliberately narrow — a gate that blocks too much just gets routed around or disabled, which is worse than no gate.
- **A tool-use evidence ledger.** Every meaningful tool call (a test run, a build, a file change) gets recorded — what actually ran, what it actually returned, pass or fail — independent of what the model *says* it ran. This is the mechanism that closes the "confident narration vs. actual evidence" gap: a model under time pressure will describe verification it didn't do unless something outside its own token stream is keeping score.
- **A capped stop-gate.** Before a turn can be reported as "done" on non-trivial work, the gate checks the evidence ledger for verification matching the task's risk class. If it's missing, the gate pushes the model to continue rather than accepting the completion claim — capped at a small number of retries so it can't loop forever on a task that's genuinely stuck.

The gate only has teeth if it can fire in practice. In our first measurement pass, the ported stop-gate blocked its own author's session mid-task — an unplanned but useful confirmation that the mechanism was live rather than aspirational documentation. A rule you've never seen fire is a rule you don't actually know is installed.

## Layer 3 — benchmark loop

Layers 1 and 2 are a hypothesis about what will improve behavior. The benchmark loop is how you check the hypothesis instead of trusting it:

1. **Build a task set that spans two categories:**
   - *Harness-dependent* tasks, where the "correct" behavior is a specific written house rule the model has no way to infer from general competence alone (e.g., "outline before you build a slide deck," "editing an existing image is a different operation from generating a new one," "delegate research instead of guessing from memory").
   - *General-reasoning* tasks, where a competent model should score well regardless of any house rule (fact-checking, summarizing, structured writing, saving/organizing information).
2. **Score the target model with the harness OFF (vanilla)** across both categories.
3. **Compare the two categories.** A large gap on harness-dependent tasks with a small gap (or none) on general-reasoning tasks tells you the model's underperformance is mostly an *instruction-coverage* problem — the model is otherwise fine, it just never saw the rule — rather than a *capability* problem. That gap is what turning the harness on is expected to recover; if the model were also weak on the general-reasoning set, no amount of house-rule injection would fix it, and you'd be looking at a capability limit instead.
4. **Turn the harness ON and re-run.** Confirm the harness-dependent scores move toward the general-reasoning baseline. Watch for two distinct failure modes: rules that should have fired and didn't (false negatives — the transfer didn't work), and gates that blocked legitimate work (false positives — the transfer over-corrected).
5. **Sanity-check the grading, not just the model.** Before attributing a low score to the model, check whether the benchmark can actually see the model's work. In our pass, preserving full tool-use transcripts (instead of grading from the model's self-report) alone raised a security-flavored benchmark from 93 to 96 — over half of what looked like a capability gap was really the grader missing evidence of work that had, in fact, been done correctly. Any harness-vs-vanilla delta should be read next to this kind of instrumentation check.

## The mining loop — where rules come from

The rule layer is a living artifact, not a one-time export. New rules come from **mining real session transcripts**:

1. **Extract episodes.** Walk the transcript for concrete moments where the model did something distinctly good (transfer-worthy) or bad (a failure mode) — each episode needs quoted evidence, not a vibe.
2. **Dedupe against known patterns.** Most episodes re-instantiate rules you already have; those confirm coverage but don't become new rules. Only genuinely new patterns, meaningful refinements, and fresh failure modes graduate.
3. **Fold the survivors into the harness** — usually a one-line addition to an existing rule file rather than a new file. Resist encoding a rule from a single occurrence; a pattern seen once is a note, seen twice is a candidate, seen under pressure is a rule.

Two hygiene checks that live mining taught us:

- **Attribute behavior to the right model.** Sessions can silently mix models (fallbacks, mid-session switches). Before encoding a failure into a model's profile, check the per-turn model metadata — we once nearly filed one model's high-context tool-call corruption under a different model's name. An episode without attribution is unusable.
- **Cross-model recurrence is a signal, not noise.** When the same good habit (say, reporting a blocker plainly instead of narrating around it) shows up in *both* models' segments of a mixed session, the habit probably comes from the harness — the hooks and standing rules — rather than the weights. That's not a confound to control away; it's the transfer working, observed in the wild.

A concrete example: the "verify the verifier" line in [`rules/verification.md`](../rules/verification.md) was mined from a live session where a registration script printed success while its own check printed `False` — the model resolved the conflict by building a third, stricter measurement, and that move graduated into a rule the same day.

## Applying this to a new base model

1. **Inventory** the source persona's accumulated rules/skills and extract them as portable, trigger-keyed rule files — generalized, with any environment-specific names, paths, or identifiers stripped. Then keep the [mining loop](#the-mining-loop--where-rules-come-from) running on new sessions.
2. **Build the hook layer**: pre-action risk classification and a narrow destructive-action block-list, a post-action evidence ledger, and a capped stop-gate that checks the ledger before accepting a completion claim. *(This repo's `hooks/` ships a subset of that layer — the evidence ledger and the stop-gate. The risk classifier and destructive block-list live in the upstream Codex plugin the hooks were adapted from, not in `hooks/`.)*
3. **Build or reuse a benchmark** spanning harness-dependent and general-reasoning tasks, per the split above.
4. **Measure vanilla**, install the harness, **measure again**. Look at the gap, and at the specific failure modes (missed enforcement vs. over-blocking) rather than only the aggregate score.
5. **Iterate on measurement, not vibes**: tighten rules that under-fire, scope down rules that over-fire, and re-run the benchmark rather than trusting that a rule change "should" help.

## See also

- [`README.md`](../README.md) — the current measurement results
- [`rules/`](../rules/) — copyable example rule layer (index + trigger-keyed rule files)
- [`codex/README.md`](../codex/README.md) — how the hook lifecycle maps onto Codex specifically, and the upstream project (`fable-ish-codex`) it was adapted from
- [`hooks/`](../hooks/) — the generalized, harness-agnostic hook implementations
- [`bench/`](../bench/) — the task set, scoring, and raw per-task results
