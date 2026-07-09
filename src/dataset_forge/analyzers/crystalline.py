"""Crystalline faceting analyzer — detects angular micro-polygon shading.

Crystalline faceting is a distinct GPT image artifact where surfaces appear
carved from angular facets rather than painted or drawn. It is visually
different from elevated microtexture noise: the contamination is angular,
structured, and distributed uniformly across affected surfaces.

Calibration history:
  During v1 calibration (anthropomorph dataset, 100 images, decision review),
  eleven images were missed by TextureAnalyzer. Diagnostic investigation showed:
    - highlight_speck: Cohen's d = -0.01 vs clean population (no signal)
    - pencil_grain:    Cohen's d = +0.80 (large effect)
  The best diagnostic rule at that calibration point:
    pencil_grain_score >= 45
    AND watercolor_smoothness_score < 52
    AND microtexture_density_score >= 20

  Threshold derivation: pencil_grain >= 45 alone produces F1=0.450, FP=20/46.
  Adding the smoothness guard (< 52) cuts FP to 13/46 with the same recall,
  lifting F1 to 0.545. The microtexture floor (>= 20) excludes genuinely smooth
  images that scored slightly above the grain threshold by chance.

Severity calibration (grain-only model, post-focused-review):
  Review of 54 crystalline-flagged images against human labels shows that the
  single-tier MEDIUM assignment overstates severity. Grain-based tiers:
    grain >= 65 -> HIGH   (cryst-only: 100% precision in calibration set)
    grain >= 55 -> MEDIUM (cryst-only: 33% precision; often co-detected w/ texture)
    grain <  55 -> LOW    (cryst-only: 28% precision; weak or borderline signal)
  Still uncalibrated against synthetic benchmarks; reviewer-validated only.
  Detection thresholds must NOT change without new benchmark evidence.

Calibration status: UNCALIBRATED.
  No synthetic benchmark exists yet. Confidence is capped conservatively.
  Thresholds must NOT be tightened or loosened without new benchmark evidence.

Findings emitted:
  artifact.crystalline_faceting  — angular faceting pattern detected
  artifact.crystalline_faceting.error  — image could not be measured
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from dataset_forge.analysis.texture import evaluate_texture
from dataset_forge.analyzers.base import Analyzer
from dataset_forge.context import DatasetContext
from dataset_forge.finding import Finding, Severity

if TYPE_CHECKING:
    from dataset_forge.measurements import ImageMeasurements

# ---------------------------------------------------------------------------
# Calibration constants
# ---------------------------------------------------------------------------

# Conservative caps until a synthetic benchmark validates these thresholds.
_UNCALIBRATED_FP_RATE = 0.28          # ~13 FP / 46 clean at diagnostic point
_UNCALIBRATED_CONFIDENCE = 0.45       # low — first-pass, uncalibrated

# Detection rule thresholds (from diagnostic: best combined rule by F1).
# Do not change without new benchmark evidence.
_GRAIN_THRESHOLD = 45.0               # pencil_grain_score lower bound
_SMOOTHNESS_CEILING = 52.0            # watercolor_smoothness_score upper bound
_MICRO_FLOOR = 20.0                   # microtexture_density_score lower bound

# Severity tiers (grain-only model, post-focused-review calibration).
# Derived from reviewer-validated labels on 54 crystalline-flagged images.
# Do not change without new benchmark evidence.
_SEVERITY_MEDIUM_GRAIN = 55.0         # grain >= this → MEDIUM (else LOW)
_SEVERITY_HIGH_GRAIN   = 65.0         # grain >= this → HIGH

BENCHMARK_VERSION = "uncalibrated"


def _severity_for_grain(grain: float) -> "Severity":
    """Map pencil_grain_score to calibrated severity tier."""
    if grain >= _SEVERITY_HIGH_GRAIN:
        return Severity.HIGH
    if grain >= _SEVERITY_MEDIUM_GRAIN:
        return Severity.MEDIUM
    return Severity.LOW


class CrystallineFacetingAnalyzer(Analyzer):
    """Detects crystalline faceting / micro-polygon shading artifacts.

    Uses `evaluate_texture()` from `analysis/texture.py`. Does not duplicate
    any measurement logic. Emits a Finding when all three conditions hold:
      - pencil_grain_score >= 45      (primary signal, d=+0.80)
      - watercolor_smoothness < 52    (guard: genuine watercolor is smoother)
      - microtexture_density >= 20    (floor: excludes truly featureless images)

    This analyzer is independent of TextureAnalyzer. They may both emit
    findings for the same image — that is correct and expected.
    """

    @property
    def name(self) -> str:
        return "crystalline_faceting_analyzer"

    @property
    def version(self) -> str:
        return "v1"

    @property
    def supported_categories(self) -> tuple[str, ...]:
        return (
            "artifact.crystalline_faceting",
            "artifact.crystalline_faceting.error",
        )

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
                    category="artifact.crystalline_faceting.error",
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

        grain     = result.pencil_grain_score
        smoothness = result.watercolor_smoothness_score
        micro     = result.microtexture_density_score

        # Rule: all three guards must pass.
        # Each guard is documented separately so future calibration can adjust
        # them independently.
        if micro < _MICRO_FLOOR:
            # Image is too smooth to plausibly carry crystalline faceting.
            return []

        if smoothness >= _SMOOTHNESS_CEILING:
            # High watercolor smoothness indicates genuine painted surface,
            # not faceted geometry. Grain elevation here is natural pencil grain.
            return []

        if grain < _GRAIN_THRESHOLD:
            return []

        explanation = (
            f"Pencil-grain score {grain:.1f} (threshold {_GRAIN_THRESHOLD}) "
            f"with watercolor smoothness {smoothness:.1f} (ceiling {_SMOOTHNESS_CEILING}) "
            f"and microtexture {micro:.1f} (floor {_MICRO_FLOOR}) "
            f"resembles surface patterns Dataset Forge currently watches for. "
            f"Surfaces may appear carved from angular micro-polygons rather than "
            f"painted or drawn. This may indicate AI-like surface texture, "
            f"compression, or intentional illustration texture. Treat this as an "
            f"advisory review signal, not a calibrated defect diagnosis."
        )

        recommendation = (
            "Candidate for human review. Review manually before any dataset decision. "
            "Do not treat this as generic microtexture; the artifact family is different."
        )

        return [
            Finding(
                image_path=image_path,
                analyzer=self.analyzer_id,
                category="artifact.crystalline_faceting",
                severity=_severity_for_grain(grain),
                confidence=_UNCALIBRATED_CONFIDENCE,
                false_positive_rate=_UNCALIBRATED_FP_RATE,
                benchmark_version=BENCHMARK_VERSION,
                evidence={
                    "pencil_grain_score": grain,
                    "watercolor_smoothness_score": smoothness,
                    "microtexture_density_score": micro,
                    "grain_threshold": _GRAIN_THRESHOLD,
                    "smoothness_ceiling": _SMOOTHNESS_CEILING,
                    "micro_floor": _MICRO_FLOOR,
                    "severity_medium_grain": _SEVERITY_MEDIUM_GRAIN,
                    "severity_high_grain": _SEVERITY_HIGH_GRAIN,
                    "calibrated": False,
                },
                explanation=explanation,
                recommendation=recommendation,
            )
        ]
