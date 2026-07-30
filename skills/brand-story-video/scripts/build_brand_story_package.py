#!/usr/bin/env python3
"""Build deterministic, local preproduction artifacts from a brand-story brief."""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

REQUIRED = (
    "brand",
    "audience",
    "objective",
    "offer",
    "proof",
    "cta",
    "duration_seconds",
    "aspect_ratio",
    "tone",
    "story_architecture",
)
ARCHITECTURES = {"origin", "customer-transformation", "craft-process", "mission-anthem", "milestone", "day-in-the-life"}
RATIOS = {"16:9", "9:16", "1:1", "4:5"}
SAFE_KEY = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


def fail(message):
    raise ValueError(message)


def load_brief(path):
    if path.suffix.lower() != ".json":
        fail("brief must be a .json file")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        fail("brief must be a JSON object")
    unknown = set(data) - set(REQUIRED) - {"constraints", "brand_assets", "rights_notes"}
    if unknown:
        fail("unknown brief fields: " + ", ".join(sorted(unknown)))
    missing = [key for key in REQUIRED if not data.get(key)]
    if missing:
        fail("missing required brief fields: " + ", ".join(missing))
    if not isinstance(data["duration_seconds"], int) or not 15 <= data["duration_seconds"] <= 180:
        fail("duration_seconds must be an integer from 15 to 180")
    if data["aspect_ratio"] not in RATIOS:
        fail("aspect_ratio must be one of " + ", ".join(sorted(RATIOS)))
    if data["story_architecture"] not in ARCHITECTURES:
        fail("unsupported story_architecture")
    for key in ("brand", "audience", "objective", "offer", "proof", "cta", "tone"):
        if not isinstance(data[key], str) or len(data[key].strip()) > 500:
            fail(f"{key} must be a non-empty string of at most 500 characters")
    return data


def distribute(total):
    weights = (0.10, 0.22, 0.27, 0.25, 0.16)
    values = [max(2, round(total * weight)) for weight in weights]
    values[-1] += total - sum(values)
    return values


def build(brief):
    labels = ("hook", "tension", "action", "outcome", "signature")
    purposes = (
        "Establish a truthful, human entry point.",
        "Make the audience problem or stakes concrete.",
        "Show the brand or protagonist acting on the problem.",
        "Show supported evidence of the intended change.",
        "Land the message, CTA, and restrained brand signature.",
    )
    cursor, timeline, shots = 0, [], []
    for index, (duration, label, purpose) in enumerate(zip(distribute(brief["duration_seconds"]), labels, purposes), 1):
        start, end = cursor, cursor + duration
        shot_id = f"S{index:02d}"
        timeline.append({"beat": label, "start_seconds": start, "end_seconds": end, "purpose": purpose})
        shots.append(
            {
                "shot_id": shot_id,
                "start_seconds": start,
                "end_seconds": end,
                "duration_seconds": duration,
                "beat": label,
                "narrative_purpose": purpose,
                "continuity_anchors": ["approved brand palette", "approved product and logo treatment"],
                "evidence": brief["proof"] if label in {"action", "outcome"} else "No external claim required.",
                "prompt_brief": f"English prompt required: {purpose}",
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
        out.mkdir(parents=True, exist_ok=True)
        brief = load_brief(args.brief.resolve())
        timeline, shots = build(brief)
        dump(out / "brand-bible.json", brief)
        dump(out / "timeline.json", {"duration_seconds": brief["duration_seconds"], "beats": timeline})
        dump(out / "shot-list.json", {"aspect_ratio": brief["aspect_ratio"], "shots": shots})
        dump(
            out / "generation-receipts.json",
            {"receipts": [], "instructions": "Record provider attempts; never store credentials."},
        )
        dump(
            out / "qa.json",
            {
                "mechanical": [
                    {"check": "all shot durations sum to target", "status": "pending"},
                    {"check": "all required receipts recorded", "status": "pending"},
                    {"check": "captions and rights documented", "status": "pending"},
                ],
                "semantic": [
                    {"check": "claims supported and story coherent", "status": "pending"},
                    {"check": "consent and disclosure reviewed", "status": "pending"},
                ],
            },
        )
        files = [p for p in sorted(out.glob("*.json")) if p.name != "manifest.json"]
        manifest = {
            "schema_version": "1.0",
            "files": [{"path": p.name, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in files],
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
