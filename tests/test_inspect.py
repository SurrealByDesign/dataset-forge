"""End-to-end tests for the v1 inspect pipeline.

Creates real synthetic images in temporary directories so the full
DatasetContext → TextureAnalyzer → Finding → Report chain runs
against actual pixel data, not stubs.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

from dataset_forge.analyzers.registry import analyzer_versions
from dataset_forge.inspect import InspectResult, run_inspect
from dataset_forge.measurements import measure_image as real_measure_image


# ---------------------------------------------------------------------------
# Image factories
# ---------------------------------------------------------------------------

def _write_smooth(path: Path, n: int = 1) -> list[Path]:
    """Write n solid-grey images. Near-zero microtexture."""
    written = []
    for i in range(n):
        p = path / f"smooth_{i:03d}.png"
        arr = np.full((256, 256, 3), 128, dtype=np.uint8)
        Image.fromarray(arr).save(p)
        written.append(p)
    return written


def _write_noisy(path: Path, n: int = 1) -> list[Path]:
    """Write n random-noise images. Very high microtexture."""
    written = []
    rng = np.random.default_rng(99)
    for i in range(n):
        p = path / f"noisy_{i:03d}.png"
        arr = rng.integers(0, 255, size=(256, 256, 3), dtype=np.uint8)
        Image.fromarray(arr).save(p)
        written.append(p)
    return written


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRunInspectBasic(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dataset = Path(self.tmp.name) / "dataset"
        self.output = Path(self.tmp.name) / "output"
        self.dataset.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_returns_inspect_result(self):
        _write_smooth(self.dataset, n=3)
        result = run_inspect(self.dataset, self.output)
        self.assertIsInstance(result, InspectResult)

    def test_image_count(self):
        _write_smooth(self.dataset, n=5)
        result = run_inspect(self.dataset, self.output)
        self.assertEqual(result.image_count, 5)

    def test_no_errors_on_valid_images(self):
        _write_smooth(self.dataset, n=3)
        result = run_inspect(self.dataset, self.output)
        self.assertEqual(result.error_count, 0)

    def test_json_report_written(self):
        _write_smooth(self.dataset, n=2)
        result = run_inspect(self.dataset, self.output)
        self.assertTrue(result.json_report.exists())

    def test_txt_report_written(self):
        _write_smooth(self.dataset, n=2)
        result = run_inspect(self.dataset, self.output)
        self.assertTrue(result.txt_report.exists())

    def test_recommendation_json_written(self):
        _write_smooth(self.dataset, n=2)
        result = run_inspect(self.dataset, self.output)
        self.assertTrue(result.recommendation_json.exists())

    def test_recommendation_markdown_written(self):
        _write_smooth(self.dataset, n=2)
        result = run_inspect(self.dataset, self.output)
        self.assertTrue(result.recommendation_markdown.exists())

    def test_existing_inspection_outputs_remain_present(self):
        _write_smooth(self.dataset, n=2)
        result = run_inspect(self.dataset, self.output)

        self.assertTrue(result.json_report.exists())
        self.assertTrue(result.txt_report.exists())
        self.assertTrue(result.recommendation_json.exists())
        self.assertTrue(result.recommendation_markdown.exists())

    def test_review_gallery_not_written_by_default(self):
        _write_smooth(self.dataset, n=2)
        result = run_inspect(self.dataset, self.output)

        self.assertIsNone(result.review_gallery_path)
        self.assertFalse((self.output / "review_gallery.html").exists())

    def test_review_gallery_written_when_requested(self):
        _write_smooth(self.dataset, n=2)
        result = run_inspect(self.dataset, self.output, review_gallery=True)

        self.assertIsNotNone(result.review_gallery_path)
        assert result.review_gallery_path is not None
        self.assertTrue(result.review_gallery_path.exists())
        self.assertEqual(result.review_gallery_path.name, "review_gallery.html")

    def test_json_report_valid(self):
        _write_smooth(self.dataset, n=2)
        result = run_inspect(self.dataset, self.output)
        data = json.loads(result.json_report.read_text(encoding="utf-8"))
        self.assertIn("schema", data)
        self.assertIn("findings", data)
        self.assertIn("summary", data)

    def test_json_report_includes_oversharpening_analyzer_version(self):
        _write_smooth(self.dataset, n=2)
        result = run_inspect(self.dataset, self.output)
        data = json.loads(result.json_report.read_text(encoding="utf-8"))
        versions = data["context"]["analyzer_versions"]
        self.assertEqual(versions["oversharpening_halo_analyzer"], "v1")

    def test_json_report_includes_high_frequency_isolated_analyzer_version(self):
        _write_smooth(self.dataset, n=2)
        result = run_inspect(self.dataset, self.output)
        data = json.loads(result.json_report.read_text(encoding="utf-8"))
        versions = data["context"]["analyzer_versions"]
        self.assertEqual(
            versions["high_frequency_isolated_artifact_analyzer"],
            "v1",
        )

    def test_json_report_includes_complete_analyzer_versions(self):
        _write_smooth(self.dataset, n=2)
        result = run_inspect(self.dataset, self.output)
        data = json.loads(result.json_report.read_text(encoding="utf-8"))

        self.assertEqual(
            data["context"]["analyzer_versions"],
            analyzer_versions(),
        )

    def test_inspection_report_schema_is_unchanged(self):
        _write_smooth(self.dataset, n=2)
        result = run_inspect(self.dataset, self.output)
        data = json.loads(result.json_report.read_text(encoding="utf-8"))

        self.assertEqual(data["schema"], "dataset-forge/inspection/v1")
        self.assertNotIn("recommendation_summary", data)
        self.assertNotIn("review_gallery", data)

    def test_inspect_uses_analyzer_registry(self):
        class RecordingAnalyzer:
            name = "recording_analyzer"
            version = "v1"

            def analyze(self, image_path, context, measurements=None):
                del image_path, context, measurements
                return []

        _write_smooth(self.dataset, n=1)
        with patch(
            "dataset_forge.inspect.create_analyzers",
            return_value=[RecordingAnalyzer()],
        ) as create_mock:
            result = run_inspect(self.dataset, self.output)

        self.assertEqual(result.total_findings, 0)
        create_mock.assert_called_once_with()

    def test_invalid_path_raises(self):
        with self.assertRaises(ValueError):
            run_inspect(Path("/nonexistent/path"), self.output)

    def test_empty_dataset_runs_without_error(self):
        # No images — discovery returns nothing, pipeline handles gracefully
        result = run_inspect(self.dataset, self.output)
        self.assertEqual(result.image_count, 0)
        self.assertEqual(result.total_findings, 0)


    def test_texture_measurements_are_computed_once_per_image(self):
        paths = _write_smooth(self.dataset, n=4)
        with (
            patch(
                "dataset_forge.context_builder.measure_image",
                wraps=real_measure_image,
            ) as measure_mock,
            patch(
                "dataset_forge.analyzers.texture.evaluate_texture",
                side_effect=AssertionError("TextureAnalyzer remeasured image"),
            ),
            patch(
                "dataset_forge.analyzers.crystalline.evaluate_texture",
                side_effect=AssertionError("CrystallineAnalyzer remeasured image"),
            ),
        ):
            result = run_inspect(self.dataset, self.output)

        self.assertEqual(result.image_count, len(paths))
        self.assertEqual(measure_mock.call_count, len(paths))


class TestRunInspectCleanDataset(unittest.TestCase):
    """Smooth images should produce few or no texture findings."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dataset = Path(self.tmp.name) / "dataset"
        self.output = Path(self.tmp.name) / "output"
        self.dataset.mkdir()
        _write_smooth(self.dataset, n=10)

    def tearDown(self):
        self.tmp.cleanup()

    def test_images_clean_count(self):
        result = run_inspect(self.dataset, self.output)
        # Smooth images score very low — all should be below dataset mean
        self.assertEqual(result.images_clean, result.image_count)

    def test_total_findings_zero_for_uniform_smooth(self):
        result = run_inspect(self.dataset, self.output)
        self.assertEqual(result.total_findings, 0)

    def test_images_with_findings_zero(self):
        result = run_inspect(self.dataset, self.output)
        self.assertEqual(result.images_with_findings, 0)

    def test_json_images_clean_matches(self):
        result = run_inspect(self.dataset, self.output)
        data = json.loads(result.json_report.read_text(encoding="utf-8"))
        self.assertEqual(data["summary"]["images_clean"], result.image_count)


class TestRunInspectNoisyDataset(unittest.TestCase):
    """Mixed dataset: mostly smooth + a few noisy outliers → findings on noisy."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dataset = Path(self.tmp.name) / "dataset"
        self.output = Path(self.tmp.name) / "output"
        self.dataset.mkdir()
        # 8 smooth + 2 very noisy — noisy images should be outliers
        _write_smooth(self.dataset, n=8)
        _write_noisy(self.dataset, n=2)

    def tearDown(self):
        self.tmp.cleanup()

    def test_image_count(self):
        result = run_inspect(self.dataset, self.output)
        self.assertEqual(result.image_count, 10)

    def test_findings_present(self):
        result = run_inspect(self.dataset, self.output)
        self.assertGreater(result.total_findings, 0)

    def test_noisy_images_flagged(self):
        result = run_inspect(self.dataset, self.output)
        self.assertGreater(result.images_with_findings, 0)

    def test_clean_images_present(self):
        result = run_inspect(self.dataset, self.output)
        self.assertGreater(result.images_clean, 0)

    def test_clean_plus_affected_equals_total(self):
        result = run_inspect(self.dataset, self.output)
        self.assertEqual(
            result.images_clean + result.images_with_findings,
            result.image_count,
        )

    def test_json_findings_have_required_fields(self):
        result = run_inspect(self.dataset, self.output)
        data = json.loads(result.json_report.read_text(encoding="utf-8"))
        if data["findings"]:
            f = data["findings"][0]
            for field in ("image_path", "analyzer", "category", "severity",
                          "confidence", "explanation", "recommendation"):
                self.assertIn(field, f)

    def test_txt_report_nonempty(self):
        result = run_inspect(self.dataset, self.output)
        txt = result.txt_report.read_text(encoding="utf-8")
        self.assertIn("Dataset Forge Inspection Report", txt)


class TestRunInspectDuplicates(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dataset = Path(self.tmp.name) / "dataset"
        self.output = Path(self.tmp.name) / "output"
        self.dataset.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_exact_duplicates_detected_in_context(self):
        # Write the same image content under two names
        arr = np.full((64, 64, 3), 100, dtype=np.uint8)
        img = Image.fromarray(arr)
        img.save(self.dataset / "copy_a.png")
        img.save(self.dataset / "copy_b.png")

        result = run_inspect(self.dataset, self.output)
        data = json.loads(result.json_report.read_text(encoding="utf-8"))
        self.assertGreater(data["context"]["exact_duplicate_count"], 0)


class TestInspectResultFields(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dataset = Path(self.tmp.name) / "dataset"
        self.output = Path(self.tmp.name) / "output"
        self.dataset.mkdir()
        _write_smooth(self.dataset, n=3)

    def tearDown(self):
        self.tmp.cleanup()

    def test_result_dataset_path(self):
        result = run_inspect(self.dataset, self.output)
        self.assertEqual(result.dataset_path, self.dataset)

    def test_result_output_dir(self):
        result = run_inspect(self.dataset, self.output)
        self.assertEqual(result.output_dir, self.output)

    def test_result_is_frozen(self):
        result = run_inspect(self.dataset, self.output)
        with self.assertRaises(Exception):
            result.image_count = 999  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
