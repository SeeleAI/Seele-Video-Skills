#!/usr/bin/env python3
"""Normalize three comic sheets and emit deterministic storyboard QA/manifest/ZIP."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont, ImageStat
except ImportError as exc:  # verified in the authoring runtime; fail closed elsewhere
    raise SystemExit("Pillow is required for storyboard image processing") from exc

FINAL_SIZE = (1920, 1080)
CONTENT_SIZE = (1620, 1080)  # 3:2 source fitted into a 16:9 delivery canvas
EXPECTED_IDS = [f"{i:02d}" for i in range(1, 19)]
QA_KEYS = ("mapping", "character", "wardrobe", "props", "hands", "axis")
QA_STATES = {"pass", "warn", "fail", "not_reviewed"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def font(size: int):
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ]
    for item in candidates:
        try:
            return ImageFont.truetype(item, size)
        except OSError:
            continue
    return ImageFont.load_default()


def validate_shots(path: Path) -> tuple[dict, list[str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    shots = data.get("shots")
    errors: list[str] = []
    if not isinstance(shots, list) or len(shots) != 18:
        return data, ["shot list must contain exactly 18 shots"]
    ids = [str(s.get("shot_id", "")) for s in shots]
    if ids != EXPECTED_IDS or len(set(ids)) != 18:
        errors.append("shot IDs must be unique and ordered 01-18")
    durations = []
    for shot in shots:
        try:
            duration = float(shot.get("duration_seconds"))
            if duration <= 0:
                raise ValueError
            durations.append(duration)
        except (TypeError, ValueError):
            errors.append(f"shot {shot.get('shot_id')}: duration_seconds must be positive")
        continuity = shot.get("continuity") or {}
        for key in ("character", "wardrobe", "props", "hands", "screen_direction", "axis"):
            if not str(continuity.get(key, "")).strip():
                errors.append(f"shot {shot.get('shot_id')}: missing continuity.{key}")
        visual = shot.get("visual_qa") or {}
        for key in QA_KEYS:
            state = visual.get(key, "not_reviewed")
            if state not in QA_STATES:
                errors.append(f"shot {shot.get('shot_id')}: invalid visual_qa.{key}={state}")
    total = round(sum(durations), 3)
    data["total_duration_seconds"] = total
    if not 60 <= total <= 90:
        errors.append(f"total duration {total}s is outside 60-90s")
    return data, errors


def dark_ratio(image: Image.Image, box: tuple[int, int, int, int], threshold: int = 48) -> float:
    crop = image.crop(box).convert("L")
    hist = crop.histogram()
    return sum(hist[: threshold + 1]) / max(1, crop.width * crop.height)


def label_patch_ok(image: Image.Image, x: int, y: int) -> bool:
    crop = image.crop((x, y, x + 86, y + 58)).convert("L")
    extrema = crop.getextrema()
    return extrema[0] <= 50 and extrema[1] >= 205 and ImageStat.Stat(crop).var[0] >= 900


def normalize_sheet(source: Path, destination: Path, first_number: int) -> dict:
    with Image.open(source) as opened:
        image = opened.convert("L")
        image.thumbnail(CONTENT_SIZE, Image.Resampling.LANCZOS)
        canvas = Image.new("L", FINAL_SIZE, 0)
        left = (FINAL_SIZE[0] - image.width) // 2
        top = (FINAL_SIZE[1] - image.height) // 2
        canvas.paste(image, (left, top))
    # Enforce the delivery grid after proportional fitting; never stretch source art.
    content_left = (FINAL_SIZE[0] - CONTENT_SIZE[0]) // 2
    cell_w = CONTENT_SIZE[0] // 3
    cell_h = CONTENT_SIZE[1] // 2
    draw = ImageDraw.Draw(canvas)
    for x in (content_left + cell_w, content_left + 2 * cell_w):
        draw.rectangle((x - 3, 0, x + 3, FINAL_SIZE[1] - 1), fill=0)
    draw.rectangle((content_left, cell_h - 3, content_left + CONTENT_SIZE[0] - 1, cell_h + 3), fill=0)
    label_font = font(42)
    positions = []
    for index in range(6):
        col, row = index % 3, index // 3
        x = content_left + col * cell_w + 10
        y = row * cell_h + 10
        text = f"{first_number + index:02d}"
        bbox = draw.textbbox((0, 0), text, font=label_font)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.rounded_rectangle((x - 5, y - 4, x + w + 7, y + h + 7), radius=5, fill=255)
        draw.text((x, y), text, fill=0, font=label_font)
        positions.append((x - 5, y - 4))
    destination.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(destination, format="PNG", optimize=True)
    with Image.open(destination) as check:
        rgb = check.convert("RGB")
        # RGB channel equality is checked directly; extrema alone are insufficient.
        r, g, b = rgb.split()
        channel_equal = list(r.getdata()) == list(g.getdata()) == list(b.getdata())
        boundaries = {
            "vertical_1": round(dark_ratio(check, (content_left + cell_w - 3, 0, content_left + cell_w + 4, 1080)), 4),
            "vertical_2": round(dark_ratio(check, (content_left + 2 * cell_w - 3, 0, content_left + 2 * cell_w + 4, 1080)), 4),
            "horizontal": round(dark_ratio(check, (content_left, cell_h - 3, content_left + CONTENT_SIZE[0], cell_h + 4)), 4),
        }
        labels = [label_patch_ok(check, x, y) for x, y in positions]
        return {
            "source": str(source), "file": destination.name, "width": check.width, "height": check.height,
            "aspect_ratio": "16:9", "mode": check.mode, "grayscale_channels_equal": channel_equal,
            "layout": "3x2", "boundary_dark_ratios": boundaries, "number_label_patches": labels,
            "sha256": sha256(destination), "bytes": destination.stat().st_size,
        }


def qa_markdown(report: dict) -> str:
    lines = ["# Storyboard QA", "", f"- Mechanical: **{report['mechanical_status'].upper()}**", f"- Visual continuity: **{report['visual_status'].upper()}**", f"- Duration: {report['total_duration_seconds']}s", f"- Source trace: {report['source_trace'] or 'not supplied'}", "", "## Sheets"]
    for sheet in report["sheets"]:
        lines.append(f"- `{sheet['file']}`: {sheet['width']}×{sheet['height']}, {sheet['layout']}, grayscale={sheet['grayscale_channels_equal']}, labels={sum(sheet['number_label_patches'])}/6")
    lines.extend(["", "## Visual findings"])
    for item in report["visual_findings"]:
        lines.append(f"- Shot {item['shot_id']}: {item['status']} — {item['notes']}")
    lines.extend(["", "## Errors"])
    lines.extend([f"- {e}" for e in report["errors"]] or ["- None"])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sheet", action="append", required=True, type=Path, help="Repeat exactly three times")
    parser.add_argument("--shot-list", required=True, type=Path)
    parser.add_argument("--story-bible", type=Path)
    parser.add_argument("--continuity-ledger", type=Path)
    parser.add_argument("--prompts", type=Path)
    parser.add_argument("--source-trace", type=Path, help="Input → screenplay → shot mapping for delivery")
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    if len(args.sheet) != 3:
        parser.error("--sheet must be provided exactly three times")
    support_files = {
        "story-bible": args.story_bible,
        "continuity-ledger": args.continuity_ledger,
        "prompts": args.prompts,
        "source-trace": args.source_trace,
    }
    inputs = [*args.sheet, args.shot_list, *(path for path in support_files.values() if path)]
    missing = [str(path) for path in inputs if not path.is_file()]
    if missing:
        parser.error("missing input: " + ", ".join(missing))

    shots_data, errors = validate_shots(args.shot_list)
    out = args.output_dir
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"refusing to overwrite non-empty output directory: {out}")
    out.mkdir(parents=True, exist_ok=True)
    shutil.copy2(args.shot_list, out / "shot-list.json")
    copied_support_files = []
    for stem, source in support_files.items():
        if source:
            destination = out / f"{stem}{source.suffix.lower()}"
            shutil.copy2(source, destination)
            copied_support_files.append(destination.name)
    sheets = []
    for index, source in enumerate(args.sheet):
        first = index * 6 + 1
        destination = out / f"storyboard-{first:02d}-{first + 5:02d}.png"
        sheets.append(normalize_sheet(source, destination, first))

    for sheet in sheets:
        if (sheet["width"], sheet["height"]) != FINAL_SIZE or not sheet["grayscale_channels_equal"]:
            errors.append(f"{sheet['file']}: size/grayscale validation failed")
        if min(sheet["boundary_dark_ratios"].values()) < 0.95:
            errors.append(f"{sheet['file']}: 3x2 separators not detected")
        if not all(sheet["number_label_patches"]):
            errors.append(f"{sheet['file']}: one or more number labels not detected")

    findings = []
    visual_states = []
    for shot in shots_data.get("shots", []):
        visual = shot.get("visual_qa") or {}
        states = [visual.get(k, "not_reviewed") for k in QA_KEYS]
        visual_states.extend(states)
        worst = "fail" if "fail" in states else "warn" if ("warn" in states or "not_reviewed" in states) else "pass"
        findings.append({"shot_id": shot["shot_id"], "status": worst, "notes": visual.get("notes", "")})
    visual_status = "fail" if "fail" in visual_states else "warn" if ("warn" in visual_states or "not_reviewed" in visual_states) else "pass"
    source_trace = "source-trace.md" if "source-trace.md" in copied_support_files else None
    report = {"mechanical_status": "fail" if errors else "pass", "visual_status": visual_status,
              "total_duration_seconds": shots_data.get("total_duration_seconds"), "source_trace": source_trace,
              "sheets": sheets, "visual_findings": findings, "errors": errors}
    (out / "qa.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "qa.md").write_text(qa_markdown(report), encoding="utf-8")
    manifest = {"project": shots_data.get("project", ""), "shot_count": len(shots_data.get("shots", [])),
                "shot_ids": [s.get("shot_id") for s in shots_data.get("shots", [])],
                "total_duration_seconds": shots_data.get("total_duration_seconds"), "sheets": sheets,
                "support_files": copied_support_files,
                "qa": {"mechanical": report["mechanical_status"], "visual": visual_status}}
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    zip_path = out / "storyboard-delivery.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(out.iterdir()):
            if path != zip_path and path.is_file():
                archive.write(path, path.name)
    print(json.dumps({"success": not errors, "output_dir": str(out), "manifest": str(out / "manifest.json"),
                      "qa": str(out / "qa.json"), "zip": str(zip_path), "visual_status": visual_status}, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
