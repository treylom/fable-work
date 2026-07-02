# fable-work

**A method for transferring "how a strong model works" into a harness — rules + verification gates + a benchmark — so other models inherit the working style.**

`fable-5` is a real model — Anthropic's Fable 5 (`claude-fable-5`), in the Claude 5 family. Even over just a few days of real use, the way we worked with it settled into a genuinely good *working style*: goals decomposed honestly, work verified before "done" was claimed, blockers reported plainly instead of narrated around. Much of that style isn't in the model's weights — it lives in the habits and scaffolding built up around the model. `fable-work` is an attempt to encode that scaffolding externally, as a portable harness (situational rule files + mechanical verification gates), and then **measure** how much of the working style actually transfers to other — often cheaper — models (e.g. a `sonnet`-class model) once the harness is switched on.

This repo is the public, generalized distribution of that harness. Internal names, paths, and identifiers from the environment it was developed in have been stripped; the logic and the measurement methodology have not.

> 🇰🇷 한국어: **[README.ko.md](README.ko.md)**

![infographic](./docs/infographic-en.png)

## Key finding

We benchmarked a model running **with** the harness (`fable-5`) against the same task set run **without** it, on a comparable general model (`sonnet-5`). The tasks split cleanly into two kinds:

| Task category | Example tasks | Vanilla avg score |
|---|---|---|
| **Harness-dependent** — the correct answer lives in a specific written house rule, not in general competence | deck-outline-before-build, image-edit-vs-generate, research-delegation | **~62** |
| **General-reasoning** — competent models get these right regardless of house rules | fact-check, cardnews, knowledge-save, writing | **~90** |

**The ~28-point gap is what turning the harness ON is expected to recover.** It isolates the part of "the model didn't do what we wanted" that is actually an *instruction-coverage* problem (the model never saw the rule) rather than a *capability* problem (the model can't reason well enough). Harness-dependent tasks are exactly the ones a rules-and-gates system is supposed to fix; general-reasoning tasks are a control group showing the same model is otherwise fine.

Two more findings from the same measurement pass, because they change how you should read any "harness helped" number:

- **A written rule is not enforcement.** The ported verification gate (the `Stop`-hook pattern described in [docs/method.md](docs/method.md)) actually blocked its own author's session mid-task. That's not a bug report — it's the proof that the gate was mechanically live rather than decorative documentation. If a rule never fires, you don't actually know it's wired in.
- **Some of the score gap is an instrument gap, not a model gap.** Simply preserving tool-use transcripts (evidence of what commands actually ran) instead of grading on the model's self-report raised the hard-security benchmark from 93 to 96 — the earlier lower score was largely the grader being unable to see work the model had actually done, not the model failing to do it.

### Scoreboard (harness ON)

| Benchmark | fable-5 | sonnet-5 |
|---|---:|---:|
| core-3 | 89.9 | 86.7 |
| hard-security | 96.5 | 95.2 |
| real-work-7 | 79.3 | 75.3 |

### Where `fable` and a comparable model differ — and why

Both columns run **with** the harness, so the `fable-5` vs `sonnet-5` gap isn't harness-vs-none — it's two harnessed models, and the useful question is *where* they diverge and *on what evidence*. The gap is not uniform:

- **It concentrates in judgment-heavy tasks.** Orchestration: **96.3 (clean)** vs **88.3 (P1)** — `fable-5` put a *hard gate* on a low-context worker (block-until-resolved + reassign) where the comparable model allowed "proceed if cleanup is hard," a skipped discipline. Constrained writing: **93.3** vs **76.7 (P1)** — `fable-5` honored a "no outside references" rule the other broke.
- **It nearly vanishes or reverses on mechanical tasks.** On plain secret-scan and code-fix, the comparable model *ties or beats* `fable-5` — at **~2.5–3× lower cost**.

The honest, evidence-backed read: **`fable-5`'s edge is judgment under ambiguity — gating a risky step, honoring a constraint, auditing more thoroughly — not a uniform lift.** You'd route mechanical work to the cheaper model. Per-task evidence for every one of these claims is in [`bench/results.md`](bench/results.md).

**How scoring works** (six axes A1–A5 + a task-specific SPECIAL, with P0/P1 defect gates, judged on the actual tool-use transcript) and the full **per-task results** are in [`bench/results.md`](bench/results.md); the axes/anchors are in [`bench/rubric.md`](bench/rubric.md) and the judging procedure in [`bench/judge-prompt.md`](bench/judge-prompt.md).

## Repo structure

```
fable-work/
├── README.md            — this file
├── LICENSE               — MIT (this repo's own contributions)
├── NOTICE                — Apache-2.0 attribution for the ported hook design
├── docs/
│   ├── method.md          — the transfer method: rule patterns, verification ledger/stop-gate, benchmark loop
│   └── infographic.png    — summary graphic (referenced above)
├── hooks/                 — harness-agnostic, generalized verification hooks (rule patterns + evidence ledger + stop-gate)
├── bench/                 — the harness-dependent vs. general-reasoning task set, scoring, and raw results
└── codex/
    └── README.md          — how to use this with Codex, via the upstream fable-ish-codex plugin
```

## Quickstart

**1. Install the hooks into your harness.**

`hooks/` is the generalized, harness-agnostic form of the verification lifecycle — three files:

- **`fable_lib.py`** — shared library. A "harness/code surface" heuristic decides which changed files require verification evidence (plain notes/markdown are exempt); an append-only evidence ledger records verifications (kept outside the project tree so it's never committed); and a pilot-gate kill switch (`FABLE_GATE_OFF=1`, or `FABLE_GATE_PILOT=<name>` to scope the gate to one named session before enabling it broadly). The other two hooks import it.
- **`verify-ledger.py`** — a `PostToolUse(Write|Edit|Bash)` hook. After a tool call, if the action is a real verification (a test run, a scan, a cross-check) it records that as evidence in an ordered ledger. It only records — never blocks. Fail-open (any exception exits cleanly).
- **`stop-verify-gate.py`** — a `Stop` hook. When the agent tries to end a turn *after* changing a harness/code surface with no successful verification recorded since that change, it emits `{"decision":"block"}` to bounce the stop once and tell the agent to actually verify. Capped at `MAX_STOP_BLOCKS`, passes through the loop-guard, fail-open — a broken hook never wedges a session.

Wire `verify-ledger.py` into your harness's post-tool-use event and `stop-verify-gate.py` into its stop / turn-end event; both import `fable_lib.py`. After wiring, run `hooks/tests/test_gate.py` — it's a runnable spec of the gate's contract. If your harness is Codex specifically, see [Codex integration](#codex-integration) below — you likely want the upstream plugin instead of a manual port.

**2. Run the benchmark.**

```bash
# run one fixture against one model, preserving the full tool-use transcript
bench/run.sh example-codefix <your-model-id> my-run

# artifacts land in $FABLE_BENCH_RUNS_DIR (default ~/.fable-bench/runs/):
#   work/  transcript.jsonl  raw-output.json  meta.json
```

Then grade the run with a judge — ideally a **different model family** than the one that produced it — feeding it `bench/rubric.md` + the fixture's answer key + the run's transcript, via the template in `bench/judge-prompt.md`. Full runner options, how scoring is assembled, and the fixture-authoring / runtime-trap pattern are in [`bench/README.md`](bench/README.md) and [`bench/results.md`](bench/results.md).

The benchmark runs the same task set with the harness off (vanilla) and on, and reports the harness-dependent vs. general-reasoning split described above. Use it to check whether *your* harness install actually recovers the gap on *your* base model — the numbers above are one measurement, not a universal constant.

## Codex integration

If you're on Codex, prefer installing the upstream plugin this project's hook design was adapted from — `fable-ish-codex` (Apache-2.0, Pandoll-AI) — rather than manually porting `hooks/`. See [`codex/README.md`](codex/README.md) for install steps and how the two projects relate.

## Method

The full write-up of the transfer method — rule-pattern design, the verification ledger / stop-gate mechanism, and the benchmark loop used to measure transfer — is in [`docs/method.md`](docs/method.md).

## License

This repository's own contributions are licensed under the [MIT License](LICENSE). The hook design under `hooks/` is adapted from `fable-ish-codex` (Apache-2.0, Copyright Pandoll-AI); see [NOTICE](NOTICE) for the required attribution.
