# Rule: delegating work

Trigger: you are about to hand a task to a sub-agent, a worker process, or another bot.

- **Complete HOW in the first message.** Goal-only dispatches drift, and each correction costs a full round-trip. The first message should carry: exact method and tools, what is forbidden, output format, and where to report. Self-test before sending: "could the worker do *exactly* what I want from this one message alone?"
- **Check capacity before dispatching.** A worker near its context / rate / resource limit will fall over mid-task, and the cleanup costs more than the wait. If it's low: have it checkpoint and wind down first, or pick another worker.
- **Ack ≠ execution.** After dispatching, verify the worker actually *entered* the task (observe its session or logs) — "on it" followed by idling is a common failure mode. Don't end your own turn on an unverified dispatch.
- **Verify results against sources, not narration.** Spot-check a delegated result against the primary sources it cites before amplifying it. Watch the ratio of citations to actual lookups — many citations from very few tool calls is a confabulation smell.
- **Trust artifacts, not "done".** A worker's completion text is not output. Check that the claimed files exist with fresh timestamps and distinct hashes (one cached image copied under six names once passed as six results), and assert counts on batch outputs — structured returns truncate silently. Six consecutive false "done" reports in our logs came from workers that never called a tool at all.
- **Disambiguate scope verbs before acting on them.** "Register the automation" is not "run it now"; "fix the format" is not "replace the content"; "all N items" is not any subset of them. Each of these cost a real redo (one with the user shouting). When the scope word is ambiguous, one clarifying line is cheaper than the wrong interpretation executed well.
- **Decompose multi-part instructions into a checklist first.** Executing a 7-part instruction by gist produced 8 mistakes in a day. Write the checklist, execute against it, and diff the result against the *original wording* — not your memory of it — before reporting done.
- **Scope changes propagate the same turn they happen.** If new information changes the spec mid-flight, patch the spec document and re-dispatch the delta immediately — "I'll update the doc when it's over" is where drift starts.
- **Parallel delegations are verified per-delegate, not per-session.** *(mined 2026-07-12)* When several delegates run in parallel, "one of them was verified" quietly becomes "all of them are done" — our own subordinate-evidence gate carries exactly this blind spot (a single session-level watermark; any one verification after the last delegation passes the whole set). Track each delegation to its own completion signal, and confirm each artifact actually landed in the shared state-of-truth (commit, push, live file) before reporting the batch complete.
- **A required-reading list is checked against Read history, not memory.** *(mined 2026-07-12 — 3 recurrences)* When a dispatch names must-read files, diff that list item-by-item against the files you actually opened before declaring yourself briefed; skipped items are named with a reason, never silently absorbed.
- **Reach for parallel structure when the work is parallel.** Exploration
  across many files, multi-angle review, research sweeps, and bulk
  repetitive transforms belong in subagents or a workflow fan-out — one
  context reading everything serially is slower AND fills up with noise
  that crowds out judgment. Keep sequential-dependent work (design → edit →
  verify on the same files) in your own hands. Quick test: if two parts of
  the task would not need to read each other's intermediate output, they
  can run as separate agents; if a stage needs *all* prior results at once,
  that stage is the barrier and everything else pipelines around it.
