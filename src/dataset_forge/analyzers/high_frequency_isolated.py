"""High-frequency isolated artifact analyzer.

Detects small, isolated high-frequency residual components such as sparse
bright or dark specks. This analyzer is intentionally narrow: distributed
texture belongs to TextureAnalyzer, edge-localized halos belong to
OversharpeningHaloAnalyzer, and crystalline faceting belongs to
CrystallineFacetingAnalyzer.

Calibration status: UNCALIBRATED.
Synthetic fixtures validate the rule shape, but real-world precision/recall
are not established. Confidence is capped at 0.45 and findings remain
candidates for human review.

Findings emitted:
  artifact.high_frequency_isolated        -- sparse isolated artifact detected
  artifact.high_frequency_isolated.error  -- image could not be measured
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from dataset_forge.analysis.texture import ANALYSIS_MAX_SIZE
from dataset_forge.analyzers.base import Analyzer
from dataset_forge.context import DatasetContext
from dataset_forge.finding import Finding, Severity
from dataset_forge.image_primitives import (
    canny_edge_mask,
    dilated_mask,
    gaussian_blur,
    load_rgb_thumbnail,
    rgb_to_gray_float32,
    signed_residual,
)

BENCHMARK_VERSION = "uncalibrated"

_UNCALIBRATED_FP_RATE = 0.40
_UNCALIBRATED_MAX_CONFIDENCE = 0.45

_RESIDUAL_SIGMA = 1.2
_RESIDUAL_ABSOLUTE_FLOOR = 26.0
_MIN_COMPONENT_AREA_PX = 1
_MAX_COMPONENT_AREA_PX = 9
_MIN_COMPONENT_COUNT = 8
_LOW_DENSITY_PER_MEGAPIXEL = 60.0
_MEDIUM_DENSITY_PER_MEGAPIXEL = 140.0
_MAX_TEXTURE_FIELD_DENSITY = 0.035
_MAX_EDGE_ADJACENT_RATIO = 0.35
_MIN_ISOLATION_SCORE = 0.55
_CHROMA_OUTLIER_THRESHOLD = 24.0
_MIN_MEDIAN_COMPONENT_RESIDUAL = 45.0
_MIN_P95_COMPONENT_RESIDUAL = 55.0


@dataclass(frozen=True)
class IsolatedArtifactResult:
    status: str
    error: str = ""
    isolated_component_count: int = 0
    component_density_per_megapixel: float = 0.0
    mean_component_area_px: float = 0.0
    observed_max_component_area_px: int = 0
    median_component_residual: float = 0.0
    p95_component_residual: float = 0.0
    bright_component_ratio: float = 0.0
    dark_component_ratio: float = 0.0
    chroma_outlier_ratio: float = 0.0
    edge_adjacent_component_ratio: float = 0.0
    texture_field_density: float = 0.0
    isolation_score: float = 0.0
    residual_threshold: float = 0.0
    min_component_area_threshold_px: int = _MIN_COMPONENT_AREA_PX
    max_component_area_threshold_px: int = _MAX_COMPONENT_AREA_PX


def _load_rgb(path: Path) -> np.ndarray | str:
    resolved = path.expanduser().resolve()
    try:
        return load_rgb_thumbnail(resolved, ANALYSIS_MAX_SIZE)
    except (OSError, ValueError) as exc:
        return str(exc)


def measure_isolated_artifacts(path: Path) -> IsolatedArtifactResult:
    """Measure sparse high-frequency residual components without modifying files."""
    rgb_or_error = _load_rgb(path)
    if isinstance(rgb_or_error, str):
        return IsolatedArtifactResult(status="error", error=rgb_or_error)

    rgb = rgb_or_error
    if min(rgb.shape[:2]) < 16:
        return IsolatedArtifactResult(
            status="error",
            error="Image is too small for isolated artifact analysis.",
        )

    gray = rgb_to_gray_float32(rgb)
    gray_signed_residual = signed_residual(gray, _RESIDUAL_SIGMA)
    residual = np.abs(gray_signed_residual)

    median = float(np.median(residual))
    mad = float(np.median(np.abs(residual - median)))
    residual_threshold = max(_RESIDUAL_ABSOLUTE_FLOOR, median + 6.0 * mad)

    residual_mask = residual >= residual_threshold
    texture_field_density = float(np.mean(residual_mask))

    edge_zone = dilated_mask(
        canny_edge_mask(gray, blur_sigma=1.0, threshold1=40, threshold2=120),
        7,
    )

    labels_count, labels, stats, _ = cv2.connectedComponentsWithStats(
        residual_mask.astype(np.uint8),
        connectivity=8,
    )

    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    a = lab[:, :, 1]
    b = lab[:, :, 2]
    a_base = gaussian_blur(a, _RESIDUAL_SIGMA)
    b_base = gaussian_blur(b, _RESIDUAL_SIGMA)
    chroma_residual = np.sqrt((a - a_base) ** 2 + (b - b_base) ** 2)

    areas: list[int] = []
    component_residuals: list[float] = []
    bright_count = 0
    dark_count = 0
    chroma_count = 0
    edge_adjacent_count = 0

    for label in range(1, labels_count):
        area = int(stats[label, cv2.CC_STAT_AREA])
        if not (_MIN_COMPONENT_AREA_PX <= area <= _MAX_COMPONENT_AREA_PX):
            continue

        component = labels == label
        # Very close neighboring pixels merge into a component; a second dilation
        # check keeps this analyzer focused on isolated debris rather than fields.
        dilated = cv2.dilate(
            component.astype(np.uint8),
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)),
        ) > 0
        nearby_labels = set(np.unique(labels[dilated]))
        nearby_labels.discard(0)
        nearby_labels.discard(label)
        if nearby_labels:
            continue

        values = residual[component]
        signed_values = gray_signed_residual[component]
        chroma_values = chroma_residual[component]
        areas.append(area)
        component_residuals.append(float(np.median(values)))
        if float(np.median(signed_values)) > 0:
            bright_count += 1
        else:
            dark_count += 1
        if float(np.percentile(chroma_values, 95)) >= _CHROMA_OUTLIER_THRESHOLD:
            chroma_count += 1
        if np.any(edge_zone[component]):
            edge_adjacent_count += 1

    count = len(areas)
    pixel_count = int(gray.shape[0] * gray.shape[1])
    density = (count / max(pixel_count, 1)) * 1_000_000.0

    if count:
        mean_area = float(np.mean(areas))
        max_area = int(max(areas))
        median_component_residual = float(np.median(component_residuals))
        p95_component_residual = float(np.percentile(component_residuals, 95))
        bright_ratio = bright_count / count
        dark_ratio = dark_count / count
        chroma_ratio = chroma_count / count
        edge_ratio = edge_adjacent_count / count
    else:
        mean_area = 0.0
        max_area = 0
        median_component_residual = 0.0
        p95_component_residual = 0.0
        bright_ratio = 0.0
        dark_ratio = 0.0
        chroma_ratio = 0.0
        edge_ratio = 0.0

    texture_penalty = min(1.0, texture_field_density / _MAX_TEXTURE_FIELD_DENSITY)
    isolation_score = 1.0 - max(edge_ratio, texture_penalty * 0.5)

    return IsolatedArtifactResult(
        status="analyzed",
        isolated_component_count=count,
        component_density_per_megapixel=round(density, 4),
        mean_component_area_px=round(mean_area, 4),
        observed_max_component_area_px=max_area,
        median_component_residual=round(median_component_residual, 4),
        p95_component_residual=round(p95_component_residual, 4),
        bright_component_ratio=round(bright_ratio, 4),
        dark_component_ratio=round(dark_ratio, 4),
        chroma_outlier_ratio=round(chroma_ratio, 4),
        edge_adjacent_component_ratio=round(edge_ratio, 4),
        texture_field_density=round(texture_field_density, 6),
        isolation_score=round(isolation_score, 4),
        residual_threshold=round(residual_threshold, 4),
        min_component_area_threshold_px=_MIN_COMPONENT_AREA_PX,
        max_component_area_threshold_px=_MAX_COMPONENT_AREA_PX,
    )


def _passes_detection(result: IsolatedArtifactResult) -> bool:
    if result.status != "analyzed":
        return False
    if result.isolated_component_count < _MIN_COMPONENT_COUNT:
        return False
    if result.component_density_per_megapixel < _LOW_DENSITY_PER_MEGAPIXEL:
        return False
    if result.median_component_residual < _MIN_MEDIAN_COMPONENT_RESIDUAL:
        return False
    if result.p95_component_residual < _MIN_P95_COMPONENT_RESIDUAL:
        return False
    if result.texture_field_density > _MAX_TEXTURE_FIELD_DENSITY:
        return False
    if result.edge_adjacent_component_ratio > _MAX_EDGE_ADJACENT_RATIO:
        return False
    return result.isolation_score >= _MIN_ISOLATION_SCORE


def _severity_for(result: IsolatedArtifactResult) -> Severity:
    if result.component_density_per_megapixel >= _MEDIUM_DENSITY_PER_MEGAPIXEL:
        return Severity.MEDIUM
    return Severity.LOW


def _confidence_for(result: IsolatedArtifactResult, severity: Severity) -> float:
    if severity >= Severity.MEDIUM:
        raw = 0.34 + min(0.08, result.isolation_score * 0.08)
    else:
        raw = 0.26 + min(0.08, result.isolation_score * 0.08)
    return round(min(raw, _UNCALIBRATED_MAX_CONFIDENCE), 4)


class HighFrequencyIsolatedArtifactAnalyzer(Analyzer):
    """Detect sparse isolated high-frequency artifacts."""

    @property
    def name(self) -> str:
        return "high_frequency_isolated_artifact_analyzer"

    @property
    def version(self) -> str:
        return "v1"

    @property
    def supported_categories(self) -> tuple[str, ...]:
        return (
            "artifact.high_frequency_isolated",
            "artifact.high_frequency_isolated.error",
        )

    @property
    def benchmark_version(self) -> str | None:
        return None

    def analyze(
        self,
        image_path: Path,
        context: DatasetContext,
        measurements=None,
    ) -> list[Finding]:
        del context, measurements
        result = measure_isolated_artifacts(image_path)

        if result.status == "error":
            return [
                Finding(
                    image_path=image_path,
                    analyzer=self.analyzer_id,
                    category="artifact.high_frequency_isolated.error",
                    severity=Severity.LOW,
                    confidence=1.0,
                    false_positive_rate=0.0,
                    benchmark_version=BENCHMARK_VERSION,
                    evidence={"error": result.error},
                    explanation=f"Image could not be measured: {result.error}",
                    recommendation=(
                        "Verify the file is a valid image. "
                        "If so, inspect manually."
                    ),
                )
            ]

        if not _passes_detection(result):
            return []

        severity = _severity_for(result)
        confidence = _confidence_for(result, severity)
        explanation = (
            f"Detected {result.isolated_component_count} small isolated "
            f"high-frequency residual components "
            f"({result.component_density_per_megapixel:.1f} per megapixel). "
            f"The median component residual is "
            f"{result.median_component_residual:.1f}, with edge-adjacent "
            f"ratio {result.edge_adjacent_component_ratio:.2f} and texture "
            f"field density {result.texture_field_density:.4f}. This pattern "
            f"is consistent with sparse isolated speck artifacts rather than "
            f"distributed texture or edge halos."
        )
        recommendation = (
            "Candidate for human review as sparse isolated high-frequency "
            "artifacts. Leave the image alone if these marks are intentional "
            "highlights, freckles, stars, grain, or decorative details."
        )

        return [
            Finding(
                image_path=image_path,
                analyzer=self.analyzer_id,
                category="artifact.high_frequency_isolated",
                severity=severity,
                confidence=confidence,
                false_positive_rate=_UNCALIBRATED_FP_RATE,
                benchmark_version=BENCHMARK_VERSION,
                evidence={
                    "isolated_component_count": result.isolated_component_count,
                    "component_density_per_megapixel": result.component_density_per_megapixel,
                    "mean_component_area_px": result.mean_component_area_px,
                    "observed_max_component_area_px": (
                        result.observed_max_component_area_px
                    ),
                    "median_component_residual": result.median_component_residual,
                    "p95_component_residual": result.p95_component_residual,
                    "bright_component_ratio": result.bright_component_ratio,
                    "dark_component_ratio": result.dark_component_ratio,
                    "chroma_outlier_ratio": result.chroma_outlier_ratio,
                    "edge_adjacent_component_ratio": result.edge_adjacent_component_ratio,
                    "texture_field_density": result.texture_field_density,
                    "isolation_score": result.isolation_score,
                    "residual_threshold": result.residual_threshold,
                    "min_component_area_threshold_px": (
                        result.min_component_area_threshold_px
                    ),
                    "max_component_area_threshold_px": (
                        result.max_component_area_threshold_px
                    ),
                    "calibrated": False,
                },
                explanation=explanation,
                recommendation=recommendation,
            )
        ]
