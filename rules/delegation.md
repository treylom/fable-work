# Rule: delegating work

Trigger: you are about to hand a task to a sub-agent, a worker process, or another bot.

- **Complete HOW in the first message.** Goal-only dispatches drift, and each correction costs a full round-trip. The first message should carry: exact method and tools, what is forbidden, output format, and where to report. Self-test before sending: "could the worker do *exactly* what I want from this one message alone?"
- **Check capacity before dispatching.** A worker near its context / rate / resource limit will fall over mid-task, and the cleanup costs more than the wait. If it's low: have it checkpoint and wind down first, or pick another worker.
- **Ack ≠ execution.** After dispatching, verify the worker actually *entered* the task (observe its session or logs) — "on it" followed by idling is a common failure mode. Don't end your own turn on an unverified dispatch.
- **Verify results against sources, not narration.** Spot-check a delegated result against the primary sources it cites before amplifying it. Watch the ratio of citations to actual lookups — many citations from very few tool calls is a confabulation smell.
- **Scope changes propagate the same turn they happen.** If new information changes the spec mid-flight, patch the spec document and re-dispatch the delta immediately — "I'll update the doc when it's over" is where drift starts.
