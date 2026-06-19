"""Tests for CrystallineFacetingAnalyzer.

Uses synthetic PIL images written to a temporary directory.  Images are
constructed to produce known high / low pencil_grain and watercolor_smoothness
scores so the detection rule can be verified without hitting the real dataset.

Because `evaluate_texture` is pure pixel math we test through the real
implementation rather than mocking it. The image factories below are tuned
to produce scores that reliably land above or below each threshold.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
from PIL import Image

from dataset_forge.analyzers.crystalline import (
    CrystallineFacetingAnalyzer,
    _GRAIN_THRESHOLD,
    _MICRO_FLOOR,
    _SMOOTHNESS_CEILING,
    _SEVERITY_MEDIUM_GRAIN,
    _SEVERITY_HIGH_GRAIN,
    _UNCALIBRATED_CONFIDENCE,
    _UNCALIBRATED_FP_RATE,
    BENCHMARK_VERSION,
)
from dataset_forge.context import (
    CONTEXT_SCHEMA_VERSION,
    AspectRatioStats,
    DatasetContext,
    FrequencyDistributions,
    ResolutionStats,
    TextureDistributions,
)
from dataset_forge.finding import Finding, Severity
from dataset_forge.measurements import ImageMeasurements


# ---------------------------------------------------------------------------
# Image factories
# ---------------------------------------------------------------------------

def _write_smooth_image(path: Path) -> None:
    """Solid grey — near-zero microtexture and pencil grain, high smoothness."""
    arr = np.full((256, 256, 3), 128, dtype=np.uint8)
    Image.fromarray(arr).save(path)


def _write_noisy_uniform_image(path: Path, noise: int = 60) -> None:
    """Uniform random noise — high microtexture AND high pencil grain."""
    rng = np.random.default_rng(42)
    arr = rng.integers(128 - noise, 128 + noise, size=(256, 256, 3), dtype=np.uint8)
    Image.fromarray(arr).save(path)


def _write_high_smoothness_image(path: Path) -> None:
    """Gentle gradient — high watercolor smoothness, moderate grain."""
    arr = np.zeros((256, 256, 3), dtype=np.uint8)
    for i in range(256):
        arr[i, :, :] = i  # smooth vertical gradient
    Image.fromarray(arr).save(path)


# ---------------------------------------------------------------------------
# Context factory (minimal; CrystallineFacetingAnalyzer does not use context
# statistics — it operates on absolute thresholds, not dataset-relative z-scores)
# ---------------------------------------------------------------------------

def _ctx() -> DatasetContext:
    n = 50
    return DatasetContext(
        schema_version=CONTEXT_SCHEMA_VERSION,
        analyzer_versions={"crystalline_faceting_analyzer": "v1"},
        image_paths=(),
        image_count=n,
        error_count=0,
        resolution_stats=ResolutionStats(
            mean_w=512.0, mean_h=512.0, stddev_w=0.0, stddev_h=0.0,
            min_w=512, min_h=512, max_w=512, max_h=512, sample_count=n,
        ),
        aspect_ratio_stats=AspectRatioStats(
            mean=1.0, stddev=0.0, min=1.0, max=1.0, sample_count=n,
        ),
        texture_distributions=TextureDistributions(
            mean=38.0, stddev=12.0, p10=20.0, p90=58.0, sample_count=n,
        ),
        frequency_distributions=FrequencyDistributions(
            dominant_freq_mean=0.1, dominant_freq_stddev=0.02, sample_count=n,
        ),
        duplicate_hashes=frozenset(),
        duplicate_groups=(),
    )


# ---------------------------------------------------------------------------
# Helpers — synthetic TextureImageResult for rule-level tests
# ---------------------------------------------------------------------------

def _mock_texture(
    grain: float = 50.0,
    smoothness: float = 45.0,
    micro: float = 38.0,
    status: str = "analyzed",
    error: str = "",
):
    """Build a minimal MagicMock that looks like a TextureImageResult."""
    r = MagicMock()
    r.status = status
    r.error = error
    r.pencil_grain_score = grain
    r.watercolor_smoothness_score = smoothness
    r.microtexture_density_score = micro
    return r


# ---------------------------------------------------------------------------
# Contract tests
# ---------------------------------------------------------------------------

class TestCrystallineFacetingAnalyzerContract(unittest.TestCase):
    def setUp(self):
        self.analyzer = CrystallineFacetingAnalyzer()

    def test_name(self):
        self.assertEqual(self.analyzer.name, "crystalline_faceting_analyzer")

    def test_version(self):
        self.assertEqual(self.analyzer.version, "v1")

    def test_analyzer_id(self):
        self.assertEqual(
            self.analyzer.analyzer_id,
            "crystalline_faceting_analyzer/v1",
        )

    def test_supported_categories(self):
        cats = self.analyzer.supported_categories
        self.assertIn("artifact.crystalline_faceting", cats)
        self.assertIn("artifact.crystalline_faceting.error", cats)

    def test_benchmark_version_is_none_until_calibrated(self):
        self.assertIsNone(self.analyzer.benchmark_version)


# ---------------------------------------------------------------------------
# Detection rule tests (mock evaluate_texture — pure rule logic)
# ---------------------------------------------------------------------------

class TestCrystallineFacetingDetectionRule(unittest.TestCase):
    """Test the three-condition detection rule in isolation.

    We patch `evaluate_texture` so we can set exact metric values without
    needing synthetic images that reliably produce boundary-value scores.
    """

    MODULE = "dataset_forge.analyzers.crystalline.evaluate_texture"

    def setUp(self):
        self.analyzer = CrystallineFacetingAnalyzer()
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "img.png"
        _write_smooth_image(self.path)  # content irrelevant; evaluate_texture is mocked

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, grain, smoothness, micro):
        tex = _mock_texture(grain=grain, smoothness=smoothness, micro=micro)
        with patch(self.MODULE, return_value=tex):
            return self.analyzer.analyze(self.path, _ctx())

    def test_all_conditions_met_produces_finding(self):
        findings = self._run(grain=50.0, smoothness=45.0, micro=38.0)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].category, "artifact.crystalline_faceting")

    def test_grain_below_threshold_no_finding(self):
        findings = self._run(grain=_GRAIN_THRESHOLD - 0.1, smoothness=45.0, micro=38.0)
        self.assertEqual(findings, [])

    def test_grain_at_threshold_produces_finding(self):
        findings = self._run(grain=_GRAIN_THRESHOLD, smoothness=45.0, micro=38.0)
        self.assertEqual(len(findings), 1)

    def test_smoothness_at_ceiling_no_finding(self):
        findings = self._run(grain=50.0, smoothness=_SMOOTHNESS_CEILING, micro=38.0)
        self.assertEqual(findings, [])

    def test_smoothness_just_below_ceiling_produces_finding(self):
        findings = self._run(grain=50.0, smoothness=_SMOOTHNESS_CEILING - 0.1, micro=38.0)
        self.assertEqual(len(findings), 1)

    def test_micro_below_floor_no_finding(self):
        findings = self._run(grain=50.0, smoothness=45.0, micro=_MICRO_FLOOR - 0.1)
        self.assertEqual(findings, [])

    def test_micro_at_floor_produces_finding(self):
        findings = self._run(grain=50.0, smoothness=45.0, micro=_MICRO_FLOOR)
        self.assertEqual(len(findings), 1)

    def test_all_conditions_just_at_boundary_produces_finding(self):
        findings = self._run(
            grain=_GRAIN_THRESHOLD,
            smoothness=_SMOOTHNESS_CEILING - 0.01,
            micro=_MICRO_FLOOR,
        )
        self.assertEqual(len(findings), 1)

    def test_missing_any_one_condition_suppresses(self):
        # Only grain fails
        self.assertEqual(self._run(grain=44.9, smoothness=45.0, micro=38.0), [])
        # Only smoothness fails (too high)
        self.assertEqual(self._run(grain=50.0, smoothness=52.0, micro=38.0), [])
        # Only micro fails (too low)
        self.assertEqual(self._run(grain=50.0, smoothness=45.0, micro=19.9), [])

    def test_provided_measurements_preserve_rule_behavior(self):
        tex = _mock_texture(grain=50.0, smoothness=45.0, micro=38.0)
        with patch(self.MODULE, return_value=tex):
            expected = self.analyzer.analyze(self.path, _ctx())
        measurements = ImageMeasurements(
            image_path=self.path.expanduser().resolve(),
            texture=tex,
        )
        with patch(
            self.MODULE,
            side_effect=AssertionError("analyzer remeasured image"),
        ):
            findings = self.analyzer.analyze(
                self.path,
                _ctx(),
                measurements=measurements,
            )

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings, expected)
        self.assertEqual(findings[0].category, "artifact.crystalline_faceting")


# ---------------------------------------------------------------------------
# Finding field tests
# ---------------------------------------------------------------------------

class TestCrystallineFacetingFindingFields(unittest.TestCase):
    MODULE = "dataset_forge.analyzers.crystalline.evaluate_texture"

    def setUp(self):
        self.analyzer = CrystallineFacetingAnalyzer()
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "img.png"
        _write_smooth_image(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def _finding(self) -> Finding:
        tex = _mock_texture(grain=50.0, smoothness=45.0, micro=38.0)
        with patch(self.MODULE, return_value=tex):
            findings = self.analyzer.analyze(self.path, _ctx())
        self.assertEqual(len(findings), 1)
        return findings[0]

    def test_finding_is_Finding_instance(self):
        self.assertIsInstance(self._finding(), Finding)

    def test_finding_analyzer_id(self):
        self.assertEqual(self._finding().analyzer, "crystalline_faceting_analyzer/v1")

    def test_finding_category(self):
        self.assertEqual(self._finding().category, "artifact.crystalline_faceting")

    def test_finding_severity_is_low_for_grain_below_medium_threshold(self):
        # _finding() uses grain=50.0 which is below _SEVERITY_MEDIUM_GRAIN (55)
        self.assertEqual(self._finding().severity, Severity.LOW)

    def test_finding_confidence_is_uncalibrated(self):
        self.assertAlmostEqual(self._finding().confidence, _UNCALIBRATED_CONFIDENCE)

    def test_finding_false_positive_rate_is_conservative(self):
        self.assertAlmostEqual(
            self._finding().false_positive_rate, _UNCALIBRATED_FP_RATE
        )

    def test_finding_benchmark_version_is_uncalibrated(self):
        self.assertEqual(self._finding().benchmark_version, BENCHMARK_VERSION)

    def test_finding_image_path_matches(self):
        self.assertEqual(self._finding().image_path, self.path)

    def test_evidence_contains_required_keys(self):
        ev = self._finding().evidence
        for key in (
            "pencil_grain_score",
            "watercolor_smoothness_score",
            "microtexture_density_score",
            "grain_threshold",
            "smoothness_ceiling",
            "micro_floor",
            "severity_medium_grain",
            "severity_high_grain",
            "calibrated",
        ):
            self.assertIn(key, ev, f"Missing evidence key: {key}")

    def test_evidence_calibrated_flag_is_false(self):
        self.assertFalse(self._finding().evidence["calibrated"])

    def test_evidence_scores_match_texture_result(self):
        ev = self._finding().evidence
        self.assertAlmostEqual(ev["pencil_grain_score"], 50.0)
        self.assertAlmostEqual(ev["watercolor_smoothness_score"], 45.0)
        self.assertAlmostEqual(ev["microtexture_density_score"], 38.0)

    def test_evidence_thresholds_match_constants(self):
        ev = self._finding().evidence
        self.assertEqual(ev["grain_threshold"], _GRAIN_THRESHOLD)
        self.assertEqual(ev["smoothness_ceiling"], _SMOOTHNESS_CEILING)
        self.assertEqual(ev["micro_floor"], _MICRO_FLOOR)

    def test_explanation_mentions_scores(self):
        text = self._finding().explanation
        self.assertIn("50.0", text)  # grain value
        self.assertIn("45.0", text)  # smoothness value

    def test_recommendation_mentions_review(self):
        rec = self._finding().recommendation
        self.assertIn("Review", rec)

    def test_evidence_severity_medium_grain_matches_constant(self):
        ev = self._finding().evidence
        self.assertEqual(ev["severity_medium_grain"], _SEVERITY_MEDIUM_GRAIN)

    def test_evidence_severity_high_grain_matches_constant(self):
        ev = self._finding().evidence
        self.assertEqual(ev["severity_high_grain"], _SEVERITY_HIGH_GRAIN)


# ---------------------------------------------------------------------------
# Severity tier tests
# ---------------------------------------------------------------------------

class TestCrystallineFacetingSeverityTiers(unittest.TestCase):
    """Verify the grain-based severity model: LOW / MEDIUM / HIGH."""

    MODULE = "dataset_forge.analyzers.crystalline.evaluate_texture"

    def setUp(self):
        self.analyzer = CrystallineFacetingAnalyzer()
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "img.png"
        _write_smooth_image(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def _severity(self, grain: float) -> Severity:
        tex = _mock_texture(grain=grain, smoothness=45.0, micro=38.0)
        with patch(self.MODULE, return_value=tex):
            findings = self.analyzer.analyze(self.path, _ctx())
        self.assertEqual(len(findings), 1)
        return findings[0].severity

    def test_grain_below_medium_threshold_is_low(self):
        # grain = 45.0 (at detection threshold, below MEDIUM boundary)
        self.assertEqual(self._severity(_GRAIN_THRESHOLD), Severity.LOW)

    def test_grain_just_below_medium_threshold_is_low(self):
        self.assertEqual(self._severity(_SEVERITY_MEDIUM_GRAIN - 0.1), Severity.LOW)

    def test_grain_at_medium_threshold_is_medium(self):
        self.assertEqual(self._severity(_SEVERITY_MEDIUM_GRAIN), Severity.MEDIUM)

    def test_grain_just_above_medium_threshold_is_medium(self):
        self.assertEqual(self._severity(_SEVERITY_MEDIUM_GRAIN + 0.1), Severity.MEDIUM)

    def test_grain_just_below_high_threshold_is_medium(self):
        self.assertEqual(self._severity(_SEVERITY_HIGH_GRAIN - 0.1), Severity.MEDIUM)

    def test_grain_at_high_threshold_is_high(self):
        self.assertEqual(self._severity(_SEVERITY_HIGH_GRAIN), Severity.HIGH)

    def test_grain_above_high_threshold_is_high(self):
        self.assertEqual(self._severity(_SEVERITY_HIGH_GRAIN + 5.0), Severity.HIGH)

    def test_mid_range_low(self):
        # grain = 50.0: clearly between detection threshold (45) and MEDIUM boundary (55)
        self.assertEqual(self._severity(50.0), Severity.LOW)

    def test_mid_range_medium(self):
        # grain = 60.0: between MEDIUM boundary (55) and HIGH boundary (65)
        self.assertEqual(self._severity(60.0), Severity.MEDIUM)

    def test_mid_range_high(self):
        # grain = 70.0: above HIGH boundary (65)
        self.assertEqual(self._severity(70.0), Severity.HIGH)

    def test_severity_constants_ordered_correctly(self):
        # Detection threshold < MEDIUM boundary < HIGH boundary
        self.assertLess(_GRAIN_THRESHOLD, _SEVERITY_MEDIUM_GRAIN)
        self.assertLess(_SEVERITY_MEDIUM_GRAIN, _SEVERITY_HIGH_GRAIN)

    def test_severity_tiers_are_contiguous(self):
        # No gap or overlap: thresholds are grain < 55 = LOW, 55-65 = MEDIUM, 65+ = HIGH
        tex_lo = _mock_texture(grain=_SEVERITY_MEDIUM_GRAIN - 0.001, smoothness=45.0, micro=38.0)
        tex_hi = _mock_texture(grain=_SEVERITY_MEDIUM_GRAIN,         smoothness=45.0, micro=38.0)
        with patch(self.MODULE, return_value=tex_lo):
            sev_lo = self.analyzer.analyze(self.path, _ctx())[0].severity
        with patch(self.MODULE, return_value=tex_hi):
            sev_hi = self.analyzer.analyze(self.path, _ctx())[0].severity
        self.assertEqual(sev_lo, Severity.LOW)
        self.assertEqual(sev_hi, Severity.MEDIUM)


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestCrystallineFacetingErrorHandling(unittest.TestCase):
    MODULE = "dataset_forge.analyzers.crystalline.evaluate_texture"

    def setUp(self):
        self.analyzer = CrystallineFacetingAnalyzer()

    def test_missing_file_returns_error_finding(self):
        path = Path("/nonexistent/image.png")
        findings = self.analyzer.analyze(path, _ctx())
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].category, "artifact.crystalline_faceting.error")
        self.assertEqual(findings[0].severity, Severity.LOW)

    def test_evaluate_texture_error_status_returns_error_finding(self):
        tex = _mock_texture(status="error", error="cannot open file")
        with patch(self.MODULE, return_value=tex):
            findings = self.analyzer.analyze(Path("/any.png"), _ctx())
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].category, "artifact.crystalline_faceting.error")

    def test_error_finding_has_error_in_evidence(self):
        tex = _mock_texture(status="error", error="corrupt")
        with patch(self.MODULE, return_value=tex):
            findings = self.analyzer.analyze(Path("/any.png"), _ctx())
        self.assertIn("error", findings[0].evidence)

    def test_error_finding_false_positive_rate_is_zero(self):
        path = Path("/nonexistent/image.png")
        findings = self.analyzer.analyze(path, _ctx())
        self.assertEqual(findings[0].false_positive_rate, 0.0)


# ---------------------------------------------------------------------------
# Synthetic image integration tests (real evaluate_texture)
# ---------------------------------------------------------------------------

class TestCrystallineFacetingIntegration(unittest.TestCase):
    """Run the real evaluate_texture on synthetic images.

    These tests verify behavior at the evaluate_texture→analyzer boundary
    without mocking, so they are sensitive to score changes in texture.py.
    They do NOT verify exact threshold boundary crossing — they verify the
    overall suppress/detect behavior for clearly safe cases.
    """

    def setUp(self):
        self.analyzer = CrystallineFacetingAnalyzer()
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_solid_grey_never_triggers(self):
        """Solid grey has near-zero grain, micro, and high smoothness."""
        p = Path(self.tmp.name) / "grey.png"
        _write_smooth_image(p)
        findings = self.analyzer.analyze(p, _ctx())
        # Smooth image: micro and grain will be far below thresholds
        # (we don't assert [] because smoothness guard could stop it first)
        # Either way, a solid grey image must not produce a faceting finding.
        faceting = [f for f in findings if f.category == "artifact.crystalline_faceting"]
        self.assertEqual(faceting, [])

    def test_returns_list(self):
        p = Path(self.tmp.name) / "grey.png"
        _write_smooth_image(p)
        result = self.analyzer.analyze(p, _ctx())
        self.assertIsInstance(result, list)

    def test_context_not_required_for_detection(self):
        """Analyzer uses absolute thresholds; context distribution is not read."""
        p = Path(self.tmp.name) / "grey.png"
        _write_smooth_image(p)
        # Empty context should not cause errors
        empty_ctx = DatasetContext(
            schema_version=CONTEXT_SCHEMA_VERSION,
            analyzer_versions={},
            image_paths=(),
            image_count=0,
            error_count=0,
            resolution_stats=ResolutionStats.empty(),
            aspect_ratio_stats=AspectRatioStats.empty(),
            texture_distributions=TextureDistributions.empty(),
            frequency_distributions=FrequencyDistributions.empty(),
            duplicate_hashes=frozenset(),
            duplicate_groups=(),
        )
        # Should not raise — returns [] or a finding but not an exception
        result = self.analyzer.analyze(p, empty_ctx)
        self.assertIsInstance(result, list)


if __name__ == "__main__":
    unittest.main()
