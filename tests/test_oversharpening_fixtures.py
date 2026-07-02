"""Regression tests for committed oversharpening benchmark fixtures."""

from __future__ import annotations

import unittest
from pathlib import Path

from dataset_forge.analyzers.oversharpening import (
    OversharpeningHaloAnalyzer,
    _LOW_EDGE_RESIDUAL_P95,
    _MEDIUM_EDGE_RESIDUAL_P95,
    _UNCALIBRATED_MAX_CONFIDENCE,
    measure_usm_residual,
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
_CLEAN_EDGE = _FIXTURES_DIR / "11_oversharpen_clean_edge.png"
_HALO_POSITIVE = _FIXTURES_DIR / "12_oversharpen_halo_positive.png"
_TEXTURE_GUARD = _FIXTURES_DIR / "13_oversharpen_texture_guard.png"

_TOL = 0.5

_CONTEXT = DatasetContext(
    schema_version=CONTEXT_SCHEMA_VERSION,
    analyzer_versions={},
    image_paths=(),
    image_count=3,
    error_count=0,
    resolution_stats=ResolutionStats.empty(),
    aspect_ratio_stats=AspectRatioStats.empty(),
    texture_distributions=TextureDistributions.empty(),
    frequency_distributions=FrequencyDistributions.empty(),
    duplicate_hashes=frozenset(),
    duplicate_groups=(),
)

_ANALYZER = OversharpeningHaloAnalyzer()


def _findings(path: Path):
    return [
        f for f in _ANALYZER.analyze(path, _CONTEXT)
        if f.category == "artifact.oversharpening_halo"
    ]


class TestOversharpeningFixtureFilesExist(unittest.TestCase):
    def test_clean_edge_fixture_exists(self):
        self.assertTrue(_CLEAN_EDGE.exists(), f"Missing: {_CLEAN_EDGE}")

    def test_halo_positive_fixture_exists(self):
        self.assertTrue(_HALO_POSITIVE.exists(), f"Missing: {_HALO_POSITIVE}")

    def test_texture_guard_fixture_exists(self):
        self.assertTrue(_TEXTURE_GUARD.exists(), f"Missing: {_TEXTURE_GUARD}")


class TestCleanEdgeFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = measure_usm_residual(_CLEAN_EDGE)
        cls.findings = _findings(_CLEAN_EDGE)

    def test_no_finding(self):
        self.assertEqual(self.findings, [])

    def test_edge_residual_p95_below_threshold(self):
        self.assertLess(self.r.edge_residual_p95, _LOW_EDGE_RESIDUAL_P95)

    def test_score_stability(self):
        self.assertAlmostEqual(self.r.edge_residual_p95, 42.1, delta=_TOL)
        self.assertAlmostEqual(self.r.edge_residual_mean, 26.0, delta=_TOL)


class TestHaloPositiveFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = measure_usm_residual(_HALO_POSITIVE)
        cls.findings = _findings(_HALO_POSITIVE)

    def test_finding_emitted(self):
        self.assertEqual(len(self.findings), 1)

    def test_severity_is_medium(self):
        self.assertEqual(self.findings[0].severity, Severity.MEDIUM)

    def test_confidence_remains_capped(self):
        self.assertLessEqual(self.findings[0].confidence, _UNCALIBRATED_MAX_CONFIDENCE)

    def test_evidence_calibrated_flag_is_false(self):
        self.assertFalse(self.findings[0].evidence["calibrated"])

    def test_edge_residual_p95_exceeds_medium_threshold(self):
        self.assertGreaterEqual(self.r.edge_residual_p95, _MEDIUM_EDGE_RESIDUAL_P95)

    def test_score_stability(self):
        self.assertAlmostEqual(self.r.edge_residual_p95, 110.1, delta=_TOL)
        self.assertAlmostEqual(self.r.edge_residual_mean, 48.2, delta=_TOL)


class TestTextureGuardFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = measure_usm_residual(_TEXTURE_GUARD)
        cls.findings = _findings(_TEXTURE_GUARD)

    def test_no_finding(self):
        self.assertEqual(self.findings, [])

    def test_no_edge_localized_usm_signal(self):
        self.assertEqual(self.r.edge_density, 0.0)
        self.assertEqual(self.r.edge_residual_p95, 0.0)


class TestFixtureContrast(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.clean = measure_usm_residual(_CLEAN_EDGE)
        cls.positive = measure_usm_residual(_HALO_POSITIVE)

    def test_positive_edge_residual_exceeds_clean_edge(self):
        self.assertGreater(
            self.positive.edge_residual_p95,
            self.clean.edge_residual_p95 + 50.0,
        )


if __name__ == "__main__":
    unittest.main()
