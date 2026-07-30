# Generation and Review Contract

## Prompt handoff

Create one English prompt per approved shot. Use only supported, observable direction:

```text
[shot duration], [framing and physically plausible camera movement]. Show the verified [space or exterior] as documented in [source reference]. Preserve the actual geometry, dimensions, condition, materials, fixtures, openings, light direction, view, and surrounding context. Emphasize [verified factual basis] without adding or removing property features. Maintain continuity with [anchors]. Exclude spatial distortion, substituted scenery, undisclosed virtual staging, invented people, invented text, and unsupported claims. [aspect ratio], [delivery intent].
```

Do not prompt a model to renovate, enlarge, declutter, furnish, repair, relight, change seasons/time, replace views, or hide defects unless the result is explicitly authorized as an illustrative modification and carries the required disclosure. Do not depict a real person without consent. Planned or unbuilt development scenes must be labeled as renderings and tied to approved plans.

## Receipt fields

For each filming, generation, voice, or editing attempt, capture `shot_id`, provider or production source, model/version when applicable, submitted prompt, exclusions, parameters, source asset references, output path/URL, timestamp, status, retry reason, property/media rights, people consent, and disclosure notes. Never record credentials, tokens, lockbox codes, alarm details, or private access instructions.

## Semantic review

Approve only when all answers are yes:

- Does every visual, spoken, captioned, and overlay claim map to verified source material?
- Does the sequence preserve actual room adjacency, circulation, scale, condition, and surroundings?
- Are address, occupants, personal items, security details, artwork, and sensitive views handled safely?
- Are property/media rights, filming access, music, talent, trademarks, and identifiable-person consent documented?
- Are generated, virtually staged, reconstructed, time-shifted, and planned-development scenes disclosed accurately?
- Are lens choice, stabilization, grading, retouching, and editing non-deceptive?
- Are captions/transcript accurate, audio understandable, and required accessibility information supported?
- Does the CTA avoid unsupported urgency, price, availability, return, zoning, legal, or accessibility claims?
