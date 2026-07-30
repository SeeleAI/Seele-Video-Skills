---
name: "promo-video-generator"
description: Generate marketing, store-preview, or ad-style promo videos for games or interactive products.
---

## What it is

This skill turns product inputs into a production-ready promo video package and then executes downstream video generation.

## Use for

Use it for teasers, launch trailers, gameplay trailers, store videos, and social ad videos that need both planning and generated output.

## Attention

Do not stop at planning when the user asked for a video deliverable. Once the storyboard is production-ready, the downstream video generation call is mandatory.

# Promo Video Generator

Turn product inputs into a usable promo-video production package — explicit enough that video generation can proceed without further clarification — then execute video generation.

**Must call `ai-model-calling` when production-ready.** Do not stop at storyboard or asset-plan output if the request is to produce video.

## Workflow

1. **Parse** — promo type, platform, duration, ratio, audience, tone, launch stage, goal.
2. **Normalize** — read `references/input-normalization.md`.
3. **Define message** — read `references/messaging-framework.md` → hook, core promise, selling points, proof points, CTA.
4. **Extract visual signals** — if URLs/images provided, read `references/visual-extraction.md`.
5. **Plan Unity screenshots** — if real gameplay proof needed, read `references/unity-screenshot-planning.md`.
6. **Choose shot structure** — read `references/shot-structure.md`.
7. **Build storyboard** — read `references/storyboard-template.md`.
8. **Build asset plan** — read `references/asset-plan-template.md`.
9. **Select CTA** — read `references/cta-patterns.md`.
10. **Build generation payload** — for each segment to generate, resolve prompt, aspect_ratio, optional start-frame image, and model choice.
11. **Call video generation** — load `ai-model-calling` and execute generation in the same request flow. Do not hand off to an unspecified caller.
12. **Check output** — read `references/output-rules.md`; label all facts / findings / assumptions / missing assets / questions.

## Modes

| Mode | Use when | Output |
|---|---|---|
| Brief | Only strategy and structure needed | Goal, audience, hook, value prop, selling points, structure, questions |
| Storyboard | Usable storyboard needed | Brief + shot structure + storyboard + CTA + asset plan |
| Capture-planning | Unity screenshot collection needed | Screenshot plan with target / view_axis / show_ui per shot |
| Production-handoff | Full package is complete enough to execute video generation immediately | Brief + storyboard with gen specs + asset plan + screenshot plan + mandatory `ai-model-calling` call |

## Clarification rules

Ask only when the answer materially changes the output. Priority unknowns:
- target platform · duration · aspect ratio · target audience · main promo goal
- whether gameplay proof matters · whether Unity screenshots are available

## Tool usage

### Unity screenshots
```
MCP: unity
tool: read_console_or_get_screenshot
action: get_screenshot
screenshot_entity: { target, view_axis, show_ui }
```
Use only when real gameplay proof is tied to a specific storyboard shot. Never request screenshots without a storyboard purpose.

### Text / URL inputs → extract positioning, feature language, tone, official terminology
### Image URLs → extract visual tone, framing style, mood, UI visibility preference


## Seele Workspace case preview

![Promo Video case cover](../../assets/cases/promo-video-generator.jpg)

[Open Film & CG in Seele Workspace](https://www.seeles.ai/workspace?category=film-cg)
