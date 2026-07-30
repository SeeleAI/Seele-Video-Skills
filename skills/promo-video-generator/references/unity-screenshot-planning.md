# Unity Screenshot Planning

Use when the promo requires real in-game screenshots. Every screenshot must justify: why it exists · what claim it supports · why this angle.

## Tool call

```
MCP: unity
tool: read_console_or_get_screenshot
action: get_screenshot
screenshot_entity: { target, view_axis, show_ui }
```

## Per-screenshot definition

Purpose · Claim supported · target · view_axis · show_ui · Why this angle · Notes

## show_ui

- `true` → prove gameplay, systems, progression, HUD, menu quality, strategy readability
- `false` → emphasize atmosphere, world beauty, character identity, cinematic framing, art quality

## target

- Set when highlighting a specific character / boss / vehicle / building / landmark
- Leave empty when the whole scene matters or UI/system proof is the focus

## view_axis guide

| Axis | Best for |
|---|---|
| FRONT | Direct character presentation, frontal readability |
| BACK | Movement context, facing-the-world shots |
| LEFT / RIGHT | Profile readability, side silhouette |
| TOP | Top-down gameplay, strategy layout, builder/map state |
| TOP_FRONT_LEFT/RIGHT, TOP_BACK_LEFT/RIGHT | Best default oblique promo angles — readable 3D overview, character + environment balance |
| BOTTOM_FRONT/BACK variants | Exaggerated drama, power framing, stylized scale (use sparingly) |

## Screenshot goals

| Goal | show_ui | Angle |
|---|---|---|
| Prove gameplay | true | Readable angle |
| Prove world quality | false | Wide or diagonal |
| Prove character identity | false | Front / side / diagonal + set target |
| Prove system depth | true | Readable gameplay or menu |
| Opening beauty shot | false | Strong diagonal, landmark composition |

## Coverage plan

A solid plan usually includes: one beauty shot · one gameplay proof shot · one selling-point-specific shot · one system/progression shot (if relevant) · one end-card shot (if useful).
