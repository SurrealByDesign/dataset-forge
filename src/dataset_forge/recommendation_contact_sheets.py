"""PNG contact sheets rendered from recommendation sidecars."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from PIL import Image, ImageDraw, ImageFont


THUMB_SIZE = 180
LABEL_H = 96
TILE_W = 220
TILE_H = THUMB_SIZE + LABEL_H
COLS = 4
PAD = 24
GAP = 12
HEADER_H = 72
MAX_TILES_PER_SHEET = 100

_BG = (246, 248, 251)
_PANEL = (255, 255, 255)
_LINE = (209, 216, 226)
_INK = (31, 41, 51)
_MUTED = (89, 100, 115)
_ACCENT = (40, 83, 107)

_SHEETS = (
    ("PRIORITY_REVIEW", "Priority Review", "priority_review_contact_sheet.png"),
    ("NEEDS_REVIEW", "Needs Review", "needs_review_contact_sheet.png"),
)


def write_recommendation_contact_sheets(
    inspection_report_path: Path,
    recommendation_summary_path: Path,
    output_dir: Path,
) -> tuple[Path, Path]:
    """Write Priority Review and Needs Review contact sheets from sidecars."""

    inspection_report = json.loads(inspection_report_path.read_text(encoding="utf-8"))
    recommendation_summary = json.loads(
        recommendation_summary_path.read_text(encoding="utf-8")
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for recommendation, title, filename in _SHEETS:
        items = _items_for(recommendation_summary, recommendation)
        output_path = output_dir / filename
        render_recommendation_contact_sheet(
            inspection_report,
            items,
            title=title,
        ).save(output_path, "PNG")
        written.append(output_path)
    return tuple(written)  # type: ignore[return-value]


def render_recommendation_contact_sheet(
    inspection_report: Mapping[str, Any],
    recommendations: list[Mapping[str, Any]],
    *,
    title: str,
) -> Image.Image:
    """Render one deterministic recommendation contact sheet."""

    display_items = recommendations[:MAX_TILES_PER_SHEET]
    rows = max(1, (len(display_items) + COLS - 1) // COLS)
    width = PAD * 2 + COLS * TILE_W + (COLS - 1) * GAP
    height = PAD * 2 + HEADER_H + rows * TILE_H + (rows - 1) * GAP

    canvas = Image.new("RGB", (width, height), _BG)
    draw = ImageDraw.Draw(canvas)
    font_lg = _load_font(20)
    font_md = _load_font(13)
    font_sm = _load_font(11)

    dataset_path = str(inspection_report.get("dataset_path", ""))
    draw.text((PAD, PAD), f"Dataset Forge - {title}", fill=_INK, font=font_lg)
    if dataset_path:
        draw.text((PAD, PAD + 28), _fit(dataset_path, 96), fill=_MUTED, font=font_sm)
    count_text = f"{len(recommendations)} {_image_word(len(recommendations))}"
    if len(recommendations) > MAX_TILES_PER_SHEET:
        count_text += f" - showing first {MAX_TILES_PER_SHEET}"
    draw.text((PAD, PAD + 46), count_text, fill=_MUTED, font=font_sm)

    y0 = PAD + HEADER_H
    if not display_items:
        _draw_empty_state(draw, PAD, y0, width - PAD * 2, TILE_H, font_md)
        return canvas

    for index, item in enumerate(display_items):
        col = index % COLS
        row = index // COLS
        x = PAD + col * (TILE_W + GAP)
        y = y0 + row * (TILE_H + GAP)
        _draw_tile(canvas, draw, item, x, y, font_md, font_sm)
    return canvas


def _items_for(
    recommendation_summary: Mapping[str, Any],
    recommendation: str,
) -> list[Mapping[str, Any]]:
    return [
        item for item in recommendation_summary.get("recommendations", [])
        if item.get("recommendation") == recommendation
    ]


def _draw_empty_state(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    width: int,
    height: int,
    font: ImageFont.ImageFont,
) -> None:
    draw.rectangle([x, y, x + width - 1, y + height - 1], fill=_PANEL, outline=_LINE)
    draw.text(
        (x + width // 2, y + height // 2),
        "No images in this review group.",
        fill=_MUTED,
        font=font,
        anchor="mm",
    )


def _draw_tile(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    item: Mapping[str, Any],
    x: int,
    y: int,
    font_md: ImageFont.ImageFont,
    font_sm: ImageFont.ImageFont,
) -> None:
    draw.rectangle([x, y, x + TILE_W - 1, y + TILE_H - 1], fill=_PANEL, outline=_LINE)
    image_box_x = x + (TILE_W - THUMB_SIZE) // 2
    image_box_y = y + 10
    _paste_thumbnail(canvas, draw, str(item.get("image_path", "")), image_box_x, image_box_y, font_sm)

    label_y = y + THUMB_SIZE + 16
    refs = list(item.get("finding_refs", []))
    primary_ref = refs[0] if refs else {}
    reason = str(item.get("primary_reason", "")) or str(primary_ref.get("category", ""))

    draw.text((x + 10, label_y), _fit(Path(str(item.get("image_path", "")).strip()).name, 30), fill=_INK, font=font_md)
    draw.text((x + 10, label_y + 18), str(item.get("display_label", "")), fill=_ACCENT, font=font_sm)
    draw.text((x + 10, label_y + 34), _fit(reason, 34), fill=_MUTED, font=font_sm)
    if primary_ref:
        category = str(primary_ref.get("category", ""))
        draw.text((x + 10, label_y + 50), _fit(category, 34), fill=_MUTED, font=font_sm)


def _paste_thumbnail(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    image_path: str,
    x: int,
    y: int,
    font: ImageFont.ImageFont,
) -> None:
    draw.rectangle([x, y, x + THUMB_SIZE - 1, y + THUMB_SIZE - 1], fill=(238, 242, 246), outline=_LINE)
    try:
        with Image.open(Path(image_path)) as image:
            image = image.convert("RGB")
            image.thumbnail((THUMB_SIZE, THUMB_SIZE), Image.Resampling.LANCZOS)
            bg = Image.new("RGB", (THUMB_SIZE, THUMB_SIZE), (238, 242, 246))
            paste_x = (THUMB_SIZE - image.width) // 2
            paste_y = (THUMB_SIZE - image.height) // 2
            bg.paste(image, (paste_x, paste_y))
            canvas.paste(bg, (x, y))
    except (OSError, ValueError):
        draw.text((x + THUMB_SIZE // 2, y + THUMB_SIZE // 2), "image unavailable", fill=_MUTED, font=font, anchor="mm")


def _fit(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    if max_chars <= 3:
        return text[:max_chars]
    return text[: max_chars - 3] + "..."


def _image_word(count: int) -> str:
    return "image" if count == 1 else "images"


def _load_font(size: int) -> ImageFont.ImageFont:
    candidates = [
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/consola.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except (OSError, IOError):
            pass
    return ImageFont.load_default()


__all__ = [
    "MAX_TILES_PER_SHEET",
    "render_recommendation_contact_sheet",
    "write_recommendation_contact_sheets",
]
