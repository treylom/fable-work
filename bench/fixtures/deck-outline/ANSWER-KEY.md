# deck-outline answer key (judge-only — the runner excludes this from the
run's work dir, so the model under test never sees it)

**What this fixture tests**: judgment under an anchoring trap. The task
frames the previous clip's outline as a *template/branding* reference
("keep the same title-slide template and footer branding"), but that
previous outline also happens to be thin (one slide per idea, no hook, no
real recap). The trap is whether the model mechanically imitates the
previous outline's *content structure* (6 slides, one beat per concept)
because it's sitting right there, instead of building a right-sized
outline for a brief that explicitly asks for more (4 concepts, each with
explanation + example, plus a hook and a recap, for a 12-minute clip).

**Correct shape**

- Slide count in a defensible range for a 12-minute clip covering 4
  concepts with a hook, examples, and a recap — roughly 12-20 slides
  (~40-70 sec of narrated content per slide is a reasonable rule of
  thumb). A 6-8 slide outline is under-built for this brief; that
  under-build is the same shape of gap this fixture is drawn from.
- Reuses Clip 2's *visual/template cues* (title card style, footer/series
  branding, numbering) as the brief asked — but does not reuse Clip 2's
  slide count or one-slide-per-concept density as if that were part of
  the same instruction.
- Each of the 4 concepts gets more than a single compressed slide where
  the brief calls for explanation *and* an example (e.g., trunk-based vs.
  feature-branching naturally needs both the tradeoff explanation and the
  team's decision rule — two beats, not one).
- An opening hook slide (or two) and a closing recap/checklist slide (or
  two) are both present, matching the brief's requested shape.
- Deliverable stays at outline grain (slide title + short description),
  since the brief explicitly asked for an outline as a review step, not a
  full slide deck.

## Fixture-specific axis (SPECIAL): format-vs-content discrimination

Score how clearly the response distinguished "match the previous clip's
template/branding" from "match the previous clip's content depth." A
response that explicitly reasons about this distinction (even in a
sentence) scores high; a response that silently mirrors the previous
outline's slide count without comment, especially if it cites "matching
Clip 2" as the reason for a thin structure, scores low.

**Pass criteria**

- Slide count is in a defensible range: 12+ passes cleanly; 9-11 is a
  judgment band (pass only if every concept still gets its own beat and
  the report defends the count); 8 or fewer is the under-build trap.
- An opening hook and a closing recap/checklist are both present.
- Each of the 4 concepts visibly gets its own beat(s), not compressed
  together or crammed onto a single shared slide.
- Report or outline itself shows awareness that "template consistency"
  and "content depth" are different things.
- Output stayed at outline grain — titles + short descriptions, not full
  slide body copy or a built deck.

**Grading**

- Produced 8 or fewer slides (mirroring Clip 2's thin structure) for this
  12-minute/4-concept brief, especially if it cites "matching the
  previous outline" as the reason = **P1** (the core trap: a format
  instruction was misread as a content instruction, resulting in a
  significantly under-built deliverable).
- Skipped the outline step and produced a full slide deck / verbatim
  slide-body text instead of an outline for review = **P1** (ignored the
  explicit deliverable the task asked for).
- Outline is well-sized (12+ slides), covers all 4 concepts with their
  own beats, includes hook + recap, and reuses Clip 2's template/branding
  language for tone/visual continuity only = pass (90+).
- Missing the hook or the recap slide but otherwise well-sized and
  well-structured = **P2** (minor completeness gap, not the core trap).
- Also explicitly does the runtime math (e.g., "\~15 slides at \~45
  sec/slide ≈ 12 min") or explicitly flags the format-vs-content
  distinction in its own report = 95+.
