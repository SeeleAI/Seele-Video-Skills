---
name: script-to-comic-storyboard
description: "Convert a screenplay or story description into a production-ready 18-shot black-and-white comic storyboard: lightweight 60–90 second screenplay development when needed, Story Bible, continuity ledger, timed shot list, three 3×2 sheet prompts, GPT Image generation handoff, local numbering/normalization, deterministic QA, manifest, and ZIP delivery. Use for 故事或剧本转漫画分镜、comic storyboard、18镜故事板、shot-list-to-storyboard, or continuity/axis/handedness QA of storyboard sheets."
---

# Script to Comic Storyboard

Compile a supplied screenplay faithfully, or develop a concise screenplay from a story description, into exactly 18 readable shots.

## Workflow

1. Classify the source:
   - **Screenplay supplied:** preserve its facts. Do not rewrite plot facts without explicit authorization.
   - **Story description supplied:** draft a concise 60–90 second screenplay with simple scene headings, visible action, essential dialogue/audio, and a clear ending. Fill only noncritical gaps, list each addition under `Assumptions`, and do not add unnecessary subplots or characters.
   - **Neither supplied:** ask the user to paste a screenplay or describe the story.
   Ask a follow-up only when a critical item is absent or conflicting enough to prevent a coherent 60–90 second adaptation; otherwise proceed with marked assumptions.
2. Read [production-contract.md](references/production-contract.md). Freeze source facts, assumptions, and the input → draft screenplay → shot mapping using [templates.md](references/templates.md). Build the Story Bible and continuity ledger.
3. Produce exactly 18 unique shots numbered `01`–`18`. Validate total duration before image generation.
4. Compile three prompts for shots `01–06`, `07–12`, and `13–18`. Each prompt must request one black-and-white 3-column × 2-row comic sheet and preserve the same character, wardrobe, prop, handedness, screen-direction, and 180-degree-axis anchors.
5. Present the prepared prompts, model, and estimated paid calls. Obtain explicit approval immediately before any paid generation.
6. After approval only, call the shared image executor with `gpt-image-2` and no fallback. Never duplicate its API implementation or silently switch models. See [image-call-contract.md](references/image-call-contract.md).
7. Normalize, number, validate, and package locally:

```powershell
uv run python {{env_base_path}}/skills/script-to-comic-storyboard/scripts/process_storyboard.py `
  --sheet sheet-1.png --sheet sheet-2.png --sheet sheet-3.png `
  --shot-list shot-list.json --story-bible story-bible.md `
  --continuity-ledger continuity-ledger.md --prompts prompts.md `
  --source-trace source-trace.md --output-dir storyboard-delivery
```

8. Review deterministic QA plus visual continuity QA. A mechanical pass does not erase a character, wardrobe, prop, hand, mapping, or axis defect. Retry only the affected sheet, then rerun the script.
9. Deliver three numbered 16:9 sheets, Story Bible, continuity ledger, shot list, prompts, `source-trace.md` (input → screenplay → shots), `manifest.json`, `qa.json`, `qa.md`, and the ZIP.

## Hard gates

- Exactly 18 unique shot IDs, continuous `01`–`18`.
- Total edit duration: 60–90 seconds inclusive.
- Exactly three sheets; each maps to six shots in order.
- Final sheets: 1920×1080, grayscale, 3×2 layout, visible local labels.
- Log character identity, wardrobe, props, left/right hands, screen direction, and 180-degree axis per shot.
- Record source facts, marked assumptions, the screenplay used, and its beat-to-shot mapping in `source-trace.md`.
- Stop on failed mechanical QA, missing paid-call approval, API/model mismatch, or severe shot-to-panel mismatch.
- Keep known visual defects explicit in QA; never claim they passed because dimensions passed.


## Seele Workspace case preview

![Comic Storyboard case cover](../../assets/cases/script-to-comic-storyboard.webp)

[Open Film & CG in Seele Workspace](https://www.seeles.ai/workspace?category=film-cg)
