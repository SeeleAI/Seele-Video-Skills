#!/usr/bin/env python3
"""Internal validator for compiled K-POP One-Take Reveal prompt packages.

Validate packages produced by compile_prompt.py before generate_video.py
submits them to the production video executor.

Stdlib only. No network.
"""

from __future__ import annotations

import re

SKILL_NAME = "kpop-multi-character-one-take-video-generator"
TITLE = "K-POP One-Take Reveal"
DURATION_SECONDS = 8.0
ASPECT_RATIO = "16:9"
TAKE_POLICY = "single-uninterrupted-take"
MIN_MEMBERS = 2
MAX_MEMBERS = 4
EPSILON = 1e-9

REF_PATTERN = re.compile(r"^\[image(\d+)\]$")

# Vocabulary that implies an edit. Matches are rejected unless immediately
# negated (e.g. "no cuts", "without dissolves") inside the prompt text.
FORBIDDEN_TERMS = [
    "cut to",
    "cutaway",
    "jump cut",
    "match cut",
    "smash cut",
    "morph cut",
    "dissolve",
    "crossfade",
    "cross-fade",
    "fade to",
    "fade out",
    "fade in",
    "fade-out",
    "fade-in",
    "wipe",
    "transition",
    "montage",
    "splice",
    "hidden edit",
    "edit point",
    "whip pan",
    "whip-pan",
    "stitch",
    "recut",
    "re-cut",
]
NEGATION_PREFIXES = ("no ", "not ", "never ", "without ", "avoid ", "free of ", "zero ")

# "Film & CG" is a frontend category label only; it must never leak into a
# model-facing prompt or a prompt/profile option list.
FORBIDDEN_CATEGORY_TERMS = ["film & cg", "film and cg", "film&cg"]


class Violation:
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail

    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


def _approx_equal(a: float, b: float) -> bool:
    return abs(a - b) < EPSILON


def _validate_header(package: dict, errors: list[Violation]) -> None:
    if package.get("skill") != SKILL_NAME:
        errors.append(Violation("HEADER_MISMATCH", f"skill must be {SKILL_NAME!r}"))
    if package.get("title") != TITLE:
        errors.append(Violation("HEADER_MISMATCH", f"title must be {TITLE!r}"))
    if not _approx_equal(float(package.get("duration_seconds", -1)), DURATION_SECONDS):
        errors.append(Violation("TIMELINE_OUT_OF_BOUNDS", "duration_seconds must be exactly 8.0"))
    if package.get("aspect_ratio") != ASPECT_RATIO:
        errors.append(Violation("HEADER_MISMATCH", "aspect_ratio must be '16:9'"))
    if package.get("take_policy") != TAKE_POLICY:
        errors.append(Violation("HEADER_MISMATCH", f"take_policy must be {TAKE_POLICY!r}"))


def _validate_identity_map(package: dict, errors: list[Violation]) -> list[dict]:
    identity_map = package.get("identity_map")
    if not isinstance(identity_map, list) or not identity_map:
        errors.append(Violation("MISSING_REF", "identity_map is missing or empty"))
        return []

    if not (MIN_MEMBERS <= len(identity_map) <= MAX_MEMBERS):
        errors.append(Violation("COUNT_MISMATCH", f"identity_map must hold {MIN_MEMBERS}-{MAX_MEMBERS} members"))

    names: set[str] = set()
    refs: set[str] = set()
    for i, entry in enumerate(identity_map):
        name = entry.get("name")
        ref = entry.get("ref")
        slot = entry.get("slot")
        if not isinstance(ref, str) or not REF_PATTERN.match(ref):
            errors.append(Violation("MISSING_REF", f"identity_map[{i}] has a missing/invalid ref {ref!r}"))
            continue
        if ref in refs:
            errors.append(Violation("DUPLICATE_REF", f"duplicate reference image {ref!r}"))
        refs.add(ref)
        ref_index = int(REF_PATTERN.match(ref).group(1))
        if slot != i + 1 or ref_index != i + 1:
            errors.append(
                Violation(
                    "ORDER_MISMATCH",
                    f"identity_map[{i}]: slot={slot!r} ref={ref!r}; expected slot {i + 1} with [image{i + 1}]",
                )
            )
        if not isinstance(name, str) or not name.strip():
            errors.append(Violation("IDENTITY_COLLISION", f"identity_map[{i}] has a missing/empty name"))
        elif name in names:
            errors.append(Violation("IDENTITY_COLLISION", f"duplicate member name {name!r}"))
        elif REF_PATTERN.match(name):
            errors.append(Violation("IDENTITY_COLLISION", f"member name {name!r} collides with reference token syntax"))
        names.add(name)

    declared = package.get("member_count")
    if declared is not None and declared != len(identity_map):
        errors.append(
            Violation("COUNT_MISMATCH", f"member_count={declared!r} but identity_map has {len(identity_map)}")
        )
    return identity_map


def _validate_timeline(package: dict, identity_map: list[dict], errors: list[Violation]) -> None:
    timeline = package.get("timeline")
    if not isinstance(timeline, list) or not timeline:
        errors.append(Violation("TIMELINE_GAP", "timeline is missing or empty"))
        return

    member_names = {entry.get("name") for entry in identity_map}
    expected_beats = 1 + len(identity_map) + 1  # opening + one solo per member + finale
    if len(timeline) != expected_beats:
        errors.append(
            Violation(
                "COUNT_MISMATCH",
                f"timeline has {len(timeline)} beats; expected {expected_beats} "
                "(opening + one solo per member + finale)",
            )
        )

    if not _approx_equal(float(timeline[0].get("start", -1)), 0.0):
        errors.append(Violation("TIMELINE_OUT_OF_BOUNDS", "first beat must start at 0.0"))
    if not _approx_equal(float(timeline[-1].get("end", -1)), DURATION_SECONDS):
        errors.append(Violation("TIMELINE_OUT_OF_BOUNDS", "last beat must end at 8.0"))

    solo_counts: dict[str, int] = {name: 0 for name in member_names}
    previous_end = 0.0
    previous_focus: str | None = None

    for i, beat in enumerate(timeline):
        start = float(beat.get("start", -1))
        end = float(beat.get("end", -1))
        label = beat.get("label", f"beat-{i}")

        if start < -EPSILON or end > DURATION_SECONDS + EPSILON:
            errors.append(Violation("TIMELINE_OUT_OF_BOUNDS", f"{label}: [{start}, {end}] outside [0.0, 8.0]"))
        if end <= start:
            errors.append(Violation("TIMELINE_OVERLAP", f"{label}: non-positive duration [{start}, {end}]"))
        if i > 0:
            if start > previous_end + EPSILON:
                errors.append(Violation("TIMELINE_GAP", f"gap before {label}: {previous_end} -> {start}"))
            elif start < previous_end - EPSILON:
                errors.append(Violation("TIMELINE_OVERLAP", f"overlap at {label}: {previous_end} -> {start}"))

        focus = beat.get("focus")
        is_first = i == 0
        is_last = i == len(timeline) - 1
        if is_first:
            if focus is not None:
                errors.append(Violation("FORMATION_INCOMPLETE", "opening beat must focus the group (focus=null)"))
        elif is_last:
            if focus != "all":
                errors.append(Violation("FORMATION_INCOMPLETE", "finale beat must focus 'all' members"))
        else:
            if focus not in member_names:
                errors.append(Violation("IDENTITY_COLLISION", f"{label}: focus {focus!r} is not a mapped member"))
            else:
                solo_counts[focus] += 1
                if focus == previous_focus:
                    errors.append(Violation("HANDOFF_MISMATCH", f"{label}: consecutive beats focus {focus!r}"))

        # Handoff continuity: a solo beat's handoff must lead from the previous focus.
        handoff = str(beat.get("handoff", ""))
        if not is_first and isinstance(previous_focus, str) and previous_focus not in ("group", "all"):
            if previous_focus not in handoff:
                errors.append(
                    Violation(
                        "HANDOFF_MISMATCH",
                        f"{label}: handoff does not lead from previous focus {previous_focus!r}",
                    )
                )
        previous_end = end
        previous_focus = focus

    for name, count in solo_counts.items():
        if count != 1:
            errors.append(Violation("COUNT_MISMATCH", f"member {name!r} has {count} solo beats; expected exactly 1"))


def _validate_formation(package: dict, identity_map: list[dict], errors: list[Violation]) -> None:
    formation = package.get("formation")
    if not isinstance(formation, dict):
        errors.append(Violation("FORMATION_INCOMPLETE", "formation block is missing"))
        return
    finale = str(formation.get("finale", ""))
    count = len(identity_map)
    if str(count) not in finale:
        errors.append(
            Violation(
                "FORMATION_INCOMPLETE",
                f"formation.finale must lock exactly the {count} mapped members",
            )
        )
    if not str(formation.get("opening", "")).strip():
        errors.append(Violation("FORMATION_INCOMPLETE", "formation.opening is missing"))


def _scan_text(package: dict, errors: list[Violation]) -> None:
    prompt_text = str(package.get("prompt_text", ""))
    lowered = prompt_text.lower()
    for term in FORBIDDEN_CATEGORY_TERMS:
        if term in lowered:
            errors.append(
                Violation(
                    "CATEGORY_LEAK",
                    f"frontend category label {term!r} must never appear in a model-facing prompt",
                )
            )

    # A forbidden term is only a violation when it is asserted. Negation is
    # scoped per line so comma-separated negative-constraint lists like
    # "no dissolves, fades, wipes, or any transition effect" stay valid.
    for line in lowered.splitlines():
        for term in FORBIDDEN_TERMS:
            start = 0
            while True:
                index = line.find(term, start)
                if index == -1:
                    break
                if not any(prefix in line[:index] for prefix in NEGATION_PREFIXES):
                    errors.append(
                        Violation(
                            "FORBIDDEN_VOCABULARY",
                            f"prompt_text asserts cut/transition vocabulary {term!r}: {line.strip()!r}",
                        )
                    )
                start = index + len(term)


def validate_package(package: dict) -> list[Violation]:
    errors: list[Violation] = []
    _validate_header(package, errors)
    identity_map = _validate_identity_map(package, errors)
    _validate_timeline(package, identity_map, errors)
    _validate_formation(package, identity_map, errors)
    _scan_text(package, errors)
    return errors
