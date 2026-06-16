"""Inspection gallery — PNG contact sheet for visual review of findings.

Generates inspection_gallery.png in the inspect output folder when the
caller requests it. Four groups are shown side-by-side:

  A  HIGH findings        — top 5 by z-score, most severe first
  B  MEDIUM findings      — top 5 by z-score
  C  Threshold boundary   — 5 images with z-scores nearest z=1.0
  D  Clean reference      — 5 images with the lowest z-scores

Public API
----------
  write_inspection_gallery(findings, context, output_path, image_scores) -> Path

Internal helpers are exposed for unit testing:
  build_image_records(image_scores, findings, dist_mean, dist_stddev) -> list[ImageRecord]
  select_gallery_groups(records) -> dict[str, list[ImageRecord | None]]
"""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

from PIL import Image, ImageDraw, ImageFont

from dataset_forge.context import DatasetContext
from dataset_forge.finding import Finding


# ---------------------------------------------------------------------------
# Layout constants
# ---------------------------------------------------------------------------

THUMB_W = 256
THUMB_H = 256
LABEL_H = 72
TILE_W = THUMB_W
TILE_H = THUMB_H + LABEL_H

GROUP_COLS = 5
GROUP_GAP = 28
TILE_GAP = 6
HEADER_H = 36
OUTER_PAD = 24
TITLE_EXTRA = 36     # space above first group for title text

_BG = (18, 22, 30)
_HEADER_BG = (30, 36, 50)
_TILE_BG = (28, 34, 46)
_LABEL_BG = (22, 27, 38)
_TEXT_DIM = (110, 125, 145)
_TEXT_BRIGHT = (220, 225, 235)

_SEV_COLORS: dict[str, tuple[int, int, int]] = {
    "HIGH":     (240, 100,  80),
    "CRITICAL": (240,  60,  60),
    "MEDIUM":   (240, 185,  60),
    "LOW":      (160, 210, 100),
    "NONE":     (100, 160, 230),
    "ERROR":    (160,  80,  80),
}

_GROUP_COLORS: dict[str, tuple[int, int, int]] = {
    "A": _SEV_COLORS["HIGH"],
    "B": _SEV_COLORS["MEDIUM"],
    "C": (100, 190, 140),
    "D": _SEV_COLORS["NONE"],
}

_GROUP_LABELS = {
    "A": "HIGH FINDINGS  (top 5 by z-score)",
    "B": "MEDIUM FINDINGS  (top 5 by z-score)",
    "C": "THRESHOLD BOUNDARY  (z-scores nearest ±1.0)",
    "D": "CLEAN REFERENCE  (5 lowest z-scores)",
}

_Z_MEDIUM_GATE = 1.0


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

class ImageRecord(NamedTuple):
    """One image's scores and finding status, ready for rendering."""

    path: Path
    severity: str    # "HIGH", "MEDIUM", "LOW", "NONE", "ERROR"
    micro: float
    z: float
    smooth: float
    speck: float


# ---------------------------------------------------------------------------
# Public helpers (exposed for testing)
# ---------------------------------------------------------------------------

def build_image_records(
    image_scores: dict[str, dict],
    findings: list[Finding],
    dist_mean: float,
    dist_stddev: float,
) -> list[ImageRecord]:
    """Convert image_scores dict → list[ImageRecord].

    Severity is taken from the highest-severity Finding for the image when
    one exists, otherwise "NONE".  Z-score is computed from the dataset
    distribution passed in.
    """
    # Index findings by resolved path string, keeping highest severity.
    sev_order = {"CRITICAL": 5, "HIGH": 4, "MEDIUM": 3, "LOW": 2, "NONE": 1}
    finding_sev: dict[str, str] = {}
    for f in findings:
        key = str(Path(f.image_path).resolve())
        if sev_order.get(f.severity.name, 0) > sev_order.get(finding_sev.get(key, "NONE"), 0):
            finding_sev[key] = f.severity.name

    safe_stddev = dist_stddev if dist_stddev > 0 else 1.0
    records: list[ImageRecord] = []

    for path_str, scores in image_scores.items():
        path = Path(path_str)
        resolved_str = str(path.resolve())

        if "error" in scores:
            records.append(ImageRecord(
                path=path,
                severity="ERROR",
                micro=0.0,
                z=0.0,
                smooth=0.0,
                speck=0.0,
            ))
            continue

        micro = float(scores.get("microtexture_density", 0.0))
        smooth = float(scores.get("watercolor_smoothness", 0.0))
        speck = float(scores.get("highlight_speck", 0.0))
        z = (micro - dist_mean) / safe_stddev

        severity = finding_sev.get(resolved_str, "NONE")

        records.append(ImageRecord(
            path=path,
            severity=severity,
            micro=micro,
            z=z,
            smooth=smooth,
            speck=speck,
        ))

    return records


def select_gallery_groups(
    records: list[ImageRecord],
) -> dict[str, list[ImageRecord | None]]:
    """Partition records into the four display groups.

    Returns a dict with keys "A", "B", "C", "D".  Each value is a list of
    exactly GROUP_COLS entries (padded with None for empty slots).
    """
    def _pad(lst: list[ImageRecord]) -> list[ImageRecord | None]:
        return lst + [None] * max(0, GROUP_COLS - len(lst))

    high = sorted(
        [r for r in records if r.severity == "HIGH"],
        key=lambda r: r.z, reverse=True,
    )[:GROUP_COLS]

    medium = sorted(
        [r for r in records if r.severity == "MEDIUM"],
        key=lambda r: r.z, reverse=True,
    )[:GROUP_COLS]

    # Boundary: images whose z-scores are closest to the MEDIUM gate (z=1.0).
    # Deduplicate paths that may already appear in high/medium groups so the
    # reviewer sees fresh images rather than repeats.
    already_shown = {r.path for r in high + medium}
    boundary_pool = [r for r in records if r.path not in already_shown]
    boundary = sorted(boundary_pool, key=lambda r: abs(r.z - _Z_MEDIUM_GATE))[:GROUP_COLS]
    boundary = sorted(boundary, key=lambda r: r.z, reverse=True)

    clean = sorted(
        [r for r in records if r.severity == "NONE"],
        key=lambda r: r.z,
    )[:GROUP_COLS]

    return {
        "A": _pad(high),
        "B": _pad(medium),
        "C": _pad(boundary),
        "D": _pad(clean),
    }


# ---------------------------------------------------------------------------
# Font loading
# ---------------------------------------------------------------------------

def _load_font(size: int) -> ImageFont.ImageFont:
    candidates = [
        "C:/Windows/Fonts/consola.ttf",
        "C:/Windows/Fonts/cour.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            pass
    return ImageFont.load_default()


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _draw_tile(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    record: ImageRecord | None,
    x: int,
    y: int,
    font_sm: ImageFont.ImageFont,
    font_md: ImageFont.ImageFont,
) -> None:
    draw.rectangle([x, y, x + TILE_W - 1, y + TILE_H - 1], fill=_TILE_BG)

    if record is None:
        draw.rectangle([x, y, x + TILE_W - 1, y + THUMB_H - 1], fill=(24, 28, 38))
        draw.text(
            (x + TILE_W // 2, y + THUMB_H // 2), "—",
            fill=_TEXT_DIM, font=font_md, anchor="mm",
        )
        return

    # Thumbnail
    try:
        with Image.open(record.path) as img:
            img = img.convert("RGB")
            img.thumbnail((THUMB_W, THUMB_H), Image.Resampling.LANCZOS)
            bg = Image.new("RGB", (THUMB_W, THUMB_H), _TILE_BG)
            paste_x = (THUMB_W - img.width) // 2
            paste_y = (THUMB_H - img.height) // 2
            bg.paste(img, (paste_x, paste_y))
            canvas.paste(bg, (x, y))
    except Exception:
        draw.rectangle([x, y, x + TILE_W - 1, y + THUMB_H - 1], fill=(24, 28, 38))
        draw.text((x + 4, y + THUMB_H // 2), "load error", fill=_SEV_COLORS["ERROR"], font=font_sm)

    # Label strip
    label_y = y + THUMB_H
    draw.rectangle([x, label_y, x + TILE_W - 1, y + TILE_H - 1], fill=_LABEL_BG)

    # Severity accent bar (3 px top of label strip)
    accent = _SEV_COLORS.get(record.severity, _TEXT_DIM)
    draw.rectangle([x, label_y, x + TILE_W - 1, label_y + 2], fill=accent)

    lpad = 5
    ty = label_y + 6

    name = record.path.name
    if len(name) > 30:
        name = name[:13] + "…" + name[-14:]
    draw.text((x + lpad, ty), name, fill=_TEXT_BRIGHT, font=font_sm)
    ty += 14

    sev_label = f"[ {record.severity} ]" if record.severity != "NONE" else "[ clean ]"
    draw.text((x + lpad, ty), sev_label, fill=accent, font=font_sm)
    ty += 14

    draw.text(
        (x + lpad, ty),
        f"micro={record.micro:5.1f}   z={record.z:+.2f}",
        fill=_TEXT_DIM, font=font_sm,
    )
    ty += 13

    draw.text(
        (x + lpad, ty),
        f"smooth={record.smooth:5.1f}  speck={record.speck:5.1f}",
        fill=_TEXT_DIM, font=font_sm,
    )


def _draw_group_header(
    draw: ImageDraw.ImageDraw,
    group_id: str,
    x: int,
    y: int,
    group_w: int,
    font_lg: ImageFont.ImageFont,
) -> None:
    color = _GROUP_COLORS[group_id]
    draw.rectangle([x, y, x + group_w - 1, y + HEADER_H - 1], fill=_HEADER_BG)
    draw.rectangle([x, y, x + 3, y + HEADER_H - 1], fill=color)
    draw.text(
        (x + 10, y + HEADER_H // 2),
        f"  {group_id}  {_GROUP_LABELS[group_id]}",
        fill=color, font=font_lg, anchor="lm",
    )


def _build_canvas(
    groups: dict[str, list[ImageRecord | None]],
    dist_mean: float,
    dist_stddev: float,
) -> Image.Image:
    group_ids = ["A", "B", "C", "D"]
    n_groups = len(group_ids)
    group_w = GROUP_COLS * TILE_W + (GROUP_COLS - 1) * TILE_GAP

    total_w = OUTER_PAD * 2 + group_w * n_groups + GROUP_GAP * (n_groups - 1)
    total_h = (
        OUTER_PAD * 2
        + TITLE_EXTRA
        + n_groups * (HEADER_H + TILE_H + TILE_GAP * 2 + 8)
    )

    canvas = Image.new("RGB", (total_w, total_h), _BG)
    draw = ImageDraw.Draw(canvas)

    font_sm = _load_font(11)
    font_md = _load_font(12)
    font_lg = _load_font(14)

    # Title
    threshold_micro = dist_mean + dist_stddev
    draw.text(
        (OUTER_PAD, 8),
        "Dataset Forge — Inspection Gallery",
        fill=_TEXT_BRIGHT, font=font_lg,
    )
    draw.text(
        (OUTER_PAD, 26),
        f"Baseline: mean={dist_mean:.1f}  stddev={dist_stddev:.1f}  "
        f"MEDIUM gate: micro≥{threshold_micro:.1f} (z≥1.0)",
        fill=_TEXT_DIM, font=font_sm,
    )

    y = OUTER_PAD + TITLE_EXTRA

    for gi, gid in enumerate(group_ids):
        tiles = groups[gid]
        gx = OUTER_PAD + gi * (group_w + GROUP_GAP)

        _draw_group_header(draw, gid, gx, y, group_w, font_lg)
        ty = y + HEADER_H + TILE_GAP

        for ci, record in enumerate(tiles):
            tx = gx + ci * (TILE_W + TILE_GAP)
            _draw_tile(canvas, draw, record, tx, ty, font_sm, font_md)

        y += HEADER_H + TILE_H + TILE_GAP * 2 + 8

    return canvas


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def write_inspection_gallery(
    findings: list[Finding],
    context: DatasetContext,
    output_path: Path,
    image_scores: dict[str, dict],
) -> Path:
    """Render and write the inspection gallery PNG.

    Uses image_scores that were already captured during DatasetContext
    building — no additional image reads required.

    Args:
        findings:     All findings from the current inspect run.
        context:      DatasetContext built by run_inspect().
        output_path:  Where to write the PNG (e.g. output_dir/inspection_gallery.png).
        image_scores: dict[str(path) → metric dict] from _build_context().

    Returns:
        The resolved output_path after writing.
    """
    dist = context.texture_distributions
    dist_mean = dist.mean
    dist_stddev = dist.stddev

    records = build_image_records(image_scores, findings, dist_mean, dist_stddev)
    groups = select_gallery_groups(records)
    canvas = _build_canvas(groups, dist_mean, dist_stddev)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, "PNG")
    return output_path.resolve()
