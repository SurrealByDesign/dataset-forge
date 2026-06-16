"""DatasetContext — statistical reference frame for Dataset Forge analyzers.

Built once per inspection run before any analyzer executes.
Read-only during analysis. Analyzers consume it; they do not modify it.

Design rule: every field here must have an immediate consumer in the v1
analyzer pipeline. Do not add speculative fields.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CONTEXT_SCHEMA = "dataset-forge/context/v1"
CONTEXT_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ResolutionStats:
    """Width and height statistics across all successfully measured images."""

    # Separate width/height stats so analyzers can reason about each axis.
    mean_w: float
    mean_h: float
    stddev_w: float
    stddev_h: float
    min_w: int
    min_h: int
    max_w: int
    max_h: int
    sample_count: int  # images that contributed (errors excluded)

    def __post_init__(self) -> None:
        if self.sample_count < 0:
            raise ValueError("sample_count must be >= 0")
        for name, val in [("mean_w", self.mean_w), ("mean_h", self.mean_h)]:
            if val < 0:
                raise ValueError(f"{name} must be >= 0")

    def to_dict(self) -> dict[str, Any]:
        return {
            "mean_w": self.mean_w,
            "mean_h": self.mean_h,
            "stddev_w": self.stddev_w,
            "stddev_h": self.stddev_h,
            "min_w": self.min_w,
            "min_h": self.min_h,
            "max_w": self.max_w,
            "max_h": self.max_h,
            "sample_count": self.sample_count,
        }

    @staticmethod
    def empty() -> ResolutionStats:
        return ResolutionStats(
            mean_w=0.0, mean_h=0.0,
            stddev_w=0.0, stddev_h=0.0,
            min_w=0, min_h=0,
            max_w=0, max_h=0,
            sample_count=0,
        )


@dataclass(frozen=True)
class AspectRatioStats:
    """Aspect ratio (width/height) statistics across the dataset.

    Analyzers use this to flag images that are outliers relative to the
    dataset norm — useful for detecting miscropped or wrongly-oriented images.
    """

    mean: float         # mean w/h ratio
    stddev: float
    min: float
    max: float
    sample_count: int

    def __post_init__(self) -> None:
        if self.sample_count < 0:
            raise ValueError("sample_count must be >= 0")

    def to_dict(self) -> dict[str, Any]:
        return {
            "mean": self.mean,
            "stddev": self.stddev,
            "min": self.min,
            "max": self.max,
            "sample_count": self.sample_count,
        }

    @staticmethod
    def empty() -> AspectRatioStats:
        return AspectRatioStats(mean=0.0, stddev=0.0, min=0.0, max=0.0, sample_count=0)


@dataclass(frozen=True)
class TextureDistributions:
    """Dataset-level microtexture density statistics.

    Microtexture density measures high-frequency energy at ~1px scale.
    These statistics let texture analyzers judge whether an individual
    image's score is anomalous relative to the dataset, not just in
    absolute terms.

    p10 / p90 are the 10th and 90th percentile values. They give a
    robust sense of the dataset's normal range without being thrown off
    by outliers at either tail.
    """

    mean: float
    stddev: float
    p10: float   # 10th percentile — lower bound of normal range
    p90: float   # 90th percentile — upper bound of normal range
    sample_count: int

    def __post_init__(self) -> None:
        if self.sample_count < 0:
            raise ValueError("sample_count must be >= 0")

    def to_dict(self) -> dict[str, Any]:
        return {
            "mean": self.mean,
            "stddev": self.stddev,
            "p10": self.p10,
            "p90": self.p90,
            "sample_count": self.sample_count,
        }

    @staticmethod
    def empty() -> TextureDistributions:
        return TextureDistributions(mean=0.0, stddev=0.0, p10=0.0, p90=0.0, sample_count=0)


@dataclass(frozen=True)
class FrequencyDistributions:
    """Dataset-level periodic frequency statistics.

    Periodic noise (crystalline microtexture, GPT glitter, moiré-like
    patterns) shows up as anomalous peaks in the frequency domain.
    These baseline statistics let the frequency analyzer distinguish
    genuine artifacts from the dataset's natural frequency content.

    dominant_freq_mean: mean of each image's strongest non-DC frequency peak
    dominant_freq_stddev: spread of that peak across the dataset
    sample_count: images that contributed a valid frequency measurement
    """

    dominant_freq_mean: float
    dominant_freq_stddev: float
    sample_count: int

    def __post_init__(self) -> None:
        if self.sample_count < 0:
            raise ValueError("sample_count must be >= 0")

    def to_dict(self) -> dict[str, Any]:
        return {
            "dominant_freq_mean": self.dominant_freq_mean,
            "dominant_freq_stddev": self.dominant_freq_stddev,
            "sample_count": self.sample_count,
        }

    @staticmethod
    def empty() -> FrequencyDistributions:
        return FrequencyDistributions(
            dominant_freq_mean=0.0, dominant_freq_stddev=0.0, sample_count=0
        )


@dataclass(frozen=True)
class DatasetContext:
    """Statistical reference frame for a single inspection run.

    Built once before any analyzer runs. All fields are read-only.
    Analyzers consume this object to make dataset-relative findings;
    they never write to it.

    Design constraint: every field must have an immediate consumer in the
    v1 analyzer pipeline. Speculative fields belong in a future version.
    """

    # Identifies the schema and version of this context object.
    # Increment CONTEXT_SCHEMA_VERSION when the shape of this dataclass changes.
    schema_version: int

    # Maps analyzer name → version string.
    # Lets reports record exactly which analyzer versions produced the findings,
    # so results are reproducible and comparable across runs.
    analyzer_versions: dict[str, str]

    # Ordered list of all image paths discovered in the dataset directory.
    # Analyzers iterate this; the report uses it for per-image sections.
    image_paths: tuple[Path, ...]

    # Total images found (including any that could not be read).
    # Distinct from len(image_paths) only if discovery filtering is applied.
    image_count: int

    # Number of images that could not be opened or measured.
    # Reported in the summary; used to qualify statistics.
    error_count: int

    # Width/height statistics from successfully measured images.
    resolution_stats: ResolutionStats

    # Aspect ratio (w/h) distribution.
    aspect_ratio_stats: AspectRatioStats

    # Microtexture density distribution — baseline for texture analyzers.
    texture_distributions: TextureDistributions

    # Periodic frequency distribution — baseline for frequency/glitter analyzers.
    frequency_distributions: FrequencyDistributions

    # SHA-256 hashes of all images. Used by analyzers to flag exact duplicates.
    # Stored as a frozenset so DatasetContext remains hashable.
    duplicate_hashes: frozenset[str]

    # Image paths grouped by hash — only entries with >1 path are duplicates.
    # Stored as a tuple of tuples so the context stays frozen/hashable.
    duplicate_groups: tuple[tuple[Path, ...], ...]

    def __post_init__(self) -> None:
        if self.schema_version != CONTEXT_SCHEMA_VERSION:
            raise ValueError(
                f"schema_version must be {CONTEXT_SCHEMA_VERSION}, got {self.schema_version}"
            )
        if self.image_count < 0:
            raise ValueError("image_count must be >= 0")
        if self.error_count < 0:
            raise ValueError("error_count must be >= 0")

    # ------------------------------------------------------------------
    # Derived properties — computed from stored data, never stored twice
    # ------------------------------------------------------------------

    @property
    def analyzed_count(self) -> int:
        """Images successfully measured (image_count minus errors)."""
        return self.image_count - self.error_count

    @property
    def exact_duplicate_count(self) -> int:
        """Number of images that are exact duplicates of another image."""
        return sum(len(g) - 1 for g in self.duplicate_groups)

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": CONTEXT_SCHEMA,
            "schema_version": self.schema_version,
            "analyzer_versions": dict(self.analyzer_versions),
            "image_count": self.image_count,
            "error_count": self.error_count,
            "analyzed_count": self.analyzed_count,
            "exact_duplicate_count": self.exact_duplicate_count,
            "resolution_stats": self.resolution_stats.to_dict(),
            "aspect_ratio_stats": self.aspect_ratio_stats.to_dict(),
            "texture_distributions": self.texture_distributions.to_dict(),
            "frequency_distributions": self.frequency_distributions.to_dict(),
            "duplicate_groups": [
                [str(p) for p in group] for group in self.duplicate_groups
            ],
        }

    # ------------------------------------------------------------------
    # Factory helpers
    # ------------------------------------------------------------------

    @staticmethod
    def empty(image_paths: list[Path] | None = None) -> DatasetContext:
        """Return an empty context — useful for tests and dry runs."""
        paths = tuple(image_paths or [])
        return DatasetContext(
            schema_version=CONTEXT_SCHEMA_VERSION,
            analyzer_versions={},
            image_paths=paths,
            image_count=len(paths),
            error_count=0,
            resolution_stats=ResolutionStats.empty(),
            aspect_ratio_stats=AspectRatioStats.empty(),
            texture_distributions=TextureDistributions.empty(),
            frequency_distributions=FrequencyDistributions.empty(),
            duplicate_hashes=frozenset(),
            duplicate_groups=(),
        )
