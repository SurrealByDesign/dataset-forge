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

import numpy as np
from PIL import Image

from dataset_forge.inspect import InspectResult, run_inspect


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

    def test_json_report_valid(self):
        _write_smooth(self.dataset, n=2)
        result = run_inspect(self.dataset, self.output)
        data = json.loads(result.json_report.read_text(encoding="utf-8"))
        self.assertIn("schema", data)
        self.assertIn("findings", data)
        self.assertIn("summary", data)

    def test_invalid_path_raises(self):
        with self.assertRaises(ValueError):
            run_inspect(Path("/nonexistent/path"), self.output)

    def test_empty_dataset_runs_without_error(self):
        # No images — discovery returns nothing, pipeline handles gracefully
        result = run_inspect(self.dataset, self.output)
        self.assertEqual(result.image_count, 0)
        self.assertEqual(result.total_findings, 0)


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
