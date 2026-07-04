# Codex integration

`tofable`'s hook design — request-risk classification, a destructive-action block-list, a tool-use evidence ledger, and a capped verification stop-gate (see [`docs/method.md`](../docs/method.md)) — is adapted from **`fable-ish-codex`**, a Codex plugin by Pandoll-AI:

- Repository: <https://github.com/Pandoll-AI/fable-ish-codex>
- License: Apache License, Version 2.0
- Copyright: 2026 Pandoll-AI

If your harness is Codex, the fastest and most maintained path is to install `fable-ish-codex` directly, rather than manually porting the generalized hooks under [`../hooks/`](../hooks/) in this repository.

## Install `fable-ish-codex` on Codex

1. Add the `fable-ish-codex` repository as a Codex plugin through your Codex plugin installation flow (marketplace install, or point Codex at the repo's `.codex-plugin/plugin.json` manually).
2. Restart Codex.
3. **Review and trust the bundled hooks** in the Codex hooks UI before relying on them — hooks that aren't trusted won't run. Codex discovers plugin hooks from `hooks/hooks.json` in the plugin.
4. Validate the install from the plugin's repository root:

   ```bash
   python3 -m json.tool .codex-plugin/plugin.json
   python3 -m json.tool hooks/hooks.json
   python3 -m py_compile hooks/*.py scripts/*.py tests/*.py
   python3 -m unittest discover -s tests
   ```

Once installed and trusted, you get the same four-stage lifecycle described in [`docs/method.md`](../docs/method.md):

| Stage | What it does |
|---|---|
| `UserPromptSubmit` | Classifies the incoming request as `quick`, `normal`, `deep`, or `blocked`, and injects compact task guidance accordingly. |
| `PreToolUse` | Blocks a small, explicit set of high-risk local actions (destructive deletes, destructive git history rewrites, infrastructure teardown, risky patch edits). |
| `PostToolUse` | Records changed-file signals, verification commands run, failures, and coarse coverage information to a small evidence ledger. |
| `Stop` | Requires verification evidence for normal/deep work before accepting a "done" claim, capped to avoid infinite continuation loops. |

By design, `fable-ish-codex` does **not** block `git push`, secret-output commands, deployment commands, database push commands, package publishing, migration-deploy commands, infrastructure apply/up commands, or permission-approval requests. It is a lightweight guardrail layer, not a full security boundary — see [Limits](#limits) below.

Optional extras from the upstream project, if you want stronger local policy:

- `rules/` — example command-policy rules, adaptable into an active Codex rules layer.
- `examples/permissions.toml` — an example secret-file access policy.

## Relationship between this repo and `fable-ish-codex`

- **`fable-ish-codex`** is the origin implementation: Codex-native, Apache-2.0, maintained by Pandoll-AI. If you're on Codex, prefer it — it's the maintained, native plugin.
- **`tofable`** (this repository) generalizes the same hook lifecycle for use in coding-agent harnesses other than Codex, and adds a benchmark loop (see [`bench/`](../bench/)) for measuring how much of the target "working style" transfer actually shows up in scored task performance rather than just being installed.
- Use [`../hooks/`](../hooks/) in this repo only if your harness is not Codex, or if you specifically need the harness-agnostic port. On Codex, the upstream plugin above is the more direct and better-maintained path.

## Limits

Hooks are guardrails, not a complete security boundary (inherited directly from the upstream project's own stated limits):

- Hooks must be reviewed and trusted before they run.
- `PreToolUse` does not intercept every possible execution path.
- `PostToolUse` cannot undo side effects from already-completed commands.
- The `Stop` gate is capped to avoid infinite continuation loops.
- Optional rules and permission profiles are examples, not silently-installed policy.

Use sandboxing, approvals, automated tests, linters, code review, and deployment policy for stronger enforcement than hooks alone can provide.

## License and citation

`fable-ish-codex` is licensed under Apache-2.0. If you use or adapt it, retain its license/attribution notices and consider citing it via its `CITATION.cff`. See [`../NOTICE`](../NOTICE) in this repository for how `tofable` itself attributes the adapted portions.
