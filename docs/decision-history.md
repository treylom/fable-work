# Decision history

Adopted / rejected decisions with reasons, so future sessions re-discover the
*reasoning*, not just the artifact. (Practice borrowed from
[fable-week](https://hugh-kim.space/fable-week.html) D5.)

## 2026-07-03 — fable-week adoption round

| decision | verdict | why |
|---|---|---|
| replay corpus (`hooks/tests/replay/`) | **adopted** | past violations become permanent regression fixtures; corpus-floor blocks the "delete fixtures to fake 100%" gaming vector |
| practice probes (`hooks/tests/probes/`) | **adopted** | replay checks *what* the gate blocks; probes check the pipeline's *contracts* (exit-code conventions, ledger schema, escape hatches) stay alive |
| requirements-lock (`hooks/requirements-lock.py`) | **adopted (opt-in)** | completion bias — deleting a feature to silence an error — is invisible to a verification gate; a signature lock makes it loud. Opt-in to keep install friction zero |
| substrate-check (`bench/substrate-check.sh`) | **adopted** | makes gate-substrate invariance a check (delta 0 = the deterministic guardrails survived the transition intact); behavioral model-independence is what bench/ measures |
| weekly-scoreboard cron | **rejected** | for a single-operator install the operating cost outweighs the value; substrate-check run by hand covers the trend question. Revisit if this repo grows CI |
| rule metabolism (242→91-style triage) | **rejected (n/a)** | our `rules/` layer is a small example set, not a bloated production corpus; the concept is documented in the plan for readers who have the bloat problem |
| rule-budget gate | **rejected (YAGNI)** | same reason as above — shipping a bloat gate for an example-sized rules layer is unused complexity; adopt only if a real installer reports re-bloat |

(The full adoption-round planning doc was an internal working file and is
kept out of the public repo; this table is the complete decision record.)
