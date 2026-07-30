---
name: ai-video-generator
description: Turn a concise creative brief and optional reference media into a model-ready video generation plan, validated request, and reviewed output. Use for general text-to-video or image-to-video requests that do not require a more specific production skill.
---

# AI Video Generator

Use this as the general fallback for video generation. Prefer a domain skill when the request is specifically a storyboard, greybox/V2V shot, vlog, brand film, property video, trailer, outfit transition, motion transfer, or K-pop one-take.

## Inputs

- Subject and action
- Environment and time of day
- Camera framing and movement
- Duration, aspect ratio, and delivery resolution
- Optional reference image/video with usage rights
- Style, lighting, audio intent, and exclusions

## Workflow

1. Normalize the brief without inventing identity, rights, brand, or factual claims.
2. Resolve contradictions between motion, camera, duration, and composition.
3. Write one primary prompt and a short negative/exclusion list.
4. Record provider/model, parameters, source references, request ID, status, and output location in a secret-free receipt.
5. Review duration, dimensions, identity/reference adherence, camera continuity, anatomy, temporal artifacts, text/logos, audio, and safety.
6. Return the generated media plus receipt and QA; a prompt alone is not completion when the user requested a video.

## Output contract

Return `video`, `generation-receipt.json`, and `qa.json`. If generation cannot run, return a clear blocker and preserve the validated request without claiming completion.

## Guardrails

- Require authorization for real-person likenesses and private media.
- Do not infer rights from file possession.
- Never expose credentials, private endpoints, or raw authorization headers.

## Seele Workspace case preview

![AI Video Generator case cover](../../assets/cases/video-generation.jpg)

[Open Film & CG in Seele Workspace](https://www.seeles.ai/workspace?category=film-cg)
