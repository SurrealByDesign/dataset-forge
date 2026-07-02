"""Internal DatasetContext construction helpers.

Shared by inspect and benchmark so both paths build context metadata and
measurement routing the same way.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from pathlib import Path

from dataset_forge.analysis.metrics import extract_image_metrics
from dataset_forge.analyzers.registry import analyzer_versions
from dataset_forge.context import (
    CONTEXT_SCHEMA_VERSION,
    AspectRatioStats,
    DatasetContext,
    FrequencyDistributions,
    ResolutionStats,
    TextureDistributions,
)
from dataset_forge.measurements import ImageMeasurements, measure_image


@dataclass(frozen=True)
class ContextBuildResult:
    context: DatasetContext
    image_scores: dict[str, dict]
    measurements_by_path: dict[Path, ImageMeasurements]


def build_dataset_context(image_paths: list[Path]) -> ContextBuildResult:
    """Measure images and assemble the shared DatasetContext payload."""
    widths: list[int] = []
    heights: list[int] = []
    aspects: list[float] = []
    microtextures: list[float] = []
    file_hashes: dict[str, list[Path]] = {}
    image_scores: dict[str, dict] = {}
    measurements_by_path: dict[Path, ImageMeasurements] = {}
    error_count = 0

    for path in image_paths:
        measurements = measure_image(path)
        measurements_by_path[path] = measurements

        try:
            metrics = extract_image_metrics(path)
            widths.append(metrics.width)
            heights.append(metrics.height)
            aspects.append(metrics.aspect_ratio)
            file_hashes.setdefault(metrics.file_hash, []).append(path)
        except Exception:
            error_count += 1
            continue

        texture = measurements.texture
        if texture.status == "analyzed":
            microtextures.append(texture.microtexture_density_score)
            image_scores[str(path)] = {
                "microtexture_density": texture.microtexture_density_score,
                "watercolor_smoothness": texture.watercolor_smoothness_score,
                "highlight_speck": texture.highlight_speck_score,
            }
        else:
            image_scores[str(path)] = {"error": texture.error}

    if widths:
        resolution_stats = ResolutionStats(
            mean_w=statistics.mean(widths),
            mean_h=statistics.mean(heights),
            stddev_w=statistics.pstdev(widths),
            stddev_h=statistics.pstdev(heights),
            min_w=min(widths),
            min_h=min(heights),
            max_w=max(widths),
            max_h=max(heights),
            sample_count=len(widths),
        )
        aspect_ratio_stats = AspectRatioStats(
            mean=statistics.mean(aspects),
            stddev=statistics.pstdev(aspects),
            min=min(aspects),
            max=max(aspects),
            sample_count=len(aspects),
        )
    else:
        resolution_stats = ResolutionStats.empty()
        aspect_ratio_stats = AspectRatioStats.empty()

    if microtextures:
        count = len(microtextures)
        sorted_microtextures = sorted(microtextures)
        texture_distributions = TextureDistributions(
            mean=statistics.mean(microtextures),
            stddev=statistics.pstdev(microtextures),
            p10=sorted_microtextures[max(0, int(math.floor(count * 0.10)))],
            p90=sorted_microtextures[min(count - 1, int(math.floor(count * 0.90)))],
            sample_count=count,
        )
    else:
        texture_distributions = TextureDistributions.empty()

    duplicate_groups = tuple(
        tuple(paths)
        for paths in file_hashes.values()
        if len(paths) > 1
    )

    context = DatasetContext(
        schema_version=CONTEXT_SCHEMA_VERSION,
        analyzer_versions=analyzer_versions(),
        image_paths=tuple(image_paths),
        image_count=len(image_paths),
        error_count=error_count,
        resolution_stats=resolution_stats,
        aspect_ratio_stats=aspect_ratio_stats,
        texture_distributions=texture_distributions,
        frequency_distributions=FrequencyDistributions.empty(),
        duplicate_hashes=frozenset(file_hashes.keys()),
        duplicate_groups=duplicate_groups,
    )
    return ContextBuildResult(
        context=context,
        image_scores=image_scores,
        measurements_by_path=measurements_by_path,
    )


__all__ = ["ContextBuildResult", "build_dataset_context"]
