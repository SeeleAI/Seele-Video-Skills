---
name: brand-story-video
description: Create production-ready brand story video plans, shot lists, and generation prompts from a brand brief. Use for brand films, company or founder origin stories, mission and culture videos, customer-impact stories, brand anthems, anniversary films, and narrative social videos. Produce structured preproduction artifacts before generating or editing video.
---

# Brand Story Video

Create an evidence-led story plan before generating footage. The audience, their tension, and the intended change determine the film; the product is supporting evidence, not the hero.

## Workflow

1. Gather a brief: brand, audience, objective, offer, proof, desired action, duration, aspect ratio, tone, constraints, and brand assets. Do not invent claims, people, permissions, testimonials, or statistics.
2. Select one story architecture and hook. Read `references/narrative-frameworks.md` for options and selection criteria.
3. Write a factual brief JSON and build the production package:

```bash
python3 {{env_base_path}}/skills/brand-story-video/scripts/build_brand_story_package.py --brief /path/to/brief.json --out /path/to/output-directory
```

The script creates the canonical brief, timed narrative, shot list, generation-receipt template, mechanical QA checklist, and checksummed manifest. It makes no network or provider calls, rejects unsafe/missing input, and refuses a non-empty output directory.
4. Review `timeline.json` and `shot-list.json`. For each shot, confirm narrative purpose, claim support, continuity, consent/rights, and accessibility. Revise the source brief and rerun rather than editing derived files by hand.
5. Read `references/generation-contract.md` before using any image/video/audio provider. Translate each approved shot into a provider-specific prompt while preserving subject identity, action, timing, aspect ratio, exclusions, and source evidence. Keep every model-facing prompt in English.
6. Record each external generation in `generation-receipts.json`; record factual, visual, audio, caption, and brand review in `qa.json`. Do not publish, license, or represent generated material as real footage without explicit authorization.

## Required brief decisions

- **Message:** one audience-relevant belief; one supported proof point; one natural CTA.
- **Narrative:** customer is normally the protagonist. Use a founder or brand only when their lived decision is the story.
- **Authenticity:** distinguish verified material, recreated scenes, and generated illustrative visuals.
- **Format:** 15–30 seconds for a social cut; 45–90 seconds for a short brand film unless a delivery spec says otherwise.

## Quality gates

Stop and resolve the issue before generation when any of these is missing: claim evidence, rights/consent status, target audience, duration, CTA, or prohibited-content constraints. Avoid invented metrics, medical/financial outcomes, deceptive before/after claims, synthetic testimonials presented as real, and logo-first endings.

Before delivery, complete the mechanical checks in `qa.json` and the semantic checks in `references/generation-contract.md`. Ensure captions/transcript, music and talent rights, platform export settings, and brand approval are documented.

## Output handoff

Deliver the generated package plus provider outputs and receipts. The package is a planning and audit record, not a rendered video. Keep source assets and provider outputs outside the skill directory; use relative paths in receipts when practical.


## Seele Workspace case preview

![Brand Story Video case cover](../../assets/cases/brand-story-video.jpg)

[Open Film & CG in Seele Workspace](https://www.seeles.ai/workspace?category=film-cg)
