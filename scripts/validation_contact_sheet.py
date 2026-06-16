"""
TextureAnalyzer visual validation tool.

Generates a contact-sheet image to help a human reviewer determine whether
TextureAnalyzer findings reflect genuine GPT artifact contamination or merely
rank images by texture complexity.

Four groups are shown side by side:
  A  HIGH findings        — top 5 by z-score (most severe first)
  B  MEDIUM findings      — top 5 by z-score
  C  Threshold boundary   — 5 images with z-scores closest to 1.0 (the MEDIUM gate)
  D  Clean reference      — 5 images with the lowest z-scores

Each thumbnail carries a label strip:
  filename | severity tag
  micro=XX.X  z=+X.XX  smooth=XX.X  speck=XX.X

This is a one-time validation aid.  It modifies no project code and produces
no Finding objects.  Run it, look at the sheet, then delete the PNG.

Usage
-----
    python scripts/validation_contact_sheet.py \\
        --report path/to/inspection_report.json \\
        --dataset path/to/dataset \\
        --output contact_sheet.png

--dataset is optional when the JSON's dataset_path field is a valid directory.
--report defaults to inspection_report.json in the current directory.
--output defaults to contact_sheet.png next to --report.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import NamedTuple

import numpy as np
from PIL import Image, ImageDraw, ImageFont

# Allow running from repo root without installing the package.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from dataset_forge.analysis.texture import evaluate_texture
from dataset_forge.discovery import discover_images


# ---------------------------------------------------------------------------
# Layout constants
# ---------------------------------------------------------------------------

THUMB_W = 256
THUMB_H = 256
LABEL_H = 72          # pixel height of text strip below each thumbnail
TILE_W = THUMB_W      # tile width (no side padding within group)
TILE_H = THUMB_H + LABEL_H

GROUP_COLS = 5        # images per group
GROUP_GAP = 28        # horizontal gap between groups
TILE_GAP = 6          # gap between tiles within a group
HEADER_H = 36         # height of group header row
OUTER_PAD = 24        # outer margin

BG_COLOR = (18, 22, 30)
HEADER_BG = (30, 36, 50)
TILE_BG = (28, 34, 46)
LABEL_BG = (22, 27, 38)
TEXT_DIM = (110, 125, 145)
TEXT_BRIGHT = (220, 225, 235)
TEXT_ACCENT_HIGH = (240, 100, 80)
TEXT_ACCENT_MED = (240, 185, 60)
TEXT_ACCENT_THRESH = (100, 190, 140)
TEXT_ACCENT_CLEAN = (100, 160, 230)
TEXT_ERROR = (160, 80, 80)

GROUP_COLORS = {
    "A": TEXT_ACCENT_HIGH,
    "B": TEXT_ACCENT_MED,
    "C": TEXT_ACCENT_THRESH,
    "D": TEXT_ACCENT_CLEAN,
}

GROUP_LABELS = {
    "A": "HIGH FINDINGS  (top 5 by z-score)",
    "B": "MEDIUM FINDINGS  (top 5 by z-score)",
    "C": "THRESHOLD BOUNDARY  (z-scores nearest ±1.0)",
    "D": "CLEAN REFERENCE  (5 lowest z-scores)",
}


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

class ImageRecord(NamedTuple):
    path: Path
    severity: str          # "HIGH", "MEDIUM", "NONE", "MISSING" (finding absent)
    micro: float
    z: float
    smooth: float
    speck: float


# ---------------------------------------------------------------------------
# Font loading
# ---------------------------------------------------------------------------

def _font(size: int) -> ImageFont.ImageFont:
    candidates = [
        "C:/Windows/Fonts/consola.ttf",
        "C:/Windows/Fonts/cour.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
    ]
    for c in candidates:
        try:
            return ImageFont.truetype(c, size)
        except (OSError, IOError):
            pass
    return ImageFont.load_default()


_FONT_SM = None
_FONT_MD = None
_FONT_LG = None


def _init_fonts() -> None:
    global _FONT_SM, _FONT_MD, _FONT_LG
    _FONT_SM = _font(11)
    _FONT_MD = _font(12)
    _FONT_LG = _font(14)


# ---------------------------------------------------------------------------
# Score extraction
# ---------------------------------------------------------------------------

def _collect_scores(
    image_paths: list[Path],
    dist_mean: float,
    dist_stddev: float,
    findings_by_path: dict[str, dict],
) -> list[ImageRecord]:
    """Run evaluate_texture on every image and return ImageRecord list."""
    records: list[ImageRecord] = []
    for path in image_paths:
        tex = evaluate_texture(path)
        if tex.status != "analyzed":
            # Represent error images so they don't silently vanish.
            records.append(ImageRecord(
                path=path,
                severity="ERROR",
                micro=0.0,
                z=0.0,
                smooth=0.0,
                speck=0.0,
            ))
            continue

        micro = tex.microtexture_density_score
        smooth = tex.watercolor_smoothness_score
        speck = tex.highlight_speck_score
        z = (micro - dist_mean) / dist_stddev if dist_stddev > 0 else 0.0

        key = str(path)
        f = findings_by_path.get(key)
        severity = f["severity"] if f else "NONE"

        records.append(ImageRecord(
            path=path,
            severity=severity,
            micro=micro,
            z=z,
            smooth=smooth,
            speck=speck,
        ))
    return records


# ---------------------------------------------------------------------------
# Group selection
# ---------------------------------------------------------------------------

def _select_groups(records: list[ImageRecord]) -> dict[str, list[ImageRecord]]:
    """Choose the four groups of images for the contact sheet."""
    high = sorted(
        [r for r in records if r.severity == "HIGH"],
        key=lambda r: r.z, reverse=True,
    )[:5]

    medium = sorted(
        [r for r in records if r.severity == "MEDIUM"],
        key=lambda r: r.z, reverse=True,
    )[:5]

    # Threshold boundary: images closest to z=1.0 (the MEDIUM gate),
    # regardless of whether they were flagged.  This shows whether the
    # threshold line falls in a sensible visual location.
    threshold_z = 1.0
    boundary = sorted(
        records,
        key=lambda r: abs(r.z - threshold_z),
    )[:5]
    # Sort boundary by z descending so higher-z (flagged) images come first.
    boundary = sorted(boundary, key=lambda r: r.z, reverse=True)

    clean = sorted(
        [r for r in records if r.severity == "NONE"],
        key=lambda r: r.z,
    )[:5]

    # Pad short groups with None placeholders so layout stays consistent.
    def _pad(lst: list[ImageRecord], n: int = 5) -> list[ImageRecord | None]:
        return lst + [None] * max(0, n - len(lst))

    return {
        "A": _pad(high),
        "B": _pad(medium),
        "C": _pad(boundary),
        "D": _pad(clean),
    }


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _severity_color(severity: str) -> tuple[int, int, int]:
    return {
        "HIGH": TEXT_ACCENT_HIGH,
        "MEDIUM": TEXT_ACCENT_MED,
        "NONE": TEXT_ACCENT_CLEAN,
        "ERROR": TEXT_ERROR,
    }.get(severity, TEXT_DIM)


def _draw_tile(
    canvas: Image.Image,
    record: ImageRecord | None,
    x: int,
    y: int,
    group_id: str,
) -> None:
    draw = ImageDraw.Draw(canvas)

    # Background
    draw.rectangle([x, y, x + TILE_W - 1, y + TILE_H - 1], fill=TILE_BG)

    if record is None:
        # Empty slot
        draw.rectangle([x, y, x + TILE_W - 1, y + THUMB_H - 1], fill=(24, 28, 38))
        draw.text((x + TILE_W // 2, y + THUMB_H // 2), "—",
                  fill=TEXT_DIM, font=_FONT_MD, anchor="mm")
        return

    # Thumbnail
    try:
        with Image.open(record.path) as img:
            img = img.convert("RGB")
            img.thumbnail((THUMB_W, THUMB_H), Image.Resampling.LANCZOS)
            # Center-paste onto a fixed-size background
            bg = Image.new("RGB", (THUMB_W, THUMB_H), TILE_BG)
            paste_x = (THUMB_W - img.width) // 2
            paste_y = (THUMB_H - img.height) // 2
            bg.paste(img, (paste_x, paste_y))
            canvas.paste(bg, (x, y))
    except Exception:
        draw.rectangle([x, y, x + TILE_W - 1, y + THUMB_H - 1], fill=(24, 28, 38))
        draw.text((x + 4, y + THUMB_H // 2), "⚠ load error",
                  fill=TEXT_ERROR, font=_FONT_SM)

    # Label strip background
    label_y = y + THUMB_H
    draw.rectangle([x, label_y, x + TILE_W - 1, y + TILE_H - 1], fill=LABEL_BG)

    # Severity accent bar (3px top of label strip)
    accent = _severity_color(record.severity)
    draw.rectangle([x, label_y, x + TILE_W - 1, label_y + 2], fill=accent)

    lpad = 5
    ty = label_y + 6

    # Line 1: filename (truncated)
    name = record.path.name
    if len(name) > 30:
        name = name[:13] + "…" + name[-14:]
    draw.text((x + lpad, ty), name, fill=TEXT_BRIGHT, font=_FONT_SM)
    ty += 14

    # Line 2: severity tag
    sev_label = f"[ {record.severity} ]" if record.severity != "NONE" else "[ clean ]"
    draw.text((x + lpad, ty), sev_label, fill=accent, font=_FONT_SM)
    ty += 14

    # Line 3: micro + z
    draw.text(
        (x + lpad, ty),
        f"micro={record.micro:5.1f}   z={record.z:+.2f}",
        fill=TEXT_DIM, font=_FONT_SM,
    )
    ty += 13

    # Line 4: smooth + speck
    draw.text(
        (x + lpad, ty),
        f"smooth={record.smooth:5.1f}  speck={record.speck:5.1f}",
        fill=TEXT_DIM, font=_FONT_SM,
    )


def _draw_group_header(
    canvas: Image.Image,
    group_id: str,
    x: int,
    y: int,
    group_w: int,
) -> None:
    draw = ImageDraw.Draw(canvas)
    color = GROUP_COLORS[group_id]
    draw.rectangle([x, y, x + group_w - 1, y + HEADER_H - 1], fill=HEADER_BG)
    # Left accent bar
    draw.rectangle([x, y, x + 3, y + HEADER_H - 1], fill=color)
    label = f"  {group_id}  {GROUP_LABELS[group_id]}"
    draw.text((x + 10, y + HEADER_H // 2), label,
              fill=color, font=_FONT_LG, anchor="lm")


def _build_canvas(groups: dict[str, list[ImageRecord | None]]) -> Image.Image:
    group_ids = ["A", "B", "C", "D"]
    n_groups = len(group_ids)
    group_w = GROUP_COLS * TILE_W + (GROUP_COLS - 1) * TILE_GAP

    total_w = OUTER_PAD * 2 + group_w * n_groups + GROUP_GAP * (n_groups - 1)
    total_h = OUTER_PAD * 2 + n_groups * (HEADER_H + TILE_H + TILE_GAP)

    canvas = Image.new("RGB", (total_w, total_h), BG_COLOR)
    draw = ImageDraw.Draw(canvas)

    # Title bar
    title = "Dataset Forge — TextureAnalyzer Visual Validation"
    subtitle = "Review: Are flagged images visibly more textured than clean ones?"
    draw.text((OUTER_PAD, 8), title, fill=TEXT_BRIGHT, font=_FONT_LG)
    draw.text((OUTER_PAD, 8 + 18), subtitle, fill=TEXT_DIM, font=_FONT_SM)

    y = OUTER_PAD + 36    # extra space for title

    for gi, gid in enumerate(group_ids):
        tiles = groups[gid]
        gx = OUTER_PAD + gi * (group_w + GROUP_GAP)

        # Group header
        _draw_group_header(canvas, gid, gx, y, group_w)
        ty = y + HEADER_H + TILE_GAP

        for ci, record in enumerate(tiles):
            tx = gx + ci * (TILE_W + TILE_GAP)
            _draw_tile(canvas, record, tx, ty, gid)

        y += HEADER_H + TILE_H + TILE_GAP * 2 + 8    # row gap

    return canvas


# ---------------------------------------------------------------------------
# Summary text
# ---------------------------------------------------------------------------

def _print_summary(
    groups: dict[str, list[ImageRecord | None]],
    dist_mean: float,
    dist_stddev: float,
    output_path: Path,
) -> None:
    print("\nContact Sheet Summary")
    print("=" * 60)
    print(f"Output:  {output_path}")
    print(f"Dataset baseline:  mean={dist_mean:.2f}  stddev={dist_stddev:.2f}")
    print(f"Threshold:  z >= 1.0  (= micro >= {dist_mean + dist_stddev:.1f})")
    print()

    labels = {
        "A": "HIGH findings",
        "B": "MEDIUM findings",
        "C": "Threshold boundary",
        "D": "Clean reference",
    }
    for gid in ["A", "B", "C", "D"]:
        print(f"Group {gid}  {labels[gid]}")
        for r in groups[gid]:
            if r is None:
                print("   (empty slot)")
            else:
                tag = f"[{r.severity:<6}]"
                print(
                    f"   {tag}  {r.path.name:<40}"
                    f"micro={r.micro:5.1f}  z={r.z:+.2f}"
                    f"  smooth={r.smooth:5.1f}  speck={r.speck:5.1f}"
                )
        print()

    print("What to look for:")
    print("  • Groups A/B should look visibly more detailed/noisy than D.")
    print("  • Group C should sit at the perceptual boundary — not obvious.")
    print("  • Any Group A/B image that looks as clean as Group D = false positive.")
    print("  • Any Group D image that looks more textured than A/B = missed detection.")
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Generate a visual validation contact sheet for TextureAnalyzer findings.",
    )
    p.add_argument(
        "--report",
        type=Path,
        default=Path("inspection_report.json"),
        help="Path to inspection_report.json produced by dataset-forge inspect.",
    )
    p.add_argument(
        "--dataset",
        type=Path,
        default=None,
        help="Path to dataset directory. Inferred from report if omitted.",
    )
    p.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output PNG path. Defaults to contact_sheet.png next to --report.",
    )
    p.add_argument(
        "--recursive",
        action="store_true",
        help="Search dataset subdirectories recursively.",
    )
    return p.parse_args()


def main() -> None:
    args = _parse_args()

    # Load report
    report_path = args.report.expanduser().resolve()
    if not report_path.exists():
        print(f"ERROR: Report not found: {report_path}", file=sys.stderr)
        sys.exit(1)

    report = json.loads(report_path.read_text(encoding="utf-8"))

    # Resolve dataset path
    dataset_path = args.dataset
    if dataset_path is None:
        dataset_path = Path(report.get("dataset_path", ""))
    dataset_path = dataset_path.expanduser().resolve()
    if not dataset_path.is_dir():
        print(
            f"ERROR: Dataset directory not found: {dataset_path}\n"
            "Pass --dataset explicitly if the path has moved.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Resolve output path
    output_path = args.output
    if output_path is None:
        output_path = report_path.parent / "contact_sheet.png"
    output_path = output_path.expanduser().resolve()

    # Extract dataset distribution from report context
    ctx = report.get("context", {})
    tex_dist = ctx.get("texture_distributions", {})
    dist_mean = tex_dist.get("mean", 0.0)
    dist_stddev = tex_dist.get("stddev", 1.0)
    if dist_stddev == 0.0:
        dist_stddev = 1.0

    # Build findings index: str(path) → finding dict
    findings_by_path: dict[str, dict] = {}
    for f in report.get("findings", []):
        findings_by_path[str(Path(f["image_path"]).resolve())] = f

    # Discover images
    print(f"Scanning dataset: {dataset_path}")
    discovery = discover_images(dataset_path, recursive=args.recursive)
    image_paths = discovery.images
    print(f"Found {len(image_paths)} images.")

    # Score every image (re-runs evaluate_texture — acceptable for a one-off tool)
    print("Evaluating texture scores…")
    records = _collect_scores(image_paths, dist_mean, dist_stddev, findings_by_path)

    # Select groups
    groups = _select_groups(records)

    # Render
    _init_fonts()
    print("Rendering contact sheet…")
    canvas = _build_canvas(groups)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, "PNG")
    print(f"Saved: {output_path}  ({canvas.width}x{canvas.height}px)")

    # Summary
    _print_summary(groups, dist_mean, dist_stddev, output_path)


if __name__ == "__main__":
    main()
