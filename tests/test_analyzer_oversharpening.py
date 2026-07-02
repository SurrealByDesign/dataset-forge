"""Tests for OversharpeningHaloAnalyzer."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

from dataset_forge.analyzers.oversharpening import (
    BENCHMARK_VERSION,
    USMResidualResult,
    OversharpeningHaloAnalyzer,
    _UNCALIBRATED_FP_RATE,
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
from dataset_forge.finding import Finding, Severity


def _ctx() -> DatasetContext:
    return DatasetContext(
        schema_version=CONTEXT_SCHEMA_VERSION,
        analyzer_versions={"oversharpening_halo_analyzer": "v1"},
        image_paths=(),
        image_count=1,
        error_count=0,
        resolution_stats=ResolutionStats.empty(),
        aspect_ratio_stats=AspectRatioStats.empty(),
        texture_distributions=TextureDistributions.empty(),
        frequency_distributions=FrequencyDistributions.empty(),
        duplicate_hashes=frozenset(),
        duplicate_groups=(),
    )


def _write_smooth_image(path: Path) -> None:
    arr = np.full((64, 64, 3), 128, dtype=np.uint8)
    Image.fromarray(arr).save(path)


class TestOversharpeningHaloAnalyzerContract(unittest.TestCase):
    def setUp(self):
        self.analyzer = OversharpeningHaloAnalyzer()

    def test_name(self):
        self.assertEqual(self.analyzer.name, "oversharpening_halo_analyzer")

    def test_version(self):
        self.assertEqual(self.analyzer.version, "v1")

    def test_analyzer_id(self):
        self.assertEqual(
            self.analyzer.analyzer_id,
            "oversharpening_halo_analyzer/v1",
        )

    def test_supported_categories(self):
        cats = self.analyzer.supported_categories
        self.assertIn("artifact.oversharpening_halo", cats)
        self.assertIn("artifact.oversharpening_halo.error", cats)

    def test_benchmark_version_is_none_until_real_world_calibration(self):
        self.assertIsNone(self.analyzer.benchmark_version)


class TestOversharpeningHaloDetectionRule(unittest.TestCase):
    MODULE = "dataset_forge.analyzers.oversharpening.measure_usm_residual"

    def setUp(self):
        self.analyzer = OversharpeningHaloAnalyzer()
        self.path = Path("image.png")

    def _run(self, result: USMResidualResult) -> list[Finding]:
        with patch(self.MODULE, return_value=result):
            return self.analyzer.analyze(self.path, _ctx())

    def test_elevated_usm_residual_produces_finding(self):
        findings = self._run(USMResidualResult(
            status="analyzed",
            edge_residual_mean=48.0,
            non_edge_residual_mean=0.5,
            edge_residual_ratio=96.0,
            edge_residual_p95=110.0,
            residual_p95=18.0,
            edge_density=0.02,
        ))

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].category, "artifact.oversharpening_halo")
        self.assertEqual(findings[0].severity, Severity.MEDIUM)

    def test_low_edge_residual_suppresses_finding(self):
        findings = self._run(USMResidualResult(
            status="analyzed",
            edge_residual_mean=25.0,
            edge_residual_ratio=100.0,
            edge_residual_p95=42.0,
            edge_density=0.02,
        ))

        self.assertEqual(findings, [])

    def test_distributed_texture_without_edges_suppresses_finding(self):
        findings = self._run(USMResidualResult(
            status="analyzed",
            edge_residual_mean=0.0,
            edge_residual_ratio=0.0,
            edge_residual_p95=0.0,
            edge_density=0.0,
        ))

        self.assertEqual(findings, [])

    def test_high_edge_density_suppresses_finding(self):
        findings = self._run(USMResidualResult(
            status="analyzed",
            edge_residual_mean=60.0,
            edge_residual_ratio=20.0,
            edge_residual_p95=120.0,
            edge_density=0.25,
        ))

        self.assertEqual(findings, [])


class TestOversharpeningHaloFindingFields(unittest.TestCase):
    MODULE = "dataset_forge.analyzers.oversharpening.measure_usm_residual"

    def setUp(self):
        self.analyzer = OversharpeningHaloAnalyzer()
        self.path = Path("image.png")

    def _finding(self) -> Finding:
        result = USMResidualResult(
            status="analyzed",
            edge_residual_mean=48.0,
            non_edge_residual_mean=0.5,
            edge_residual_ratio=96.0,
            edge_residual_p95=110.0,
            residual_p95=18.0,
            edge_density=0.02,
        )
        with patch(self.MODULE, return_value=result):
            findings = self.analyzer.analyze(self.path, _ctx())
        self.assertEqual(len(findings), 1)
        return findings[0]

    def test_finding_is_finding_instance(self):
        self.assertIsInstance(self._finding(), Finding)

    def test_finding_analyzer_id(self):
        self.assertEqual(
            self._finding().analyzer,
            "oversharpening_halo_analyzer/v1",
        )

    def test_finding_confidence_is_capped(self):
        self.assertLessEqual(self._finding().confidence, _UNCALIBRATED_MAX_CONFIDENCE)

    def test_finding_false_positive_rate_is_conservative(self):
        self.assertEqual(self._finding().false_positive_rate, _UNCALIBRATED_FP_RATE)

    def test_finding_benchmark_version_is_uncalibrated(self):
        self.assertEqual(self._finding().benchmark_version, BENCHMARK_VERSION)

    def test_evidence_contains_required_usm_residual_keys(self):
        ev = self._finding().evidence
        for key in (
            "edge_residual_mean",
            "non_edge_residual_mean",
            "edge_residual_ratio",
            "edge_residual_p95",
            "residual_p95",
            "edge_density",
            "sigma_baseline",
            "calibrated",
        ):
            self.assertIn(key, ev)

    def test_evidence_is_json_serializable(self):
        json.dumps(self._finding().evidence)

    def test_evidence_calibrated_flag_is_false(self):
        self.assertFalse(self._finding().evidence["calibrated"])

    def test_evidence_does_not_use_failed_research_metrics(self):
        ev = self._finding().evidence
        self.assertNotIn("halo_score", ev)
        self.assertNotIn("ringing_score", ev)

    def test_explanation_mentions_usm_residual(self):
        self.assertIn("USM residual", self._finding().explanation)

    def test_recommendation_mentions_human_review(self):
        self.assertIn("human review", self._finding().recommendation)


class TestOversharpeningHaloErrorHandling(unittest.TestCase):
    def setUp(self):
        self.analyzer = OversharpeningHaloAnalyzer()

    def test_missing_file_returns_error_finding(self):
        path = Path("/nonexistent/image.png")
        findings = self.analyzer.analyze(path, _ctx())
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].category, "artifact.oversharpening_halo.error")
        self.assertEqual(findings[0].severity, Severity.LOW)
        self.assertIn("error", findings[0].evidence)

    def test_smooth_image_has_no_finding(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "smooth.png"
            _write_smooth_image(path)
            findings = self.analyzer.analyze(path, _ctx())
        self.assertEqual(findings, [])

    def test_measure_usm_residual_is_read_only_measurement(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "smooth.png"
            _write_smooth_image(path)
            result = measure_usm_residual(path)
        self.assertEqual(result.status, "analyzed")


if __name__ == "__main__":
    unittest.main()
