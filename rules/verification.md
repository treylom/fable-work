# Rule: verification before completion

Trigger: you are about to say "done", "fixed", "verified", "passing" — or to end a turn after changing code/config.

- **Evidence before claims.** Run the narrowest command that would prove the claim (a test, a scan, a diff, a re-read) and look at its output *before* saying it. A completion claim with no fresh evidence is a guess. (The stop-gate in [`hooks/`](../hooks/) enforces exactly this, mechanically.)
- **State the grade of your verification.** "Verified" hides a ladder: ① deterministic (script/assert) → ② scenario replay (end-to-end) → ③ independent evaluator → ④ human review. Say which rung actually ran; don't let ① quietly stand in for ③.
- **3-tier the inputs when it matters.** ① nominal (happy path) ② deep (larger windows, all switches, deeper trees) ③ boundary (empty input, off-by-one, skip conditions). Small changes may genuinely only need ① — then say so explicitly.
- **Verify the verifier.** When a success message and your own check disagree ("registered." vs `found: False`), don't pick a side — build a third, stricter measurement (parse the structure instead of substring-matching text). Mined from a live session where the *checker* had the bug (matching an unescaped string against escaped JSON) and the action had been fine all along.
- **Attribute before you learn from a failure.** In mixed-model or multi-worker sessions, pin a failure to the component that actually produced it (check the metadata, not the narrative) before encoding any lesson. We once nearly filed one model's tool-call corruption under a different model's profile — the transcript's per-turn metadata settled it in minutes.
