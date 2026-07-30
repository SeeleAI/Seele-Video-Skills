---
name: real-estate-video
description: Create production-ready property video plans, truthful shot lists, and generation handoff prompts from verified listing or development facts. Use for listing tours, room-by-room walkthroughs, architecture and interior showcases, development or amenity films, and permission-cleared agent-led or lifestyle property videos. Produce structured preproduction artifacts before filming, generating, or editing video.
---

# Real Estate Video

Plan the property as it exists. Use light, movement, spatial sequence, and verified details to communicate experience without changing, enlarging, furnishing, or embellishing reality deceptively.

## Workflow

1. Gather the property brief: identifier, video type, audience, objective, verified facts, ordered spaces, duration, aspect ratio, tone, CTA, rights, disclosures, and constraints. Do not invent dimensions, floorplans, views, amenities, materials, prices, availability, legal status, accessibility, people, or neighborhood claims.
2. Select an honest spatial arc and camera treatment. Read `references/property-story-patterns.md` for structures and shot selection.
3. Write the brief as JSON and build the local planning package:

```bash
python3 {{env_base_path}}/skills/real-estate-video/scripts/build_real_estate_video_package.py --brief /path/to/brief.json --out /path/to/output-directory
```

The script creates a canonical brief, timed outline, shot list, generation-receipt template, QA checklist, and checksummed manifest. It makes no network or provider calls, rejects incomplete or unsafe input, and refuses a non-empty output directory.
4. Review `timeline.json` and `shot-list.json`. Confirm every factual basis against source records; confirm the visual path matches the real layout and filming access. Correct the source brief and rerun instead of hand-editing derived files.
5. Read `references/generation-and-review-contract.md` before any filming, image/video generation, voice, or editing handoff. Keep all model-facing prompt templates in English. Preserve real geometry, finishes, condition, light, views, boundaries, and surrounding context.
6. Record each provider or production attempt in `generation-receipts.json`. Complete factual, spatial, visual, audio, disclosure, consent, and accessibility review in `qa.json`. Never claim the package is a rendered video.

## Required decisions

- **Truth:** each visible or spoken claim maps to a verified fact or verified space detail.
- **Rights:** property/media rights and filming access are confirmed; identifiable people require consent.
- **Disclosure:** generated, virtually staged, reconstructed, time-shifted, or otherwise illustrative scenes are labeled where relevant.
- **Spatial clarity:** orient the viewer, follow real adjacency, and avoid lens or edit choices that misrepresent size or condition.
- **Format:** use 15–45 seconds for a short social cut and 45–180 seconds for a listing or architecture film unless delivery requirements specify otherwise.

## Quality gates

Stop before filming or generation if verified facts, ordered spaces, property/media rights, filming access, duration, CTA, or required disclosure are missing. Agent-led and lifestyle videos also require people consent. Do not create deceptive renovations, substitute views, hidden defects, imaginary furnishings presented as real, fake neighborhood proximity, discriminatory audience targeting, Fair Housing violations, or unsupported investment language.

Before delivery, complete the mechanical checks in `qa.json` and semantic checks in `references/generation-and-review-contract.md`. Confirm captions/transcript, music and talent rights, address/privacy treatment, platform requirements, and stakeholder approval.

## Output handoff

Deliver the planning package with authorized source assets, production/provider outputs, receipts, and approvals. Keep credentials out of receipts and source media outside the skill directory. The package is a preproduction and audit record, not proof that footage was captured or generated.


## Seele Workspace case preview

![Real Estate Video case cover](../../assets/cases/real-estate-video.jpg)

[Open Film & CG in Seele Workspace](https://www.seeles.ai/workspace?category=film-cg)
