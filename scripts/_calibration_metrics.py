"""Shared measurement helpers for calibration scripts."""

from __future__ import annotations

from pathlib import Path

from dataset_forge.measurements import measure_image

METRICS = [
    ("microtexture_density_score", "Microtexture density"),
    ("local_contrast_score", "Local contrast"),
    ("edge_sharpness_score", "Edge sharpness"),
    ("highlight_speck_score", "Highlight speck"),
    ("texture_consistency_score", "Texture consistency"),
    ("watercolor_smoothness_score", "Watercolor smoothness"),
    ("pencil_grain_score", "Pencil grain"),
]


def measure_texture(path: Path):
    """Return the texture measurement for one image."""
    return measure_image(path).texture


def texture_score_row(path: Path) -> dict | None:
    """Return a calibration score row for one image, or None on measurement error."""
    tex = measure_texture(path)
    if tex.status != "analyzed":
        return None
    return {
        "filename": path.name,
        **{key: getattr(tex, key) for key, _ in METRICS},
    }


def collect_texture_scores(paths: list[Path]) -> list[dict]:
    """Return calibration score rows for successfully measured images."""
    results = []
    for path in paths:
        row = texture_score_row(path)
        if row is not None:
            results.append(row)
    return results
