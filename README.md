# fable-work

**A method for transferring "how a strong model works" into a harness — rules + verification gates + a benchmark — so other models inherit the working style.**

`fable` is the name we give, in this project, to a model instance that developed an unusually good working style through extended real-world use: it decomposed goals honestly, verified before claiming completion, and reported blockers plainly instead of narrating around them. That style is not a weight update — it lived in habits, not parameters. `fable-work` is an attempt to encode that style externally, as a portable harness (situational rule files + mechanical verification gates), and then **measure** how much of it actually transfers to a different base model (e.g. an `opus`/`sonnet`-class model) once the harness is switched on.

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

The hooks in `hooks/` are the generalized, harness-agnostic form of the verification lifecycle: risk classification on new requests, a block-list for a small set of destructive local actions, a tool-use evidence ledger, and a capped "don't claim done without proof" stop-gate. Wire them into your coding-agent harness's hook/lifecycle system (see `hooks/` for the per-hook contract and any harness-specific adapter notes). If your harness is Codex specifically, see [Codex integration](#codex-integration) below — you likely want the upstream plugin instead of a manual port.

**2. Run the benchmark.**

```bash
cd bench
# see bench/ for the current runner and task manifest
```

The benchmark runs the same task set with the harness off (vanilla) and on, and reports the harness-dependent vs. general-reasoning split described above. Use it to check whether *your* harness install actually recovers the gap on *your* base model — the numbers above are one measurement, not a universal constant.

## Codex integration

If you're on Codex, prefer installing the upstream plugin this project's hook design was adapted from — `fable-ish-codex` (Apache-2.0, Pandoll-AI) — rather than manually porting `hooks/`. See [`codex/README.md`](codex/README.md) for install steps and how the two projects relate.

## Method

The full write-up of the transfer method — rule-pattern design, the verification ledger / stop-gate mechanism, and the benchmark loop used to measure transfer — is in [`docs/method.md`](docs/method.md).

## License

This repository's own contributions are licensed under the [MIT License](LICENSE). The hook design under `hooks/` is adapted from `fable-ish-codex` (Apache-2.0, Copyright Pandoll-AI); see [NOTICE](NOTICE) for the required attribution.
