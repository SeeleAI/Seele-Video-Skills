# Production contract

## Inputs

Accept either:

- a screenplay targeting 60–90 seconds; or
- a story description/idea that can be adapted into a concise 60–90 second screenplay.

If neither exists, ask for one. Preserve supplied screenplay facts. For a story description, use a lightweight LLM drafting pass: simple scene headings, visible action, essential dialogue/audio, and a clear ending. Fill noncritical gaps only and label them as assumptions. Ask only when missing or conflicting critical information prevents a coherent adaptation. Optional visual references must have documented rights.

## Required planning artifacts

1. **Source trace**: source type, verbatim input summary, locked facts, explicitly marked assumptions, the supplied or drafted screenplay, and beat-to-shot ranges.
2. **Story Bible**: stable IDs and visual anchors for characters, locations, wardrobe, and props.
3. **Continuity ledger**: per-shot start/end state, screen direction, held hand, prop state, and 180-degree axis.
4. **Shot list**: exactly 18 records with `shot_id`, `duration_seconds`, visible action, framing, camera, dialogue/audio, and continuity fields.
5. **Three sheet prompts**: six ordered panels each; repeat fixed anchors in every prompt.

Use seconds as the time base. Sum `duration_seconds`; accept only 60–90 inclusive. Treat concurrent action/dialogue by critical-path duration, not blind addition.

## Sheet prompt contract

For each range (`01–06`, `07–12`, `13–18`) state:

- `3 columns × 2 rows`, left-to-right then top-to-bottom.
- Black ink/graphite grayscale only; no color.
- One panel per mapped shot; no inset panels, merged cells, captions, speech balloons, or generated shot numbers.
- Repeat exact character face/hair/build, wardrobe, damage/wetness, and prop anchors.
- State each prop's owner, state, and anatomical hand.
- State screen direction and the established 180-degree axis; name any deliberate axis reset.
- Describe one dominant visible action and one dominant framing per panel.

Generate without numbers, then add `01`–`18` locally. This prevents model text errors from becoming the numbering source of truth.

## QA layers

### Deterministic

- File decode, count, size, ratio, grayscale channels.
- 3×2 separator geometry and six local number-label patches.
- Shot IDs, uniqueness, order, duration, and sheet mapping.
- SHA-256 manifest and ZIP contents.

### Visual/manual

For every shot record `pass`, `warn`, or `fail` plus notes for:

- shot-to-panel semantic mapping;
- character identity;
- wardrobe and state;
- prop presence/state;
- anatomical left/right hand;
- screen direction and 180-degree axis.

Mechanical QA cannot infer semantic continuity. A `warn` remains visible in the final QA; a `fail` blocks delivery until repaired or explicitly accepted by the user. Delivery QA must also confirm that `source-trace.md` records input → supplied/draft screenplay → shot ranges; it must not imply that assumptions were user-supplied facts.

## Attribution

This workflow abstracts general production interfaces and QA principles from an MIT-licensed storyboard workflow. It does not bundle or copy that project's implementation. License verified: MIT, copyright 2026 zyz254009-crypto.
