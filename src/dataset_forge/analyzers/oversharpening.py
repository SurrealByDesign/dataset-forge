"""Oversharpening / halo analyzer.

Detects edge-localized unsharp-mask residuals: artificial bright/dark bands
immediately around edges. This intentionally does not reuse the earlier
halo/ringing research metrics as primary signals; those were shown to confuse
clean hard outlines with artifacts.

Calibration status: UNCALIBRATED.
Synthetic fixtures validate the rule shape, but real-world precision/recall
are not established. Confidence is capped at 0.45 and findings remain
candidates for human review.

Findings emitted:
  artifact.oversharpening_halo        -- edge-localized USM residual detected
  artifact.oversharpening_halo.error  -- image could not be measured
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

from dataset_forge.analysis.texture import ANALYSIS_MAX_SIZE
from dataset_forge.analyzers.base import Analyzer
from dataset_forge.context import DatasetContext
from dataset_forge.finding import Finding, Severity

BENCHMARK_VERSION = "uncalibrated"

_UNCALIBRATED_FP_RATE = 0.35
_UNCALIBRATED_MAX_CONFIDENCE = 0.45

_SIGMA_BASELINE = 2.0
_MIN_EDGE_DENSITY = 0.004
_MAX_EDGE_DENSITY = 0.18
_LOW_EDGE_RESIDUAL_MEAN = 35.0
_LOW_EDGE_RESIDUAL_P95 = 70.0
_LOW_RESIDUAL_RATIO = 6.0
_MEDIUM_EDGE_RESIDUAL_MEAN = 40.0
_MEDIUM_EDGE_RESIDUAL_P95 = 90.0
_MEDIUM_RESIDUAL_RATIO = 8.0


@dataclass(frozen=True)
class USMResidualResult:
    status: str
    error: str = ""
    edge_residual_mean: float = 0.0
    non_edge_residual_mean: float = 0.0
    edge_residual_ratio: float = 0.0
    edge_residual_p95: float = 0.0
    residual_p95: float = 0.0
    edge_density: float = 0.0


def measure_usm_residual(path: Path) -> USMResidualResult:
    """Measure edge-localized unsharp-mask residuals without modifying image data."""
    resolved = path.expanduser().resolve()
    try:
        with Image.open(resolved) as opened:
            image = ImageOps.exif_transpose(opened).convert("RGB")
            image.thumbnail(
                (ANALYSIS_MAX_SIZE, ANALYSIS_MAX_SIZE),
                Image.Resampling.LANCZOS,
            )
            rgb = np.asarray(image, dtype=np.uint8)
    except (OSError, ValueError) as exc:
        return USMResidualResult(status="error", error=str(exc))

    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32)
    if min(gray.shape) < 8:
        return USMResidualResult(
            status="error",
            error="Image is too small for oversharpening analysis.",
        )

    blurred_for_edges = cv2.GaussianBlur(gray, (0, 0), 1.0)
    edges = cv2.Canny(
        np.clip(blurred_for_edges, 0, 255).astype(np.uint8),
        threshold1=40,
        threshold2=120,
    ) > 0
    edge_density = float(np.mean(edges))

    if not np.any(edges):
        return USMResidualResult(status="analyzed", edge_density=0.0)

    residual = np.abs(gray - cv2.GaussianBlur(gray, (0, 0), _SIGMA_BASELINE))

    edge_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    exclusion_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    edge_zone = cv2.dilate(edges.astype(np.uint8), edge_kernel) > 0
    non_edge_zone = ~(cv2.dilate(edges.astype(np.uint8), exclusion_kernel) > 0)

    edge_values = residual[edge_zone]
    non_edge_values = residual[non_edge_zone]

    edge_residual_mean = float(np.mean(edge_values)) if edge_values.size else 0.0
    non_edge_residual_mean = (
        float(np.mean(non_edge_values)) if non_edge_values.size else 0.0
    )
    edge_residual_ratio = edge_residual_mean / max(non_edge_residual_mean, 0.25)
    edge_residual_p95 = (
        float(np.percentile(edge_values, 95)) if edge_values.size else 0.0
    )
    residual_p95 = float(np.percentile(residual, 95))

    return USMResidualResult(
        status="analyzed",
        edge_residual_mean=round(edge_residual_mean, 4),
        non_edge_residual_mean=round(non_edge_residual_mean, 4),
        edge_residual_ratio=round(edge_residual_ratio, 4),
        edge_residual_p95=round(edge_residual_p95, 4),
        residual_p95=round(residual_p95, 4),
        edge_density=round(edge_density, 6),
    )


def _severity_for(result: USMResidualResult) -> Severity:
    if (
        result.edge_residual_mean >= _MEDIUM_EDGE_RESIDUAL_MEAN
        and result.edge_residual_p95 >= _MEDIUM_EDGE_RESIDUAL_P95
        and result.edge_residual_ratio >= _MEDIUM_RESIDUAL_RATIO
    ):
        return Severity.MEDIUM
    return Severity.LOW


def _passes_detection(result: USMResidualResult) -> bool:
    if result.status != "analyzed":
        return False
    if not (_MIN_EDGE_DENSITY <= result.edge_density <= _MAX_EDGE_DENSITY):
        return False
    return (
        result.edge_residual_mean >= _LOW_EDGE_RESIDUAL_MEAN
        and result.edge_residual_p95 >= _LOW_EDGE_RESIDUAL_P95
        and result.edge_residual_ratio >= _LOW_RESIDUAL_RATIO
    )


def _confidence_for(result: USMResidualResult, severity: Severity) -> float:
    if severity >= Severity.MEDIUM:
        raw = 0.35 + min(0.10, (result.edge_residual_p95 - _MEDIUM_EDGE_RESIDUAL_P95) / 400)
    else:
        raw = 0.25 + min(0.10, (result.edge_residual_p95 - _LOW_EDGE_RESIDUAL_P95) / 300)
    return round(min(raw, _UNCALIBRATED_MAX_CONFIDENCE), 4)


class OversharpeningHaloAnalyzer(Analyzer):
    """Detect edge-localized USM residuals consistent with oversharpening/halos."""

    @property
    def name(self) -> str:
        return "oversharpening_halo_analyzer"

    @property
    def version(self) -> str:
        return "v1"

    @property
    def supported_categories(self) -> tuple[str, ...]:
        return (
            "artifact.oversharpening_halo",
            "artifact.oversharpening_halo.error",
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
        result = measure_usm_residual(image_path)

        if result.status == "error":
            return [
                Finding(
                    image_path=image_path,
                    analyzer=self.analyzer_id,
                    category="artifact.oversharpening_halo.error",
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
            f"USM residuals near edges are elevated: edge residual mean "
            f"{result.edge_residual_mean:.1f}, 95th percentile "
            f"{result.edge_residual_p95:.1f}, and edge/non-edge ratio "
            f"{result.edge_residual_ratio:.1f}. This pattern is consistent "
            f"with artificial oversharpening or halo bands around edges."
        )
        recommendation = (
            "Candidate for human review as an oversharpening/halo artifact. "
            "Do not modify the image automatically; leave it alone if the edge "
            "crispness is stylistically intentional."
        )

        return [
            Finding(
                image_path=image_path,
                analyzer=self.analyzer_id,
                category="artifact.oversharpening_halo",
                severity=severity,
                confidence=confidence,
                false_positive_rate=_UNCALIBRATED_FP_RATE,
                benchmark_version=BENCHMARK_VERSION,
                evidence={
                    "edge_residual_mean": result.edge_residual_mean,
                    "non_edge_residual_mean": result.non_edge_residual_mean,
                    "edge_residual_ratio": result.edge_residual_ratio,
                    "edge_residual_p95": result.edge_residual_p95,
                    "residual_p95": result.residual_p95,
                    "edge_density": result.edge_density,
                    "sigma_baseline": _SIGMA_BASELINE,
                    "low_edge_residual_mean": _LOW_EDGE_RESIDUAL_MEAN,
                    "low_edge_residual_p95": _LOW_EDGE_RESIDUAL_P95,
                    "low_residual_ratio": _LOW_RESIDUAL_RATIO,
                    "medium_edge_residual_mean": _MEDIUM_EDGE_RESIDUAL_MEAN,
                    "medium_edge_residual_p95": _MEDIUM_EDGE_RESIDUAL_P95,
                    "medium_residual_ratio": _MEDIUM_RESIDUAL_RATIO,
                    "calibrated": False,
                },
                explanation=explanation,
                recommendation=recommendation,
            )
        ]
