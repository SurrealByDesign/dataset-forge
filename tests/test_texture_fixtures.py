"""Regression tests for committed synthetic texture benchmark fixtures.

These tests load the actual committed PNG files and verify their scores against
the values measured at generation time. They serve as regression guards for:
  - The fixture images (break if images are accidentally modified)
  - evaluate_texture() output (break if measurement code changes)
  - TextureAnalyzer detection logic (break if thresholds or z-score logic changes)

Fixture files:
    benchmarks/synthetic_defects/09_texture_clean.png
    benchmarks/synthetic_defects/10_texture_positive.png

Generator:
    scripts/generate_texture_fixtures.py
"""

from __future__ import annotations

import statistics
import unittest
from pathlib import Path

from dataset_forge.analysis.texture import evaluate_texture
from dataset_forge.analyzers.texture import (
    TextureAnalyzer,
    _ABSOLUTE_FLOOR,
    _Z_MEDIUM,
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
_CLEAN_FIXTURE = _FIXTURES_DIR / "09_texture_clean.png"
_NOISE_FIXTURE = _FIXTURES_DIR / "10_texture_positive.png"

_TOL = 0.5

# Scores measured at generation time.
_CLEAN_MICRO = 0.0
_NOISE_MICRO = 88.7

# Context built from the two-image texture_committed group.
# Population stddev of [0, X] = X/2; z of noise = (X - X/2) / (X/2) = 1.0.
_GROUP_MICROS = [_CLEAN_MICRO, _NOISE_MICRO]
_GROUP_MEAN = statistics.mean(_GROUP_MICROS)
_GROUP_STDDEV = statistics.pstdev(_GROUP_MICROS)

_GROUP_CONTEXT = DatasetContext(
    schema_version=CONTEXT_SCHEMA_VERSION,
    analyzer_versions={},
    image_paths=(),
    image_count=2,
    error_count=0,
    resolution_stats=ResolutionStats.empty(),
    aspect_ratio_stats=AspectRatioStats.empty(),
    texture_distributions=TextureDistributions(
        mean=_GROUP_MEAN,
        stddev=_GROUP_STDDEV,
        p10=_CLEAN_MICRO,
        p90=_NOISE_MICRO,
        sample_count=2,
    ),
    frequency_distributions=FrequencyDistributions.empty(),
    duplicate_hashes=frozenset(),
    duplicate_groups=(),
)

_ANALYZER = TextureAnalyzer()


def _measure(path: Path):
    r = evaluate_texture(path)
    if r.status != "analyzed":
        raise RuntimeError(f"evaluate_texture failed on {path}: {r.error}")
    return r


def _texture_findings(path: Path, ctx: DatasetContext):
    return [
        f for f in _ANALYZER.analyze(path, ctx)
        if f.category == "texture.high_microtexture"
    ]


class TestFixtureFilesExist(unittest.TestCase):
    def test_clean_fixture_exists(self):
        self.assertTrue(_CLEAN_FIXTURE.exists(), f"Missing: {_CLEAN_FIXTURE}")

    def test_noise_fixture_exists(self):
        self.assertTrue(_NOISE_FIXTURE.exists(), f"Missing: {_NOISE_FIXTURE}")


class TestCleanFixture(unittest.TestCase):
    """09_texture_clean.png: flat grey anchor. No finding (below absolute floor)."""

    @classmethod
    def setUpClass(cls):
        cls.r = _measure(_CLEAN_FIXTURE)
        cls.findings = _texture_findings(_CLEAN_FIXTURE, _GROUP_CONTEXT)

    def test_no_finding(self):
        self.assertEqual(len(self.findings), 0, "Expected no texture finding for clean image")

    def test_micro_below_absolute_floor(self):
        self.assertLess(self.r.microtexture_density_score, _ABSOLUTE_FLOOR)

    def test_micro_score_stable(self):
        self.assertAlmostEqual(self.r.microtexture_density_score, _CLEAN_MICRO, delta=_TOL)

    def test_grain_score_stable(self):
        self.assertAlmostEqual(self.r.pencil_grain_score, 42.0, delta=_TOL)

    def test_smooth_score_stable(self):
        self.assertAlmostEqual(self.r.watercolor_smoothness_score, 100.0, delta=_TOL)


class TestNoiseFixture(unittest.TestCase):
    """10_texture_positive.png: seeded uniform noise. TextureAnalyzer fires MEDIUM."""

    @classmethod
    def setUpClass(cls):
        cls.r = _measure(_NOISE_FIXTURE)
        cls.findings = _texture_findings(_NOISE_FIXTURE, _GROUP_CONTEXT)

    def test_finding_emitted(self):
        self.assertTrue(len(self.findings) > 0, "Expected a texture finding, got none")

    def test_severity_is_medium(self):
        self.assertEqual(self.findings[0].severity, Severity.MEDIUM)

    def test_micro_above_absolute_floor(self):
        self.assertGreaterEqual(self.r.microtexture_density_score, _ABSOLUTE_FLOOR)

    def test_micro_score_stable(self):
        self.assertAlmostEqual(self.r.microtexture_density_score, _NOISE_MICRO, delta=_TOL)

    def test_grain_score_stable(self):
        self.assertAlmostEqual(self.r.pencil_grain_score, 77.1, delta=_TOL)

    def test_smooth_score_stable(self):
        self.assertAlmostEqual(self.r.watercolor_smoothness_score, 22.0, delta=_TOL)

    def test_z_score_is_at_medium_boundary(self):
        z = self.findings[0].evidence.get("z_score")
        self.assertIsNotNone(z)
        self.assertGreaterEqual(z, _Z_MEDIUM)

    def test_z_score_pinned_to_one(self):
        """For a two-image [0, X] group, z is structurally 1.0 exactly."""
        z = self.findings[0].evidence.get("z_score")
        self.assertAlmostEqual(z, 1.0, delta=0.01)


class TestGroupContextConsistency(unittest.TestCase):
    """Validates the two-image group math used to build _GROUP_CONTEXT."""

    def test_group_mean_is_half_noise_micro(self):
        self.assertAlmostEqual(_GROUP_MEAN, _NOISE_MICRO / 2, delta=0.01)

    def test_group_stddev_equals_mean(self):
        """For [0, X], pstdev = X/2 = mean."""
        self.assertAlmostEqual(_GROUP_STDDEV, _GROUP_MEAN, delta=0.01)

    def test_z_score_for_noise_is_one(self):
        z = (_NOISE_MICRO - _GROUP_MEAN) / _GROUP_STDDEV
        self.assertAlmostEqual(z, 1.0, delta=0.01)

    def test_z_score_for_clean_is_minus_one(self):
        z = (_CLEAN_MICRO - _GROUP_MEAN) / _GROUP_STDDEV
        self.assertAlmostEqual(z, -1.0, delta=0.01)


class TestFixtureContrast(unittest.TestCase):
    """Cross-fixture: noise image has much higher micro than clean."""

    @classmethod
    def setUpClass(cls):
        cls.clean_r = _measure(_CLEAN_FIXTURE)
        cls.noise_r = _measure(_NOISE_FIXTURE)

    def test_noise_micro_far_exceeds_clean(self):
        self.assertGreater(
            self.noise_r.microtexture_density_score,
            self.clean_r.microtexture_density_score + _ABSOLUTE_FLOOR,
        )

    def test_only_noise_exceeds_floor(self):
        self.assertGreaterEqual(self.noise_r.microtexture_density_score, _ABSOLUTE_FLOOR)
        self.assertLess(self.clean_r.microtexture_density_score, _ABSOLUTE_FLOOR)


if __name__ == "__main__":
    unittest.main()
