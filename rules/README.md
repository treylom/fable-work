# rules/ — example rule layer (Layer 1)

These are **generic, copyable examples** of the trigger-keyed rule files described in [docs/method.md](../docs/method.md#layer-1--rule-patterns). They are not our production house rules — those are environment-specific (real paths, bot names, project history) and stay private. What ships here is the *shape*, with two fully written examples mined from real sessions.

How to use:

1. Copy this folder into your harness workspace (e.g. `.claude/rules/` for Claude Code).
2. Keep `INDEX.example.md` (renamed to `INDEX.md`) referenced from your always-loaded prompt (CLAUDE.md / AGENTS.md / system prompt) — the index is the *only* always-loaded piece.
3. Read the matching rule file **only when a trigger row matches** the current situation.
4. Replace and extend the rows with your own house rules — one situation per file, encoding "how", not just "what".

Two rules of thumb that keep this layer healthy:

- **A rule earns its place by citing an incident.** Every "must/never" should trace to something that actually went wrong (or visibly right) in a real session. Rules invented in the abstract over-constrain and get routed around.
- **Don't front-load.** If rule bodies end up pasted into the always-loaded prompt "to be safe", recall of *all* rules degrades. The index is the contract; the bodies stay on disk until triggered.

Where new rules come from — mining real session transcripts — is described in [docs/method.md](../docs/method.md#the-mining-loop--where-rules-come-from).
