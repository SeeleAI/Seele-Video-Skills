#!/usr/bin/env python3
"""Internal deterministic prompt compiler for K-POP One-Take Reveal.

Reads a brief JSON (2-4 members, exactly one reference image per member,
optional scene) and returns a compiled prompt package. The package is
fully deterministic: identical briefs always produce byte-identical output.

Stdlib only. No network, no randomness, no timestamps.

This module is not a prompt-only CLI. generate_video.py is the only product
entry point and must validate this package before invoking video generation.
"""

from __future__ import annotations

import json
import re

SKILL_NAME = "kpop-multi-character-one-take-video-generator"
TITLE = "K-POP One-Take Reveal"
DURATION_SECONDS = 8.0
ASPECT_RATIO = "16:9"
TAKE_POLICY = "single-uninterrupted-take"

REF_TOKEN_ANYWHERE = re.compile(r"\[image\d+\]")
REF_PATTERN = re.compile(r"^\[image(\d+)\]$")
MIN_MEMBERS = 2
MAX_MEMBERS = 4

# Exact, gapless, non-overlapping beat durations per member count.
# All values are dyadic decimals so float arithmetic stays exact.
# Layout per count: opening 1.0s, one solo reveal slot per member, finale 1.0s.
SOLO_SLOT_SECONDS = {2: 3.0, 3: 2.0, 4: 1.5}
OPENING_SECONDS = 1.0
FINALE_SECONDS = 1.0

CAMERA_PATH = (
    "one continuous slow push-in that begins wide on the full formation, "
    "glides in a single smooth arc across the line during the solo reveals, "
    "and settles into a locked medium-wide framing for the final group pose; "
    "the camera never stops, never cuts, and never leaves the scene"
)

NEGATIVE_CONSTRAINTS = [
    "no cuts, no cutaways, no jump cuts, no match cuts, no morph cuts",
    "no dissolves, fades, wipes, crossfades, or any transition effect",
    "no hidden edits, no seam passes, no whip-pan edit points, no reshoots stitched together",
    "no member swaps, no identity drift, no face or outfit changes between beats",
    "no extra people entering or leaving the frame",
    "no on-screen text, logos, watermarks, or UI overlays",
]


class PromptContractError(ValueError):
    """Raised when an internal prompt brief violates the fixed contract."""


def _fail(message: str) -> None:
    raise PromptContractError(message)


def _parse_ref_index(ref: str) -> int:
    match = REF_PATTERN.match(ref)
    if not match:
        _fail(f"invalid reference image token {ref!r}; expected [imageN]")
    return int(match.group(1))


def load_brief(raw: str) -> dict:
    try:
        brief = json.loads(raw)
    except json.JSONDecodeError as exc:
        _fail(f"brief is not valid JSON: {exc}")
    if not isinstance(brief, dict):
        _fail("brief must be a JSON object")

    members = brief.get("members")
    if not isinstance(members, list):
        _fail("brief.members must be a list")
    if not (MIN_MEMBERS <= len(members) <= MAX_MEMBERS):
        _fail(f"member count must be {MIN_MEMBERS}-{MAX_MEMBERS}, got {len(members)}")

    seen_names: set[str] = set()
    seen_refs: set[str] = set()
    expected_next = 1
    for i, member in enumerate(members):
        if not isinstance(member, dict):
            _fail(f"members[{i}] must be an object")
        name = member.get("name")
        ref = member.get("ref")
        if not isinstance(name, str) or not name.strip():
            _fail(f"members[{i}] is missing a non-empty 'name'")
        if not isinstance(ref, str) or not ref.strip():
            _fail(f"members[{i}] ({name}) is missing its reference image 'ref'")
        name = name.strip()
        ref = ref.strip()
        index = _parse_ref_index(ref)
        if name in seen_names:
            _fail(f"duplicate member name {name!r}")
        if ref in seen_refs:
            _fail(f"duplicate reference image {ref!r}; exactly one ref per member")
        if REF_PATTERN.match(name):
            _fail(f"member name {name!r} collides with reference token syntax")
        if index != expected_next:
            _fail(
                f"reference order mismatch: members[{i}] uses [image{index}] "
                f"but slot {expected_next} was expected; order members [image1]..[imageN]"
            )
        seen_names.add(name)
        seen_refs.add(ref)
        expected_next += 1
        member["name"] = name
        member["ref"] = ref

    scene = brief.get("scene")
    if scene is not None:
        if not isinstance(scene, str):
            _fail("brief.scene must be a string when provided")
        scene = scene.strip()
        if REF_TOKEN_ANYWHERE.search(scene):
            _fail("scene must not contain [imageN] reference tokens")
        brief["scene"] = scene or None

    return brief


def compile_package(brief: dict) -> dict:
    members = brief["members"]
    count = len(members)
    slot = SOLO_SLOT_SECONDS[count]
    scene = brief.get("scene") or "a dark stage with a single volumetric spotlight and haze"

    identity_map = [{"slot": i + 1, "name": m["name"], "ref": m["ref"]} for i, m in enumerate(members)]

    timeline: list[dict] = []
    start = 0.0

    timeline.append(
        {
            "beat": 0,
            "label": "opening-formation",
            "start": 0.0,
            "end": OPENING_SECONDS,
            "focus": None,
            "blocking": (
                "all members hold the opening group formation in a staggered line, frozen mid-pose, eyes down"
            ),
            "camera": "wide establishing framing; the continuous push-in begins",
            "handoff": "opens on the full group; the first solo member raises their eyeline into lens",
        }
    )
    start = OPENING_SECONDS

    for i, m in enumerate(members):
        end = start + slot
        prev_focus = "the group formation" if i == 0 else members[i - 1]["name"]
        timeline.append(
            {
                "beat": i + 1,
                "label": f"solo-reveal-{m['name']}",
                "start": start,
                "end": end,
                "focus": m["name"],
                "blocking": (
                    f"{m['name']} ({m['ref']}) steps one pace forward into the solo mark "
                    f"while the others hold the line half a pace back; "
                    f"{m['name']} hits a sharp point-move and locks eyes with the lens"
                ),
                "camera": (f"the arc glides laterally from {prev_focus} toward {m['name']} without breaking speed"),
                "handoff": (
                    f"as the camera passes, {m['name']}'s shoulder briefly occludes "
                    f"{prev_focus}, then clears to reveal the next mark"
                ),
            }
        )
        start = end

    all_names = ", ".join(m["name"] for m in members)
    timeline.append(
        {
            "beat": len(members) + 1,
            "label": "finale-group-lock",
            "start": start,
            "end": DURATION_SECONDS,
            "focus": "all",
            "blocking": (
                f"all members ({all_names}) snap back into the final formation and freeze "
                "in the ending pose, breathing visible, eyelines converging on the lens"
            ),
            "camera": "the push-in settles and holds locked until frame end; no pull-out, no fade",
            "handoff": (
                f"{members[-1]['name']} rejoins the line in one continuous step; "
                f"final formation contains exactly the {count} mapped members"
            ),
        }
    )

    continuity = {
        "handoffs": [
            "every beat hands focus to the next through lateral camera travel plus a "
            "brief shoulder occlusion, never through an edit"
        ],
        "occlusion": (
            "occlusions are momentary blocking overlaps inside the same take; they must "
            "never fully black out the frame or mask a cut"
        ),
        "eyelines": (
            "each solo member opens their eyeline to the lens at the start of their slot "
            "and releases it as the next member's slot begins; all eyelines converge on "
            "the lens in the finale"
        ),
    }

    package = {
        "skill": SKILL_NAME,
        "title": TITLE,
        "duration_seconds": DURATION_SECONDS,
        "aspect_ratio": ASPECT_RATIO,
        "take_policy": TAKE_POLICY,
        "member_count": count,
        "identity_map": identity_map,
        "scene": scene,
        "formation": {
            "opening": "staggered single line, solo marks one pace forward of the line",
            "finale": f"locked group formation containing exactly the {count} mapped members",
        },
        "camera_path": CAMERA_PATH,
        "timeline": timeline,
        "continuity": continuity,
        "negative_constraints": NEGATIVE_CONSTRAINTS,
        "prompt_text": "",
    }
    package["prompt_text"] = render_prompt_text(package)
    return package


def render_prompt_text(package: dict) -> str:
    lines: list[str] = []
    lines.append(
        f"{package['title']} — {package['duration_seconds']:.0f}s, {package['aspect_ratio']}, one uninterrupted take."
    )
    lines.append("")
    lines.append("Identity map:")
    for entry in package["identity_map"]:
        lines.append(f"- {entry['ref']} = {entry['name']} (slot {entry['slot']})")
    lines.append("")
    lines.append(f"Scene: {package['scene']}.")
    lines.append(f"Camera: {package['camera_path']}.")
    lines.append(f"Formation: {package['formation']['opening']}; finale: {package['formation']['finale']}.")
    lines.append("")
    lines.append("Beat timeline (8.0s total, gapless, non-overlapping):")
    for beat in package["timeline"]:
        focus = beat["focus"] if beat["focus"] else "group"
        lines.append(
            f"- {beat['start']:.2f}s-{beat['end']:.2f}s [{beat['label']}] focus={focus}: "
            f"{beat['blocking']} Camera: {beat['camera']} Handoff: {beat['handoff']}"
        )
    lines.append("")
    continuity = package["continuity"]
    lines.append(
        "Continuity: " + continuity["handoffs"][0] + " " + continuity["occlusion"] + " " + continuity["eyelines"]
    )
    lines.append("")
    lines.append("Negative constraints:")
    for item in package["negative_constraints"]:
        lines.append(f"- {item}")
    return "\n".join(lines)
