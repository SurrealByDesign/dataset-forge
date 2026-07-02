"""Regression tests for committed high-frequency isolated benchmark fixtures."""

from __future__ import annotations

import unittest
from pathlib import Path

from dataset_forge.analyzers.high_frequency_isolated import (
    HighFrequencyIsolatedArtifactAnalyzer,
    _UNCALIBRATED_MAX_CONFIDENCE,
    measure_isolated_artifacts,
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
_CLEAN = _FIXTURES_DIR / "14_hfi_clean_negative.png"
_BRIGHT = _FIXTURES_DIR / "15_hfi_bright_speck_positive.png"
_DARK = _FIXTURES_DIR / "16_hfi_dark_speck_positive.png"
_GRAIN = _FIXTURES_DIR / "17_hfi_pencil_grain_guard.png"
_HALO = _FIXTURES_DIR / "18_hfi_edge_halo_guard.png"

_TOL = 0.5

_CONTEXT = DatasetContext(
    schema_version=CONTEXT_SCHEMA_VERSION,
    analyzer_versions={},
    image_paths=(),
    image_count=5,
    error_count=0,
    resolution_stats=ResolutionStats.empty(),
    aspect_ratio_stats=AspectRatioStats.empty(),
    texture_distributions=TextureDistributions.empty(),
    frequency_distributions=FrequencyDistributions.empty(),
    duplicate_hashes=frozenset(),
    duplicate_groups=(),
)

_ANALYZER = HighFrequencyIsolatedArtifactAnalyzer()


def _findings(path: Path):
    return [
        f for f in _ANALYZER.analyze(path, _CONTEXT)
        if f.category == "artifact.high_frequency_isolated"
    ]


class TestHighFrequencyIsolatedFixtureFilesExist(unittest.TestCase):
    def test_clean_fixture_exists(self):
        self.assertTrue(_CLEAN.exists(), f"Missing: {_CLEAN}")

    def test_bright_fixture_exists(self):
        self.assertTrue(_BRIGHT.exists(), f"Missing: {_BRIGHT}")

    def test_dark_fixture_exists(self):
        self.assertTrue(_DARK.exists(), f"Missing: {_DARK}")

    def test_grain_fixture_exists(self):
        self.assertTrue(_GRAIN.exists(), f"Missing: {_GRAIN}")

    def test_halo_fixture_exists(self):
        self.assertTrue(_HALO.exists(), f"Missing: {_HALO}")


class TestCleanFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = measure_isolated_artifacts(_CLEAN)
        cls.findings = _findings(_CLEAN)

    def test_no_finding(self):
        self.assertEqual(self.findings, [])

    def test_no_isolated_components(self):
        self.assertEqual(self.r.isolated_component_count, 0)


class TestBrightSpeckFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = measure_isolated_artifacts(_BRIGHT)
        cls.findings = _findings(_BRIGHT)

    def test_finding_emitted(self):
        self.assertEqual(len(self.findings), 1)

    def test_severity_is_medium(self):
        self.assertEqual(self.findings[0].severity, Severity.MEDIUM)

    def test_confidence_remains_capped(self):
        self.assertLessEqual(self.findings[0].confidence, _UNCALIBRATED_MAX_CONFIDENCE)

    def test_evidence_calibrated_flag_is_false(self):
        self.assertFalse(self.findings[0].evidence["calibrated"])

    def test_bright_ratio_is_dominant(self):
        self.assertEqual(self.r.bright_component_ratio, 1.0)
        self.assertEqual(self.r.dark_component_ratio, 0.0)

    def test_score_stability(self):
        self.assertEqual(self.r.isolated_component_count, 22)
        self.assertAlmostEqual(self.r.median_component_residual, 81.1, delta=_TOL)


class TestDarkSpeckFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = measure_isolated_artifacts(_DARK)
        cls.findings = _findings(_DARK)

    def test_finding_emitted(self):
        self.assertEqual(len(self.findings), 1)

    def test_severity_is_medium(self):
        self.assertEqual(self.findings[0].severity, Severity.MEDIUM)

    def test_dark_ratio_is_dominant(self):
        self.assertEqual(self.r.bright_component_ratio, 0.0)
        self.assertEqual(self.r.dark_component_ratio, 1.0)

    def test_score_stability(self):
        self.assertEqual(self.r.isolated_component_count, 22)
        self.assertAlmostEqual(self.r.median_component_residual, 86.8, delta=_TOL)


class TestPencilGrainGuardFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = measure_isolated_artifacts(_GRAIN)
        cls.findings = _findings(_GRAIN)

    def test_no_finding(self):
        self.assertEqual(self.findings, [])

    def test_component_residual_below_detection_floor(self):
        self.assertLess(self.r.median_component_residual, 45.0)
        self.assertGreater(self.r.isolated_component_count, 100)


class TestEdgeHaloGuardFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = measure_isolated_artifacts(_HALO)
        cls.findings = _findings(_HALO)

    def test_no_finding(self):
        self.assertEqual(self.findings, [])

    def test_components_are_edge_adjacent(self):
        self.assertEqual(self.r.edge_adjacent_component_ratio, 1.0)
        self.assertEqual(self.r.isolation_score, 0.0)


if __name__ == "__main__":
    unittest.main()
