# Generation and Review Contract

## Prompt handoff

Create one English prompt per approved shot. Include only supported, observable direction:

```text
[shot duration], [framing and camera movement]. [subject with identity-safe description] [performs action] in [specific environment]. [lighting and palette]. [mood and pacing]. Preserve [continuity anchors]. No [undesired artifacts or claims]. [aspect ratio], [delivery intent].
```

Do not ask a model to depict a real person without authorization. Do not describe generated scenes as documentary evidence. Use supplied brand assets only with documented rights.

## Receipt fields

For every provider attempt, capture `shot_id`, provider, model/version, submitted prompt, negative prompt or exclusions, parameters, source asset references, output path/URL, timestamp, status, retry reason, and rights/consent notes. Never record credentials or tokens.

## Semantic review

Approve only when all answers are yes:

- Does the cut preserve the chosen audience, tension, proof, and CTA?
- Is each claim supported and each person/asset cleared for its use?
- Are generated/recreated scenes labeled accurately where disclosure is required?
- Do identity, wardrobe, geography, product details, and screen direction stay continuous?
- Is dialogue understandable, music licensed, and captions/transcript accurate?
- Does the final brand appearance serve the story rather than interrupt it?
