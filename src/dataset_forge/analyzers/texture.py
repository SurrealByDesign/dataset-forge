"""Texture analyzer — detects GPT-style microtexture artifacts.

Wraps `analysis/texture.py`'s `evaluate_texture()` measurement function
in the standard Analyzer contract. Does not duplicate measurement logic.

Findings emitted:
  texture.high_microtexture   — image score is anomalously high relative
                                 to the dataset baseline (z-score driven)
  texture.error               — image could not be opened or measured

Calibration status: UNCALIBRATED.
Thresholds are derived from dataset-relative z-scores only.
A synthetic benchmark is required before findings should be treated as
fully calibrated evidence. Until then, confidence is capped at 0.70 and
false_positive_rate is reported conservatively at 0.15.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import TYPE_CHECKING

from dataset_forge.analysis.texture import evaluate_texture
from dataset_forge.analyzers.base import Analyzer
from dataset_forge.context import DatasetContext
from dataset_forge.finding import Finding, Severity

if TYPE_CHECKING:
    from dataset_forge.measurements import ImageMeasurements

# Calibration note: these values will tighten once a synthetic benchmark exists.
_UNCALIBRATED_FP_RATE = 0.15
_UNCALIBRATED_MAX_CONFIDENCE = 0.70

# Z-score thresholds — how many stddevs above the dataset mean triggers a finding.
# MEDIUM: noticeably above average.  HIGH: strong outlier.  CRITICAL: extreme.
_Z_MEDIUM = 1.0
_Z_HIGH = 2.0
_Z_CRITICAL = 3.0

# Absolute floor: images below this raw score never trigger even if the dataset
# average is very low. Prevents noise on nearly-clean datasets.
_ABSOLUTE_FLOOR = 15.0

BENCHMARK_VERSION = "uncalibrated"


def _z_to_severity(z: float) -> Severity:
    if z >= _Z_CRITICAL:
        return Severity.CRITICAL
    if z >= _Z_HIGH:
        return Severity.HIGH
    if z >= _Z_MEDIUM:
        return Severity.MEDIUM
    return Severity.NONE


def _z_to_confidence(z: float) -> float:
    """Map z-score to a [0, _UNCALIBRATED_MAX_CONFIDENCE] confidence value.

    Uses a sigmoid so confidence rises smoothly with z but is capped until
    a proper benchmark calibrates the thresholds.
    """
    raw = 1.0 / (1.0 + math.exp(-0.8 * (z - 1.5)))
    return round(min(raw, _UNCALIBRATED_MAX_CONFIDENCE), 4)


class TextureAnalyzer(Analyzer):
    """Detects anomalously high microtexture density relative to dataset baseline.

    Uses `evaluate_texture()` from `analysis/texture.py` for all pixel-level
    measurements. This class is responsible only for translating those
    measurements into calibrated (or acknowledged-uncalibrated) Findings.
    """

    @property
    def name(self) -> str:
        return "texture_analyzer"

    @property
    def version(self) -> str:
        return "v1"

    @property
    def supported_categories(self) -> tuple[str, ...]:
        return ("texture.high_microtexture", "texture.error")

    @property
    def benchmark_version(self) -> str | None:
        return None  # will be set once synthetic benchmark exists

    def analyze(
        self,
        image_path: Path,
        context: DatasetContext,
        measurements: ImageMeasurements | None = None,
    ) -> list[Finding]:
        result = (
            measurements.texture
            if measurements is not None
            else evaluate_texture(image_path)
        )

        if result.status == "error":
            return [
                Finding(
                    image_path=image_path,
                    analyzer=self.analyzer_id,
                    category="texture.error",
                    severity=Severity.LOW,
                    confidence=1.0,
                    false_positive_rate=0.0,
                    benchmark_version=BENCHMARK_VERSION,
                    evidence={"error": result.error},
                    explanation=f"Image could not be measured: {result.error}",
                    recommendation="Verify the file is a valid image. If so, investigate manually.",
                )
            ]

        dist = context.texture_distributions
        micro = result.microtexture_density_score

        # No dataset baseline available — emit nothing rather than guess.
        if dist.sample_count == 0 or dist.stddev == 0.0:
            return []

        # Below absolute floor — not a GPT microtexture candidate.
        if micro < _ABSOLUTE_FLOOR:
            return []

        z = (micro - dist.mean) / dist.stddev
        severity = _z_to_severity(z)

        if severity == Severity.NONE:
            return []

        confidence = _z_to_confidence(z)

        explanation = (
            f"Microtexture density {micro:.1f} is {z:.1f} standard deviations above "
            f"the dataset mean ({dist.mean:.1f} ± {dist.stddev:.1f}). "
            f"High microtexture density is a review signal Dataset Forge currently "
            f"watches for. It may indicate AI-like surface texture, compression, "
            f"natural grain, or intentional illustration texture."
        )

        if severity >= Severity.HIGH:
            recommendation = (
                "Strong candidate for human review. Do not modify the image "
                "if the texture is stylistically intentional."
            )
        else:
            recommendation = (
                "Mild microtexture elevation. Monitor in context of full dataset. "
                "Leave alone if the image otherwise looks correct."
            )

        return [
            Finding(
                image_path=image_path,
                analyzer=self.analyzer_id,
                category="texture.high_microtexture",
                severity=severity,
                confidence=confidence,
                false_positive_rate=_UNCALIBRATED_FP_RATE,
                benchmark_version=BENCHMARK_VERSION,
                evidence={
                    "microtexture_density": micro,
                    "dataset_mean": dist.mean,
                    "dataset_stddev": dist.stddev,
                    "z_score": round(z, 3),
                    "dataset_p10": dist.p10,
                    "dataset_p90": dist.p90,
                    "watercolor_smoothness": result.watercolor_smoothness_score,
                    "highlight_speck": result.highlight_speck_score,
                    "calibrated": False,
                },
                explanation=explanation,
                recommendation=recommendation,
            )
        ]
