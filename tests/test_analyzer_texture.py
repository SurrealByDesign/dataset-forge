"""Tests for TextureAnalyzer.

Uses synthetic PIL images so the tests are self-contained and never touch
the real dataset. All images are generated in-memory and written to a
temporary directory.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

from dataset_forge.analyzers.texture import TextureAnalyzer, _z_to_severity
from dataset_forge.context import (
    CONTEXT_SCHEMA_VERSION,
    AspectRatioStats,
    DatasetContext,
    FrequencyDistributions,
    ResolutionStats,
    TextureDistributions,
)
from dataset_forge.finding import Finding, Severity
from dataset_forge.measurements import measure_image


# ---------------------------------------------------------------------------
# Image factories
# ---------------------------------------------------------------------------

def _write_smooth_image(path: Path) -> None:
    """Solid grey — near-zero microtexture."""
    arr = np.full((256, 256, 3), 128, dtype=np.uint8)
    Image.fromarray(arr).save(path)


def _write_noisy_image(path: Path, noise_level: int = 80) -> None:
    """Random noise — very high microtexture, simulates GPT glitter."""
    rng = np.random.default_rng(42)
    arr = rng.integers(128 - noise_level, 128 + noise_level,
                       size=(256, 256, 3), dtype=np.uint8)
    Image.fromarray(arr).save(path)


def _write_mild_noise_image(path: Path, noise_level: int = 20) -> None:
    rng = np.random.default_rng(7)
    arr = rng.integers(128 - noise_level, 128 + noise_level,
                       size=(256, 256, 3), dtype=np.uint8)
    Image.fromarray(arr).save(path)


# ---------------------------------------------------------------------------
# Context factories
# ---------------------------------------------------------------------------

def _ctx(mean: float = 30.0, stddev: float = 8.0, n: int = 50) -> DatasetContext:
    """Return a realistic DatasetContext with the given texture baseline."""
    return DatasetContext(
        schema_version=CONTEXT_SCHEMA_VERSION,
        analyzer_versions={"texture_analyzer": "v1"},
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
            mean=mean, stddev=stddev, p10=mean - stddev, p90=mean + stddev,
            sample_count=n,
        ),
        frequency_distributions=FrequencyDistributions(
            dominant_freq_mean=0.1, dominant_freq_stddev=0.02, sample_count=n,
        ),
        duplicate_hashes=frozenset(),
        duplicate_groups=(),
    )


def _empty_dist_ctx() -> DatasetContext:
    """Context with zero-sample texture distributions — no baseline."""
    return DatasetContext(
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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestTextureAnalyzerContract(unittest.TestCase):
    def setUp(self):
        self.analyzer = TextureAnalyzer()

    def test_name(self):
        self.assertEqual(self.analyzer.name, "texture_analyzer")

    def test_version(self):
        self.assertEqual(self.analyzer.version, "v1")

    def test_analyzer_id(self):
        self.assertEqual(self.analyzer.analyzer_id, "texture_analyzer/v1")

    def test_supported_categories(self):
        cats = self.analyzer.supported_categories
        self.assertIn("texture.high_microtexture", cats)
        self.assertIn("texture.error", cats)

    def test_benchmark_version_is_none_until_calibrated(self):
        self.assertIsNone(self.analyzer.benchmark_version)


class TestTextureAnalyzerSmoothImage(unittest.TestCase):
    def setUp(self):
        self.analyzer = TextureAnalyzer()
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "smooth.png"
        _write_smooth_image(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_smooth_image_produces_no_findings(self):
        # Smooth image score will be far below the dataset mean of 30
        ctx = _ctx(mean=30.0, stddev=8.0)
        findings = self.analyzer.analyze(self.path, ctx)
        self.assertEqual(findings, [])

    def test_returns_list(self):
        findings = self.analyzer.analyze(self.path, _ctx())
        self.assertIsInstance(findings, list)


    def test_provided_measurements_preserve_behavior(self):
        ctx = _ctx(mean=30.0, stddev=8.0)
        measurements = measure_image(self.path)
        self.assertEqual(
            self.analyzer.analyze(self.path, ctx),
            self.analyzer.analyze(self.path, ctx, measurements=measurements),
        )


class TestTextureAnalyzerNoisyImage(unittest.TestCase):
    def setUp(self):
        self.analyzer = TextureAnalyzer()
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "noisy.png"
        _write_noisy_image(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_noisy_image_produces_finding(self):
        # Dataset mean=30, stddev=5 → noisy image (~100 score) is a massive outlier
        ctx = _ctx(mean=30.0, stddev=5.0)
        findings = self.analyzer.analyze(self.path, ctx)
        self.assertGreater(len(findings), 0)

    def test_finding_has_correct_category(self):
        ctx = _ctx(mean=30.0, stddev=5.0)
        findings = self.analyzer.analyze(self.path, ctx)
        self.assertEqual(findings[0].category, "texture.high_microtexture")

    def test_finding_severity_is_high_or_critical(self):
        ctx = _ctx(mean=30.0, stddev=5.0)
        findings = self.analyzer.analyze(self.path, ctx)
        self.assertGreaterEqual(findings[0].severity, Severity.HIGH)

    def test_finding_confidence_in_range(self):
        ctx = _ctx(mean=30.0, stddev=5.0)
        findings = self.analyzer.analyze(self.path, ctx)
        c = findings[0].confidence
        self.assertGreater(c, 0.0)
        self.assertLessEqual(c, 1.0)

    def test_finding_is_finding_instance(self):
        ctx = _ctx(mean=30.0, stddev=5.0)
        findings = self.analyzer.analyze(self.path, ctx)
        self.assertIsInstance(findings[0], Finding)

    def test_finding_analyzer_id(self):
        ctx = _ctx(mean=30.0, stddev=5.0)
        findings = self.analyzer.analyze(self.path, ctx)
        self.assertEqual(findings[0].analyzer, "texture_analyzer/v1")

    def test_finding_evidence_contains_z_score(self):
        ctx = _ctx(mean=30.0, stddev=5.0)
        findings = self.analyzer.analyze(self.path, ctx)
        self.assertIn("z_score", findings[0].evidence)
        self.assertGreater(findings[0].evidence["z_score"], 2.0)

    def test_finding_evidence_calibrated_flag_is_false(self):
        ctx = _ctx(mean=30.0, stddev=5.0)
        findings = self.analyzer.analyze(self.path, ctx)
        self.assertFalse(findings[0].evidence["calibrated"])

    def test_finding_evidence_contains_stable_keys(self):
        ctx = _ctx(mean=30.0, stddev=5.0)
        findings = self.analyzer.analyze(self.path, ctx)
        ev = findings[0].evidence
        for key in (
            "microtexture_density",
            "dataset_mean",
            "dataset_stddev",
            "z_score",
            "dataset_p10",
            "dataset_p90",
            "watercolor_smoothness",
            "highlight_speck",
            "calibrated",
        ):
            self.assertIn(key, ev, f"Missing evidence key: {key}")

    def test_finding_evidence_is_json_serializable(self):
        ctx = _ctx(mean=30.0, stddev=5.0)
        findings = self.analyzer.analyze(self.path, ctx)
        json.dumps(findings[0].evidence)

    def test_finding_explanation_is_advisory_not_overclaimed(self):
        ctx = _ctx(mean=30.0, stddev=5.0)
        findings = self.analyzer.analyze(self.path, ctx)
        text = findings[0].explanation
        self.assertIn("review signal Dataset Forge currently watches for", text)
        self.assertIn("AI-like surface texture", text)
        self.assertIn("compression", text)
        self.assertIn("intentional illustration texture", text)
        self.assertNotIn("common GPT image artifact", text)

    def test_finding_image_path_matches(self):
        ctx = _ctx(mean=30.0, stddev=5.0)
        findings = self.analyzer.analyze(self.path, ctx)
        self.assertEqual(findings[0].image_path, self.path)


    def test_provided_measurements_preserve_finding(self):
        ctx = _ctx(mean=30.0, stddev=5.0)
        measurements = measure_image(self.path)
        self.assertEqual(
            self.analyzer.analyze(self.path, ctx),
            self.analyzer.analyze(self.path, ctx, measurements=measurements),
        )


class TestTextureAnalyzerEdgeCases(unittest.TestCase):
    def setUp(self):
        self.analyzer = TextureAnalyzer()
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_no_baseline_returns_empty(self):
        """Without dataset statistics, emit nothing rather than guess."""
        p = Path(self.tmp.name) / "noisy.png"
        _write_noisy_image(p)
        findings = self.analyzer.analyze(p, _empty_dist_ctx())
        self.assertEqual(findings, [])

    def test_missing_file_returns_error_finding(self):
        p = Path(self.tmp.name) / "does_not_exist.png"
        findings = self.analyzer.analyze(p, _ctx())
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].category, "texture.error")
        self.assertEqual(findings[0].severity, Severity.LOW)

    def test_noisy_image_within_normal_dataset_no_finding(self):
        """If the whole dataset is noisy, a noisy image is not an outlier."""
        p = Path(self.tmp.name) / "noisy.png"
        _write_mild_noise_image(p, noise_level=20)
        # Dataset mean very high, large stddev — mild noise image is unremarkable
        ctx = _ctx(mean=80.0, stddev=20.0)
        findings = self.analyzer.analyze(p, ctx)
        self.assertEqual(findings, [])


    def test_provided_measurements_skip_direct_texture_evaluation(self):
        p = Path(self.tmp.name) / "noisy.png"
        _write_noisy_image(p)
        measurements = measure_image(p)
        with patch(
            "dataset_forge.analyzers.texture.evaluate_texture",
            side_effect=AssertionError("analyzer remeasured image"),
        ):
            findings = self.analyzer.analyze(
                p,
                _ctx(mean=30.0, stddev=5.0),
                measurements=measurements,
            )
        self.assertGreater(len(findings), 0)


class TestZToSeverity(unittest.TestCase):
    def test_below_threshold(self):
        self.assertEqual(_z_to_severity(0.5), Severity.NONE)

    def test_medium_threshold(self):
        self.assertEqual(_z_to_severity(1.0), Severity.MEDIUM)

    def test_high_threshold(self):
        self.assertEqual(_z_to_severity(2.0), Severity.HIGH)

    def test_critical_threshold(self):
        self.assertEqual(_z_to_severity(3.0), Severity.CRITICAL)

    def test_extreme_value(self):
        self.assertEqual(_z_to_severity(10.0), Severity.CRITICAL)


if __name__ == "__main__":
    unittest.main()
