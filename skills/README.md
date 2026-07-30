# Seele Video Skills

This directory contains the public Film & CG skill collection. Each directory includes an executable or operational `SKILL.md`; canonical packages also retain safe scripts, references, templates, and evals where available.

| Workspace Card | Public skill directory | Source status |
| --- | --- | --- |
| Greybox Previz | [`greybox-cg-v2v`](greybox-cg-v2v/) | Canonical skill, public-runtime sanitized |
| Comic Storyboard | [`script-to-comic-storyboard`](script-to-comic-storyboard/) | Canonical skill |
| Depth-Guided Motion Transfer | [`convert-video-to-depth-spatial`](convert-video-to-depth-spatial/) | Canonical depth skill, public-runtime sanitized |
| Promo Video | [`promo-video-generator`](promo-video-generator/) | Canonical skill |
| Game Trailer | [`game-trailer`](game-trailer/) | Public recipe derived from the Workspace Card; no dedicated canonical production skill exists yet |
| Brand Story Video | [`brand-story-video`](brand-story-video/) | Canonical skill |
| Authentic Camcorder Vlog | [`authentic-camcorder-vlog-video-prompts`](authentic-camcorder-vlog-video-prompts/) | Canonical skill |
| Weekly Outfit Transitions | [`weekly-outfit-transition-video-prompts`](weekly-outfit-transition-video-prompts/) | Canonical skill |
| K-POP One-Take Reveal | [`kpop-multi-character-one-take-video-generator`](kpop-multi-character-one-take-video-generator/) | Canonical skill, public-runtime sanitized |
| Real Estate Video | [`real-estate-video`](real-estate-video/) | Canonical skill |
| AI Video Generator | [`ai-video-generator`](ai-video-generator/) | Public general recipe derived from the Workspace Card; no dedicated canonical production skill exists yet |
| Motion Generation | [`motion-generation`](motion-generation/) | Canonical skill, public-runtime sanitized |

## Requirements and verification

- Python **3.10+** for bundled Python executors; storyboard image processing also requires Pillow.
- Greybox recording requires a Chromium-compatible browser and FFmpeg as described in its references.
- Generation executors require the model/gateway adapters and environment variables documented in their own `SKILL.md` and references.
- The published tree is checked for valid frontmatter, Python/JavaScript syntax, JSON validity, local case-image links, oversized files, credentials, private hosts, and machine-specific paths.

## Public-runtime policy

Private endpoints, shared tokens, machine-specific absolute paths, bytecode caches, and credentials are excluded. Runtime-integrated skills use explicit environment variables or adapter boundaries; configure them through your own secret manager. Public packages must never assume access to Seele production infrastructure.
