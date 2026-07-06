# Rule: continuation before stopping

Trigger: you are about to stop, defer ("I'll finish this tomorrow / after the review"), scale down, or wrap up a session while unresolved goals remain.

Stopping early is a failure mode, not a safety feature. Field logs show premature stops commonly fall into five buckets: over-cautious halts that never checked existing safety nets, self-declared deferrals, approval gates that quietly became bottlenecks, treating a hung or dead process as "still waiting", and stalling silently without telling anyone.

Three questions to pass before any early stop (the stop-gate in [`hooks/`](../hooks/) — `continuation-gate.py` — surfaces exactly these questions, mechanically):

- **Is this a real technical blocker?** Check the safety nets that already exist (auto-compaction, backups, retries, rollback paths) before halting out of caution. Low remaining context is not a stop reason when the runtime compacts automatically. Mined from a session where an agent halted three separate times "to be safe" — each time the safety net it hadn't checked would have carried it through.
- **Whose call is it?** Finishing early, deferring to tomorrow, and closing the session are the user's decisions. Do not declare them on the user's behalf while goals remain open. Default is to keep going; the user interrupts when they want to stop.
- **Have you said so?** If you are genuinely blocked, report the blocker explicitly instead of going quiet. A stall the user knows about is recoverable; a silent one is not — in our logs, the silence was consistently judged worse than the stall itself.

When something stops responding, classify it before waiting on it:

| State | Signal | Remedy |
|---|---|---|
| **waiting** | legitimate anchor + expected duration known | leave it alone; suppress liveness nags |
| **hung** | progress assumption broken, no output past a time cap | escalate past the cap — don't extend it |
| **dead** | process exited / blocked on interactive input | restart or hand to a human; a mention won't reach it |

Treating all three as "waiting" is how multi-hour stalls happen. Mined from a real 4.5-hour stall where a worker acknowledged a task and then produced nothing — the acknowledgement itself had cleared the "unhandled mention" alarm that would otherwise have fired.
