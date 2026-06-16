"""Versioned, extensible evidence shared by all analysis modules."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

EVIDENCE_SCHEMA = "dataset-forge/evidence"
EVIDENCE_VERSION = 1


@dataclass
class ImageEvidence:
    """All analyzer observations for one image, without a decision."""

    image_id: str
    filename: str
    original_path: str
    status: str = "analyzed"
    error: str = ""
    quality_metrics: dict[str, Any] = field(default_factory=dict)
    artifact_metrics: dict[str, Any] = field(default_factory=dict)
    texture_metrics: dict[str, Any] = field(default_factory=dict)
    dataset_relative_metrics: dict[str, Any] = field(default_factory=dict)
    semantic_metrics: dict[str, Any] = field(default_factory=dict)
    benchmark_metrics: dict[str, Any] = field(default_factory=dict)
    extensions: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Evidence:
    """Dataset-level evidence envelope consumed by the recommendation engine."""

    schema: str = EVIDENCE_SCHEMA
    version: int = EVIDENCE_VERSION
    images: list[ImageEvidence] = field(default_factory=list)
    dataset_metrics: dict[str, Any] = field(default_factory=dict)
    semantic_metrics: dict[str, Any] = field(default_factory=dict)
    benchmark_metrics: dict[str, Any] = field(default_factory=dict)
    extensions: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "version": self.version,
            "images": [image.to_dict() for image in self.images],
            "dataset_metrics": self.dataset_metrics,
            "semantic_metrics": self.semantic_metrics,
            "benchmark_metrics": self.benchmark_metrics,
            "extensions": self.extensions,
        }

    def by_filename(self) -> dict[str, ImageEvidence]:
        return {image.filename: image for image in self.images}


def evidence_from_rows(rows: Iterable[Mapping[str, Any]]) -> Evidence:
    """Adapt existing manifest rows into the unified evidence schema."""
    images: list[ImageEvidence] = []
    for row in rows:
        filename = str(row.get("filename", ""))
        original_path = str(row.get("original_path", ""))
        file_hash = str(row.get("file_hash", "") or "")
        image_id = file_hash[:16] or filename or original_path
        images.append(
            ImageEvidence(
                image_id=image_id,
                filename=filename,
                original_path=original_path,
                status=str(row.get("status", "analyzed")),
                error=str(row.get("error", "") or ""),
                quality_metrics=_present(
                    row,
                    (
                        "overall_quality_score",
                        "resolution_score",
                        "brightness_consistency_score",
                        "contrast_score",
                        "megapixels",
                        "average_brightness",
                        "average_contrast",
                        "aspect_ratio",
                        "duplicate_risk",
                        "exact_duplicate_of",
                        "probable_duplicate_of",
                    ),
                ),
                artifact_metrics=_present(row, ("artifact_score",)),
                texture_metrics=_present(
                    row,
                    (
                        "texture_score",
                        "microtexture_density_score",
                        "local_contrast_score",
                        "edge_sharpness_score",
                        "highlight_speck_score",
                        "texture_consistency_score",
                        "watercolor_smoothness_score",
                        "pencil_grain_score",
                    ),
                ),
                dataset_relative_metrics=_present(
                    row,
                    (
                        "texture_delta_from_average",
                        "representative_score",
                        "cleanliness_score",
                    ),
                ),
                extensions={
                    "source": _present(
                        row,
                        ("file_size", "image_width", "image_height", "color_mode"),
                    )
                },
            )
        )
    return Evidence(images=images)


def write_evidence(path: Path, evidence: Evidence) -> None:
    path.write_text(
        json.dumps(evidence.to_dict(), indent=2) + "\n",
        encoding="utf-8",
    )


def _present(
    row: Mapping[str, Any],
    names: tuple[str, ...],
) -> dict[str, Any]:
    return {
        name: row[name]
        for name in names
        if name in row and row[name] not in ("", None)
    }


__all__ = [
    "EVIDENCE_SCHEMA",
    "EVIDENCE_VERSION",
    "Evidence",
    "ImageEvidence",
    "evidence_from_rows",
    "write_evidence",
]
