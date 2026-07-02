# Rules INDEX — situation router (always-loaded)

> The only part of the rule layer that stays in context permanently. Before acting, scan the trigger column; when a row matches, read that rule file and apply it. Rule bodies live in the files, not here.

| When you are about to… | read | one-line gist |
|---|---|---|
| claim work is done / verified / passing | [verification.md](verification.md) | evidence before claims; state the grade; verify the verifier |
| hand work to a sub-agent / worker / other bot | [delegation.md](delegation.md) | complete HOW up front; check capacity; ack ≠ execution |
| edit code or config | *(write your own — e.g. blast-radius check before, 3-step verify after)* | |
| write to shared storage / publish externally | *(write your own — e.g. independent review gate before anything public)* | |
| assert something "doesn't exist / is broken" | *(write your own — e.g. widen the search before concluding absence)* | |

Conflict priority, when a rule and an instruction disagree: **explicit user instruction > rule file > default behavior.**
