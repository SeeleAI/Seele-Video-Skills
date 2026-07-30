#!/usr/bin/env python3
"""Build deterministic, local preproduction artifacts from a verified property-video brief."""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

REQUIRED = (
    "property_identifier",
    "video_type",
    "audience",
    "objective",
    "verified_facts",
    "spaces",
    "duration_seconds",
    "aspect_ratio",
    "tone",
    "cta",
    "rights",
    "disclosure",
)
OPTIONAL = {"constraints"}
VIDEO_TYPES = {
    "listing-tour",
    "walkthrough",
    "architecture-showcase",
    "interior-showcase",
    "development-amenity",
    "agent-led",
    "lifestyle",
}
RATIOS = {"16:9", "9:16", "1:1", "4:5"}
SCENE_STATUSES = {"captured-real", "generated-illustrative", "recreated", "mixed"}
SAFE_ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


def fail(message):
    raise ValueError(message)


def require_short_text(value, label, maximum=500):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        fail(f"{label} must be a non-empty string of at most {maximum} characters")
    return value.strip()


def require_exact_keys(value, label, required, optional=()):
    if not isinstance(value, dict):
        fail(f"{label} must be an object")
    unknown = set(value) - set(required) - set(optional)
    missing = set(required) - set(value)
    if unknown:
        fail(f"unknown {label} fields: " + ", ".join(sorted(unknown)))
    if missing:
        fail(f"missing {label} fields: " + ", ".join(sorted(missing)))


def validate_string_list(value, label, maximum_items=30):
    if not isinstance(value, list) or not value or len(value) > maximum_items:
        fail(f"{label} must be a non-empty array with at most {maximum_items} items")
    return [require_short_text(item, f"{label} item") for item in value]


def load_brief(path):
    if path.suffix.lower() != ".json":
        fail("brief must be a .json file")
    data = json.loads(path.read_text(encoding="utf-8"))
    require_exact_keys(data, "brief", REQUIRED, OPTIONAL)

    for key in ("property_identifier", "audience", "objective", "tone", "cta"):
        data[key] = require_short_text(data[key], key)
    if data["video_type"] not in VIDEO_TYPES:
        fail("unsupported video_type")
    if not isinstance(data["duration_seconds"], int) or not 15 <= data["duration_seconds"] <= 300:
        fail("duration_seconds must be an integer from 15 to 300")
    if data["aspect_ratio"] not in RATIOS:
        fail("aspect_ratio must be one of " + ", ".join(sorted(RATIOS)))

    if not isinstance(data["verified_facts"], list) or not data["verified_facts"] or len(data["verified_facts"]) > 50:
        fail("verified_facts must be a non-empty array with at most 50 items")
    facts = []
    for index, fact in enumerate(data["verified_facts"]):
        require_exact_keys(fact, f"verified_facts[{index}]", ("fact", "source_ref"))
        facts.append(
            {
                "fact": require_short_text(fact["fact"], f"verified_facts[{index}].fact"),
                "source_ref": require_short_text(fact["source_ref"], f"verified_facts[{index}].source_ref"),
            }
        )
    data["verified_facts"] = facts

    if not isinstance(data["spaces"], list) or not data["spaces"] or len(data["spaces"]) > 30:
        fail("spaces must be a non-empty ordered array with at most 30 items")
    spaces, seen = [], set()
    for index, space in enumerate(data["spaces"]):
        require_exact_keys(space, f"spaces[{index}]", ("space_id", "name", "verified_details", "source_refs"))
        space_id = space["space_id"]
        if not isinstance(space_id, str) or not SAFE_ID.fullmatch(space_id):
            fail(f"spaces[{index}].space_id must match {SAFE_ID.pattern}")
        if space_id in seen:
            fail("space_id values must be unique")
        seen.add(space_id)
        spaces.append(
            {
                "space_id": space_id,
                "name": require_short_text(space["name"], f"spaces[{index}].name"),
                "verified_details": validate_string_list(
                    space["verified_details"], f"spaces[{index}].verified_details"
                ),
                "source_refs": validate_string_list(space["source_refs"], f"spaces[{index}].source_refs"),
            }
        )
    data["spaces"] = spaces

    require_exact_keys(
        data["rights"],
        "rights",
        (
            "property_media_rights_confirmed",
            "filming_access_confirmed",
            "identifiable_people",
            "people_consent_confirmed",
        ),
    )
    for key, value in data["rights"].items():
        if not isinstance(value, bool):
            fail(f"rights.{key} must be boolean")
    if not data["rights"]["property_media_rights_confirmed"]:
        fail("property/media rights must be confirmed")
    if not data["rights"]["filming_access_confirmed"]:
        fail("filming access must be confirmed")
    people_required = data["video_type"] in {"agent-led", "lifestyle"}
    if people_required and not data["rights"]["identifiable_people"]:
        fail("agent-led and lifestyle videos require an identifiable-person plan")
    if data["rights"]["identifiable_people"] and not data["rights"]["people_consent_confirmed"]:
        fail("people consent must be confirmed when identifiable people appear")

    require_exact_keys(data["disclosure"], "disclosure", ("scene_status", "disclosure_text"))
    if data["disclosure"]["scene_status"] not in SCENE_STATUSES:
        fail("unsupported disclosure.scene_status")
    disclosure_text = data["disclosure"]["disclosure_text"]
    if not isinstance(disclosure_text, str) or len(disclosure_text.strip()) > 500:
        fail("disclosure.disclosure_text must be a string of at most 500 characters")
    if data["disclosure"]["scene_status"] != "captured-real" and not disclosure_text.strip():
        fail("illustrative, recreated, or mixed scenes require disclosure text")
    data["disclosure"]["disclosure_text"] = disclosure_text.strip()

    if "constraints" in data:
        data["constraints"] = validate_string_list(data["constraints"], "constraints")
    return data


def distribute(total):
    weights = (0.12, 0.18, 0.32, 0.23, 0.15)
    durations = [max(2, round(total * weight)) for weight in weights]
    durations[-1] += total - sum(durations)
    if durations[-1] < 2:
        deficit = 2 - durations[-1]
        donor = max(range(len(durations) - 1), key=lambda i: durations[i])
        durations[donor] -= deficit
        durations[-1] = 2
    return durations


def build(brief):
    labels = ("orientation", "arrival", "spatial-flow", "verified-detail", "close")
    purposes = (
        "Orient the viewer using authorized, current property context.",
        "Establish an honest threshold or first spatial impression.",
        "Show the documented sequence and relationship of spaces.",
        "Examine a verified feature without altering condition or scale.",
        "Return to a truthful signature view and present the approved call to action.",
    )
    camera_intents = (
        "Stable establishing view or legally captured approach; avoid substituted surroundings.",
        "Eye-level approach or threshold reveal that preserves actual geometry.",
        "Measured movement following the real circulation path; avoid impossible transitions.",
        "Natural-perspective detail-to-context move; preserve materials and condition.",
        "Restrained hold or pullback with accurate overlays and disclosure when required.",
    )
    space_indexes = (0, 0, 1, 2, -1)
    durations = distribute(brief["duration_seconds"])
    cursor, timeline, shots = 0, [], []
    for index, (duration, label, purpose, camera, requested_space_index) in enumerate(
        zip(durations, labels, purposes, camera_intents, space_indexes), 1
    ):
        space = brief["spaces"][requested_space_index % len(brief["spaces"])]
        fact = brief["verified_facts"][(index - 1) % len(brief["verified_facts"])]
        start, end = cursor, cursor + duration
        shot_id = f"S{index:02d}"
        factual_basis = [fact["fact"], *space["verified_details"]]
        source_refs = sorted(set([fact["source_ref"], *space["source_refs"]]))
        timeline.append({"beat": label, "start_seconds": start, "end_seconds": end, "purpose": purpose})
        shots.append(
            {
                "shot_id": shot_id,
                "start_seconds": start,
                "end_seconds": end,
                "duration_seconds": duration,
                "beat": label,
                "space_id": space["space_id"],
                "space_name": space["name"],
                "narrative_purpose": purpose,
                "camera_intent": camera,
                "factual_basis": factual_basis,
                "source_refs": source_refs,
                "continuity_anchors": [
                    "actual spatial geometry",
                    "documented finishes and condition",
                    "current surroundings",
                ],
                "disclosure": brief["disclosure"],
                "prompt_brief": "Write an English production prompt using only the factual basis and source references in this shot. Preserve property reality and include the approved disclosure when applicable.",
            }
        )
        cursor = end
    return timeline, shots


def dump(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--brief", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    try:
        if not args.brief.is_file():
            fail("brief file does not exist")
        out = args.out.resolve()
        if out.exists() and (not out.is_dir() or any(out.iterdir())):
            fail("output directory must be absent or empty")
        brief = load_brief(args.brief.resolve())
        timeline, shots = build(brief)
        out.mkdir(parents=True, exist_ok=True)
        dump(out / "canonical-brief.json", brief)
        dump(out / "timeline.json", {"duration_seconds": brief["duration_seconds"], "beats": timeline})
        dump(out / "shot-list.json", {"aspect_ratio": brief["aspect_ratio"], "shots": shots})
        dump(
            out / "generation-receipts.json",
            {
                "receipts": [],
                "instructions": "Record production and provider attempts; never store credentials or private access details.",
            },
        )
        dump(
            out / "qa.json",
            {
                "mechanical": [
                    {"check": "all shot durations sum to target", "status": "pending"},
                    {"check": "all manifest checksums verified", "status": "pending"},
                    {"check": "all required production/provider receipts recorded", "status": "pending"},
                    {"check": "captions, rights, consent, and disclosures documented", "status": "pending"},
                ],
                "semantic": [
                    {"check": "all claims map to verified facts and sources", "status": "pending"},
                    {"check": "layout, scale, condition, views, and surroundings remain accurate", "status": "pending"},
                    {"check": "generated or recreated scenes are disclosed", "status": "pending"},
                ],
            },
        )
        files = [path for path in sorted(out.glob("*.json")) if path.name != "manifest.json"]
        manifest = {
            "schema_version": "1.0",
            "files": [{"path": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in files],
        }
        dump(out / "manifest.json", manifest)
        print(
            json.dumps(
                {"status": "ok", "output": str(out), "shots": len(shots), "duration_seconds": brief["duration_seconds"]}
            )
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}), file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
