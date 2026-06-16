from __future__ import annotations

import csv
from pathlib import Path

MANIFEST_FIELDS = (
    "original_path",
    "filename",
    "extension",
    "file_size",
    "image_width",
    "image_height",
    "aspect_ratio",
    "megapixels",
    "color_mode",
    "average_brightness",
    "average_saturation",
    "average_contrast",
    "perceptual_hash",
    "file_hash",
    "texture_score",
    "artifact_score",
    "exact_duplicate_of",
    "probable_duplicate_of",
    "overall_quality_score",
    "duplicate_risk",
    "resolution_score",
    "brightness_consistency_score",
    "contrast_score",
    "status",
    "preset_name",
    "preset_description",
    "preset_source",
)


def empty_manifest_row() -> dict[str, object]:
    return {field: "" for field in MANIFEST_FIELDS}


def write_manifest(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

