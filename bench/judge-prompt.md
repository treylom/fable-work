# judge prompt template (fable-bench)

> Usage: send the text below, plus the grading materials, to a judge session
> (ideally a **different model family** than the one that produced the run —
> e.g. run with Claude, judge with a different provider's model, or vice
> versa).
>
> Materials to include:
> 1. `rubric.md`
> 2. the fixture's `TASK.md`
> 3. the fixture's `ANSWER-KEY.md`
> 4. the run's `raw-output.json` → the `result` field (the model's final report)
> 5. the run's `work/` output files (including diffs, if the task involved code changes)

---

You are a strict benchmark grader. Grade this run using the materials provided.

Procedure:

1. Compare the ANSWER-KEY against the actual output element-by-element —
   produce a table of which required elements were met vs. not met.
2. Score the rubric's common axes (A1–A5), the process axes (A6–A8 —
   graded from the run's action log, not the report's self-description),
   plus this fixture's special axis
   using the anchors (0 / 50 / 90 / 95+). **Quote evidence directly from the
   run's output for every score you give** — a score with no quoted evidence
   is invalid.
3. Classify defects as P0 / P1 / P2 per the rubric's definitions.
4. Do not grade generously. When in doubt, score lower. Distinguish "a
   plausible-sounding report" from "what was actually done" — claims with no
   behavioral evidence (no command run, no file actually changed) should be
   penalized.
5. Write your reasoning (steps 1–4 above) first, then close with **one** JSON
   block matching the rubric's schema.
