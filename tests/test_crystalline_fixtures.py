"""Regression tests for committed semi-synthetic crystalline benchmark fixtures.

These tests load the actual committed PNG files and verify their scores against
the values measured at generation time. They serve as regression guards for:
  - The fixture images (break if images are accidentally modified)
  - The metric code (break if evaluate_texture output changes)
  - The analyzer rule (break if detection logic changes)

Fixture files:
    benchmarks/synthetic_defects/06_crystalline_low.png
    benchmarks/synthetic_defects/07_crystalline_medium.png
    benchmarks/synthetic_defects/08_crystalline_negative_smooth.png

Generator:
    scripts/generate_crystalline_fixtures.py
"""

from __future__ import annotations

import unittest
from pathlib import Path

from dataset_forge.analysis.texture import evaluate_texture
from dataset_forge.analyzers.crystalline import (
    CrystallineFacetingAnalyzer,
    _GRAIN_THRESHOLD,
    _SMOOTHNESS_CEILING,
    _MICRO_FLOOR,
    _SEVERITY_MEDIUM_GRAIN,
    _SEVERITY_HIGH_GRAIN,
)
from dataset_forge.context import (
    CONTEXT_SCHEMA_VERSION,
    AspectRatioStats,
    DatasetContext,
    FrequencyDistributions,
    ResolutionStats,
    TextureDistributions,
)
from dataset_forge.finding import Severity

_FIXTURES_DIR = Path(__file__).resolve().parent.parent / "benchmarks" / "synthetic_defects"
_LOW_FIXTURE    = _FIXTURES_DIR / "06_crystalline_low.png"
_MEDIUM_FIXTURE = _FIXTURES_DIR / "07_crystalline_medium.png"
_NEG_FIXTURE    = _FIXTURES_DIR / "08_crystalline_negative_smooth.png"

# Score tolerance: fixtures are deterministic so exact match is expected,
# but a small tolerance guards against float rounding differences across platforms.
_TOL = 0.5

_CONTEXT = DatasetContext(
    schema_version=CONTEXT_SCHEMA_VERSION,
    analyzer_versions={},
    image_paths=(),
    image_count=1,
    error_count=0,
    resolution_stats=ResolutionStats.empty(),
    aspect_ratio_stats=AspectRatioStats.empty(),
    texture_distributions=TextureDistributions(
        mean=25.0, stddev=5.0, p10=18.0, p90=33.0, sample_count=10
    ),
    frequency_distributions=FrequencyDistributions.empty(),
    duplicate_hashes=frozenset(),
    duplicate_groups=(),
)

_ANALYZER = CrystallineFacetingAnalyzer()


def _measure(path: Path):
    r = evaluate_texture(path)
    if r.status != "analyzed":
        raise RuntimeError(f"evaluate_texture failed on {path}: {r.error}")
    return r


def _findings(path: Path):
    return [
        f for f in _ANALYZER.analyze(path, _CONTEXT)
        if f.category == "artifact.crystalline_faceting"
    ]


class TestFixtureFilesExist(unittest.TestCase):
    def test_low_fixture_exists(self):
        self.assertTrue(_LOW_FIXTURE.exists(), f"Missing: {_LOW_FIXTURE}")

    def test_medium_fixture_exists(self):
        self.assertTrue(_MEDIUM_FIXTURE.exists(), f"Missing: {_MEDIUM_FIXTURE}")

    def test_negative_fixture_exists(self):
        self.assertTrue(_NEG_FIXTURE.exists(), f"Missing: {_NEG_FIXTURE}")


class TestLowFixture(unittest.TestCase):
    """06_crystalline_low.png: near-threshold positive case, LOW severity."""

    @classmethod
    def setUpClass(cls):
        cls.r = _measure(_LOW_FIXTURE)
        cls.findings = _findings(_LOW_FIXTURE)

    # --- Detection ---

    def test_analyzer_fires(self):
        self.assertTrue(len(self.findings) > 0, "Expected crystalline finding, got none")

    def test_severity_is_low(self):
        self.assertEqual(self.findings[0].severity, Severity.LOW)

    # --- Guards all satisfied ---

    def test_grain_above_threshold(self):
        self.assertGreaterEqual(self.r.pencil_grain_score, _GRAIN_THRESHOLD)

    def test_smooth_below_ceiling(self):
        self.assertLess(self.r.watercolor_smoothness_score, _SMOOTHNESS_CEILING)

    def test_micro_above_floor(self):
        self.assertGreaterEqual(self.r.microtexture_density_score, _MICRO_FLOOR)

    # --- Severity threshold: grain < MEDIUM boundary ---

    def test_grain_below_medium_threshold(self):
        self.assertLess(self.r.pencil_grain_score, _SEVERITY_MEDIUM_GRAIN)

    # --- Score stability (regression against measured-at-generation values) ---

    def test_grain_score_stable(self):
        self.assertAlmostEqual(self.r.pencil_grain_score, 45.1, delta=_TOL)

    def test_smooth_score_stable(self):
        self.assertAlmostEqual(self.r.watercolor_smoothness_score, 47.3, delta=_TOL)

    def test_micro_score_stable(self):
        self.assertAlmostEqual(self.r.microtexture_density_score, 53.0, delta=_TOL)


class TestMediumFixture(unittest.TestCase):
    """07_crystalline_medium.png: strong positive case, MEDIUM severity."""

    @classmethod
    def setUpClass(cls):
        cls.r = _measure(_MEDIUM_FIXTURE)
        cls.findings = _findings(_MEDIUM_FIXTURE)

    # --- Detection ---

    def test_analyzer_fires(self):
        self.assertTrue(len(self.findings) > 0, "Expected crystalline finding, got none")

    def test_severity_is_medium(self):
        self.assertEqual(self.findings[0].severity, Severity.MEDIUM)

    # --- Guards all satisfied ---

    def test_grain_above_threshold(self):
        self.assertGreaterEqual(self.r.pencil_grain_score, _GRAIN_THRESHOLD)

    def test_smooth_below_ceiling(self):
        self.assertLess(self.r.watercolor_smoothness_score, _SMOOTHNESS_CEILING)

    def test_micro_above_floor(self):
        self.assertGreaterEqual(self.r.microtexture_density_score, _MICRO_FLOOR)

    # --- Severity tier: MEDIUM range ---

    def test_grain_at_or_above_medium_threshold(self):
        self.assertGreaterEqual(self.r.pencil_grain_score, _SEVERITY_MEDIUM_GRAIN)

    def test_grain_below_high_threshold(self):
        self.assertLess(self.r.pencil_grain_score, _SEVERITY_HIGH_GRAIN)

    # --- Score stability ---

    def test_grain_score_stable(self):
        self.assertAlmostEqual(self.r.pencil_grain_score, 64.2, delta=_TOL)

    def test_smooth_score_stable(self):
        self.assertAlmostEqual(self.r.watercolor_smoothness_score, 36.6, delta=_TOL)

    def test_micro_score_stable(self):
        self.assertAlmostEqual(self.r.microtexture_density_score, 65.8, delta=_TOL)


class TestNegativeSmoothGuardFixture(unittest.TestCase):
    """08_crystalline_negative_smooth.png: no finding -- smoothness guard blocks."""

    @classmethod
    def setUpClass(cls):
        cls.r = _measure(_NEG_FIXTURE)
        cls.findings = _findings(_NEG_FIXTURE)

    # --- No detection ---

    def test_analyzer_does_not_fire(self):
        self.assertEqual(len(self.findings), 0, "Expected no crystalline finding")

    # --- Smoothness guard is the active blocker ---

    def test_smooth_above_ceiling(self):
        self.assertGreaterEqual(self.r.watercolor_smoothness_score, _SMOOTHNESS_CEILING)

    # --- Other guards would pass (grain and micro are above threshold) ---

    def test_grain_above_threshold(self):
        self.assertGreaterEqual(self.r.pencil_grain_score, _GRAIN_THRESHOLD)

    def test_micro_above_floor(self):
        self.assertGreaterEqual(self.r.microtexture_density_score, _MICRO_FLOOR)

    # --- Score stability ---

    def test_grain_score_stable(self):
        self.assertAlmostEqual(self.r.pencil_grain_score, 62.0, delta=_TOL)

    def test_smooth_score_stable(self):
        self.assertAlmostEqual(self.r.watercolor_smoothness_score, 53.2, delta=_TOL)

    def test_micro_score_stable(self):
        self.assertAlmostEqual(self.r.microtexture_density_score, 43.3, delta=_TOL)


class TestFixtureMonotonicity(unittest.TestCase):
    """Cross-fixture property: positive fixtures score higher grain than negative."""

    @classmethod
    def setUpClass(cls):
        cls.low_r = _measure(_LOW_FIXTURE)
        cls.med_r = _measure(_MEDIUM_FIXTURE)
        cls.neg_r = _measure(_NEG_FIXTURE)

    def test_medium_grain_exceeds_low_grain(self):
        self.assertGreater(
            self.med_r.pencil_grain_score,
            self.low_r.pencil_grain_score,
        )

    def test_low_smooth_is_lower_than_medium_smooth(self):
        # Both positives have smooth < 52; lower smooth = more artifact-like
        self.assertLess(self.med_r.watercolor_smoothness_score, _SMOOTHNESS_CEILING)
        self.assertLess(self.low_r.watercolor_smoothness_score, _SMOOTHNESS_CEILING)

    def test_negative_smooth_is_highest(self):
        self.assertGreater(
            self.neg_r.watercolor_smoothness_score,
            self.med_r.watercolor_smoothness_score,
        )


if __name__ == "__main__":
    unittest.main()
