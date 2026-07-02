"""Tests for HighFrequencyIsolatedArtifactAnalyzer."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

from dataset_forge.analyzers.high_frequency_isolated import (
    BENCHMARK_VERSION,
    HighFrequencyIsolatedArtifactAnalyzer,
    IsolatedArtifactResult,
    _UNCALIBRATED_FP_RATE,
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
from dataset_forge.finding import Finding, Severity


def _ctx() -> DatasetContext:
    return DatasetContext(
        schema_version=CONTEXT_SCHEMA_VERSION,
        analyzer_versions={"high_frequency_isolated_artifact_analyzer": "v1"},
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


class TestHighFrequencyIsolatedAnalyzerContract(unittest.TestCase):
    def setUp(self):
        self.analyzer = HighFrequencyIsolatedArtifactAnalyzer()

    def test_name(self):
        self.assertEqual(
            self.analyzer.name,
            "high_frequency_isolated_artifact_analyzer",
        )

    def test_version(self):
        self.assertEqual(self.analyzer.version, "v1")

    def test_analyzer_id(self):
        self.assertEqual(
            self.analyzer.analyzer_id,
            "high_frequency_isolated_artifact_analyzer/v1",
        )

    def test_supported_categories(self):
        cats = self.analyzer.supported_categories
        self.assertIn("artifact.high_frequency_isolated", cats)
        self.assertIn("artifact.high_frequency_isolated.error", cats)

    def test_benchmark_version_is_none_until_real_world_calibration(self):
        self.assertIsNone(self.analyzer.benchmark_version)


class TestHighFrequencyIsolatedDetectionRule(unittest.TestCase):
    MODULE = "dataset_forge.analyzers.high_frequency_isolated.measure_isolated_artifacts"

    def setUp(self):
        self.analyzer = HighFrequencyIsolatedArtifactAnalyzer()
        self.path = Path("image.png")

    def _run(self, result: IsolatedArtifactResult) -> list[Finding]:
        with patch(self.MODULE, return_value=result):
            return self.analyzer.analyze(self.path, _ctx())

    def _positive_result(self) -> IsolatedArtifactResult:
        return IsolatedArtifactResult(
            status="analyzed",
            isolated_component_count=18,
            component_density_per_megapixel=274.6,
            mean_component_area_px=2.0,
            observed_max_component_area_px=2,
            median_component_residual=82.0,
            p95_component_residual=94.0,
            bright_component_ratio=1.0,
            dark_component_ratio=0.0,
            chroma_outlier_ratio=0.0,
            edge_adjacent_component_ratio=0.05,
            texture_field_density=0.001,
            isolation_score=0.95,
            residual_threshold=26.0,
            min_component_area_threshold_px=1,
            max_component_area_threshold_px=9,
        )

    def test_sparse_isolated_components_produce_finding(self):
        findings = self._run(self._positive_result())

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].category, "artifact.high_frequency_isolated")
        self.assertEqual(findings[0].severity, Severity.MEDIUM)

    def test_low_count_suppresses_finding(self):
        result = self._positive_result()
        result = IsolatedArtifactResult(
            **{**result.__dict__, "isolated_component_count": 3}
        )

        self.assertEqual(self._run(result), [])

    def test_low_component_residual_suppresses_grain_like_field(self):
        result = self._positive_result()
        result = IsolatedArtifactResult(
            **{
                **result.__dict__,
                "median_component_residual": 28.0,
                "p95_component_residual": 34.0,
            }
        )

        self.assertEqual(self._run(result), [])

    def test_dense_texture_field_suppresses_finding(self):
        result = self._positive_result()
        result = IsolatedArtifactResult(
            **{**result.__dict__, "texture_field_density": 0.08}
        )

        self.assertEqual(self._run(result), [])

    def test_edge_adjacent_components_suppress_finding(self):
        result = self._positive_result()
        result = IsolatedArtifactResult(
            **{
                **result.__dict__,
                "edge_adjacent_component_ratio": 0.9,
                "isolation_score": 0.1,
            }
        )

        self.assertEqual(self._run(result), [])


class TestHighFrequencyIsolatedFindingFields(unittest.TestCase):
    MODULE = "dataset_forge.analyzers.high_frequency_isolated.measure_isolated_artifacts"

    def setUp(self):
        self.analyzer = HighFrequencyIsolatedArtifactAnalyzer()
        self.path = Path("image.png")

    def _finding(self) -> Finding:
        result = IsolatedArtifactResult(
            status="analyzed",
            isolated_component_count=18,
            component_density_per_megapixel=274.6,
            mean_component_area_px=2.0,
            observed_max_component_area_px=2,
            median_component_residual=82.0,
            p95_component_residual=94.0,
            bright_component_ratio=1.0,
            dark_component_ratio=0.0,
            chroma_outlier_ratio=0.0,
            edge_adjacent_component_ratio=0.05,
            texture_field_density=0.001,
            isolation_score=0.95,
            residual_threshold=26.0,
            min_component_area_threshold_px=1,
            max_component_area_threshold_px=9,
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
            "high_frequency_isolated_artifact_analyzer/v1",
        )

    def test_finding_confidence_is_capped(self):
        self.assertLessEqual(self._finding().confidence, _UNCALIBRATED_MAX_CONFIDENCE)

    def test_finding_false_positive_rate_is_conservative(self):
        self.assertEqual(self._finding().false_positive_rate, _UNCALIBRATED_FP_RATE)

    def test_finding_benchmark_version_is_uncalibrated(self):
        self.assertEqual(self._finding().benchmark_version, BENCHMARK_VERSION)

    def test_evidence_contains_required_keys(self):
        ev = self._finding().evidence
        for key in (
            "isolated_component_count",
            "component_density_per_megapixel",
            "mean_component_area_px",
            "observed_max_component_area_px",
            "median_component_residual",
            "p95_component_residual",
            "bright_component_ratio",
            "dark_component_ratio",
            "chroma_outlier_ratio",
            "edge_adjacent_component_ratio",
            "texture_field_density",
            "isolation_score",
            "residual_threshold",
            "min_component_area_threshold_px",
            "max_component_area_threshold_px",
            "calibrated",
        ):
            self.assertIn(key, ev)

    def test_evidence_is_json_serializable(self):
        json.dumps(self._finding().evidence)

    def test_evidence_calibrated_flag_is_false(self):
        self.assertFalse(self._finding().evidence["calibrated"])

    def test_severity_is_low_or_medium_only(self):
        self.assertIn(self._finding().severity, (Severity.LOW, Severity.MEDIUM))

    def test_explanation_mentions_isolated_components(self):
        self.assertIn("isolated", self._finding().explanation)

    def test_recommendation_mentions_human_review(self):
        self.assertIn("human review", self._finding().recommendation)


class TestHighFrequencyIsolatedErrorHandling(unittest.TestCase):
    def setUp(self):
        self.analyzer = HighFrequencyIsolatedArtifactAnalyzer()

    def test_missing_file_returns_error_finding(self):
        path = Path("/nonexistent/image.png")
        findings = self.analyzer.analyze(path, _ctx())
        self.assertEqual(len(findings), 1)
        self.assertEqual(
            findings[0].category,
            "artifact.high_frequency_isolated.error",
        )
        self.assertEqual(findings[0].severity, Severity.LOW)
        self.assertIn("error", findings[0].evidence)

    def test_smooth_image_has_no_finding(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "smooth.png"
            _write_smooth_image(path)
            findings = self.analyzer.analyze(path, _ctx())
        self.assertEqual(findings, [])

    def test_measure_isolated_artifacts_is_read_only_measurement(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "smooth.png"
            _write_smooth_image(path)
            result = measure_isolated_artifacts(path)
        self.assertEqual(result.status, "analyzed")


if __name__ == "__main__":
    unittest.main()
