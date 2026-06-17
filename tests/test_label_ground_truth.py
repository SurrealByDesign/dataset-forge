"""Tests for scripts/label_ground_truth.py.

Because the labeling session is interactive (calls ``input()``), tests
patch builtins.input to feed simulated keystrokes.  run_labeling_session()
is the unit under test; the CLI main() is exercised only for smoke tests.

Coverage:
  - JSON schema written correctly
  - Resumability (skip already-labeled, re-label with --review)
  - Label routing (A→ARTIFACT, C→CLEAN, U→UNCERTAIN)
  - Skip (S) and quit (Q) mid-session
  - Notes attached to labels
  - Metrics extracted from findings index
  - Clean images (not in findings) get null metrics
  - Output file written after every label
  - Excluded output sub-directories are not offered for labeling
  - ground_truth.json can be loaded again by _load_ground_truth
  - dataset_path and report_path recorded in output
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

# Allow import from repo src/ and scripts/
_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "src"))
sys.path.insert(0, str(_REPO / "scripts"))

from label_ground_truth import (
    GROUND_TRUTH_SCHEMA,
    VALID_LABELS,
    _build_findings_index,
    _extract_metrics,
    _is_excluded,
    _load_ground_truth,
    run_labeling_session,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _write_image(path: Path) -> None:
    Image.fromarray(
        np.full((32, 32, 3), 128, dtype=np.uint8)
    ).save(path)


def _minimal_report(dataset_path: Path, findings: list[dict] | None = None) -> dict:
    return {
        "schema": "dataset-forge/inspection/v1",
        "generated_at": "2026-06-16T00:00:00Z",
        "dataset_path": str(dataset_path),
        "context": {
            "total_images": 1,
            "analyzed_images": 1,
            "error_images": 0,
            "texture_distributions": {"mean": 40.0, "stddev": 10.0,
                                       "p10": 30.0, "p90": 50.0,
                                       "sample_count": 1},
        },
        "findings": findings or [],
        "summary": {"total_findings": 0, "images_with_findings": 0,
                    "images_clean": 1, "severity_counts": {}},
    }


def _finding_entry(image_name: str, severity: str = "MEDIUM") -> dict:
    return {
        "image_path": image_name,
        "analyzer": "texture_analyzer/v1",
        "category": "texture.high_microtexture",
        "severity": severity,
        "confidence": 0.65,
        "false_positive_rate": 0.15,
        "benchmark_version": "uncalibrated",
        "evidence": {
            "microtexture_density": 58.2,
            "z_score": 1.57,
            "watercolor_smoothness": 34.1,
            "highlight_speck": 5.3,
            "calibrated": False,
        },
        "explanation": "High microtexture.",
        "recommendation": "Review.",
        "schema": "dataset-forge/finding/v1",
    }


def _write_report(path: Path, report: dict) -> None:
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# _load_ground_truth
# ---------------------------------------------------------------------------

class TestLoadGroundTruth(unittest.TestCase):

    def test_returns_skeleton_when_file_missing(self):
        gt = _load_ground_truth(Path("/nonexistent/ground_truth.json"))
        self.assertEqual(gt["schema"], GROUND_TRUTH_SCHEMA)
        self.assertIn("labels", gt)

    def test_returns_skeleton_when_schema_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "gt.json"
            p.write_text(json.dumps({"schema": "wrong/v99", "labels": {}}),
                         encoding="utf-8")
            gt = _load_ground_truth(p)
            self.assertEqual(gt["schema"], GROUND_TRUTH_SCHEMA)

    def test_loads_existing_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "gt.json"
            data = {
                "schema": GROUND_TRUTH_SCHEMA,
                "labels": {"img.png": {"label": "ARTIFACT"}},
            }
            p.write_text(json.dumps(data), encoding="utf-8")
            gt = _load_ground_truth(p)
            self.assertEqual(gt["labels"]["img.png"]["label"], "ARTIFACT")


# ---------------------------------------------------------------------------
# _build_findings_index
# ---------------------------------------------------------------------------

class TestBuildFindingsIndex(unittest.TestCase):

    def test_empty_findings_returns_empty_dict(self):
        idx = _build_findings_index({"findings": []})
        self.assertEqual(idx, {})

    def test_finding_indexed_by_filename(self):
        report = {"findings": [_finding_entry("img_001.png", "HIGH")]}
        idx = _build_findings_index(report)
        self.assertIn("img_001.png", idx)

    def test_finding_indexed_by_basename_only(self):
        f = _finding_entry("/abs/path/img_002.png", "MEDIUM")
        idx = _build_findings_index({"findings": [f]})
        self.assertIn("img_002.png", idx)
        self.assertNotIn("/abs/path/img_002.png", idx)

    def test_multiple_findings_all_indexed(self):
        report = {"findings": [
            _finding_entry("a.png"),
            _finding_entry("b.png"),
        ]}
        idx = _build_findings_index(report)
        self.assertIn("a.png", idx)
        self.assertIn("b.png", idx)


# ---------------------------------------------------------------------------
# _extract_metrics
# ---------------------------------------------------------------------------

class TestExtractMetrics(unittest.TestCase):

    def test_none_finding_returns_null_metrics(self):
        m = _extract_metrics(None)
        self.assertIsNone(m["severity"])
        self.assertIsNone(m["micro"])
        self.assertIsNone(m["z"])

    def test_finding_severity_extracted(self):
        m = _extract_metrics(_finding_entry("img.png", "HIGH"))
        self.assertEqual(m["severity"], "HIGH")

    def test_evidence_values_extracted(self):
        m = _extract_metrics(_finding_entry("img.png"))
        self.assertAlmostEqual(m["micro"], 58.2)
        self.assertAlmostEqual(m["z"], 1.57)
        self.assertAlmostEqual(m["smooth"], 34.1)
        self.assertAlmostEqual(m["speck"], 5.3)


# ---------------------------------------------------------------------------
# _is_excluded
# ---------------------------------------------------------------------------

class TestIsExcluded(unittest.TestCase):

    def setUp(self):
        self.root = Path("/dataset")

    def test_inspect_output_excluded(self):
        self.assertTrue(
            _is_excluded(self.root / "inspect_output" / "img.png", self.root)
        )

    def test_normal_image_not_excluded(self):
        self.assertFalse(
            _is_excluded(self.root / "img.png", self.root)
        )

    def test_output_dir_excluded(self):
        self.assertTrue(
            _is_excluded(self.root / "output" / "img.png", self.root)
        )

    def test_nested_normal_subdir_not_excluded(self):
        self.assertFalse(
            _is_excluded(self.root / "subfolder" / "img.png", self.root)
        )


# ---------------------------------------------------------------------------
# run_labeling_session — core behaviour
# ---------------------------------------------------------------------------

class TestRunLabelingSession(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.dataset = self.root / "dataset"
        self.dataset.mkdir()
        self.output_dir = self.root / "out"
        self.output_dir.mkdir()
        self.gt_path = self.root / "ground_truth.json"
        self.report_path = self.root / "report.json"

    def tearDown(self):
        self.tmp.cleanup()

    def _write_images(self, names: list[str]) -> None:
        for n in names:
            _write_image(self.dataset / n)

    def _write_report(self, findings: list[dict] | None = None) -> None:
        _write_report(
            self.report_path,
            _minimal_report(self.dataset, findings),
        )

    def _run(self, inputs: list[str], *, review: bool = False) -> dict:
        """Run a session with the given sequence of simulated input() responses."""
        responses = iter(inputs)
        with patch("builtins.input", side_effect=lambda _prompt="": next(responses)):
            return run_labeling_session(
                self.dataset,
                self.report_path,
                self.gt_path,
                review=review,
                preview=False,  # never open OS viewer during tests
            )

    # ---- output file structure -----------------------------------------

    def test_output_file_written(self):
        self._write_images(["img_001.png"])
        self._write_report()
        self._run(["a", ""])    # label ARTIFACT, no note
        self.assertTrue(self.gt_path.exists())

    def test_schema_field_correct(self):
        self._write_images(["img_001.png"])
        self._write_report()
        gt = self._run(["c", ""])
        self.assertEqual(gt["schema"], GROUND_TRUTH_SCHEMA)

    def test_dataset_path_recorded(self):
        self._write_images(["img_001.png"])
        self._write_report()
        gt = self._run(["c", ""])
        self.assertEqual(Path(gt["dataset_path"]).resolve(), self.dataset.resolve())

    def test_report_path_recorded(self):
        self._write_images(["img_001.png"])
        self._write_report()
        gt = self._run(["c", ""])
        self.assertEqual(Path(gt["report_path"]).resolve(), self.report_path.resolve())

    def test_labeled_by_is_human(self):
        self._write_images(["img_001.png"])
        self._write_report()
        gt = self._run(["c", ""])
        self.assertEqual(gt["labeled_by"], "human")

    # ---- label routing ------------------------------------------------

    def test_a_maps_to_artifact(self):
        self._write_images(["img_001.png"])
        self._write_report()
        gt = self._run(["a", ""])
        self.assertEqual(gt["labels"]["img_001.png"]["label"], "ARTIFACT")

    def test_c_maps_to_clean(self):
        self._write_images(["img_001.png"])
        self._write_report()
        gt = self._run(["c", ""])
        self.assertEqual(gt["labels"]["img_001.png"]["label"], "CLEAN")

    def test_u_maps_to_uncertain(self):
        self._write_images(["img_001.png"])
        self._write_report()
        gt = self._run(["u", ""])
        self.assertEqual(gt["labels"]["img_001.png"]["label"], "UNCERTAIN")

    def test_full_word_artifact_accepted(self):
        self._write_images(["img_001.png"])
        self._write_report()
        gt = self._run(["ARTIFACT", ""])
        self.assertEqual(gt["labels"]["img_001.png"]["label"], "ARTIFACT")

    # ---- notes ---------------------------------------------------------

    def test_note_stored_with_label(self):
        self._write_images(["img_001.png"])
        self._write_report()
        gt = self._run(["a", "clear glitter speckle"])
        self.assertEqual(gt["labels"]["img_001.png"]["notes"], "clear glitter speckle")

    def test_empty_note_stored(self):
        self._write_images(["img_001.png"])
        self._write_report()
        gt = self._run(["c", ""])
        self.assertEqual(gt["labels"]["img_001.png"]["notes"], "")

    # ---- skip ----------------------------------------------------------

    def test_s_skips_without_labeling(self):
        self._write_images(["img_001.png"])
        self._write_report()
        gt = self._run(["s"])
        self.assertNotIn("img_001.png", gt["labels"])

    def test_skip_preserves_existing_label(self):
        self._write_images(["img_001.png", "img_002.png"])
        self._write_report()
        # Label first, skip second
        gt = self._run(["a", "", "s"])
        self.assertIn("img_001.png", gt["labels"])
        self.assertNotIn("img_002.png", gt["labels"])

    # ---- quit ----------------------------------------------------------

    def test_q_stops_session(self):
        self._write_images(["img_001.png", "img_002.png"])
        self._write_report()
        # Quit before labeling anything
        gt = self._run(["q"])
        self.assertNotIn("img_001.png", gt["labels"])

    def test_q_saves_labels_already_made(self):
        self._write_images(["img_001.png", "img_002.png"])
        self._write_report()
        gt = self._run(["a", "", "q"])  # label first, quit before second
        self.assertIn("img_001.png", gt["labels"])
        self.assertNotIn("img_002.png", gt["labels"])

    # ---- resumability --------------------------------------------------

    def test_already_labeled_skipped_by_default(self):
        self._write_images(["img_001.png", "img_002.png"])
        self._write_report()
        # First session: label both
        self._run(["a", "", "c", ""])
        # Second session: nothing to label — no input needed
        gt2 = self._run([])
        # Both labels still present, unchanged
        self.assertEqual(gt2["labels"]["img_001.png"]["label"], "ARTIFACT")
        self.assertEqual(gt2["labels"]["img_002.png"]["label"], "CLEAN")

    def test_review_flag_re_presents_labeled_images(self):
        self._write_images(["img_001.png"])
        self._write_report()
        # First label: ARTIFACT
        self._run(["a", ""])
        # Review: change to CLEAN
        gt = self._run(["c", "new note"], review=True)
        self.assertEqual(gt["labels"]["img_001.png"]["label"], "CLEAN")
        self.assertEqual(gt["labels"]["img_001.png"]["notes"], "new note")

    # ---- metrics from findings -----------------------------------------

    def test_finding_metrics_stored_with_label(self):
        self._write_images(["img_001.png"])
        self._write_report(findings=[_finding_entry("img_001.png", "HIGH")])
        gt = self._run(["a", ""])
        entry = gt["labels"]["img_001.png"]
        self.assertEqual(entry["severity_from_report"], "HIGH")
        self.assertAlmostEqual(entry["micro"], 58.2)
        self.assertAlmostEqual(entry["z"], 1.57)

    def test_clean_image_has_null_metrics(self):
        self._write_images(["img_001.png"])
        self._write_report(findings=[])   # image not in findings
        gt = self._run(["c", ""])
        entry = gt["labels"]["img_001.png"]
        self.assertIsNone(entry["severity_from_report"])
        self.assertIsNone(entry["micro"])

    def test_labeled_at_timestamp_present(self):
        self._write_images(["img_001.png"])
        self._write_report()
        gt = self._run(["c", ""])
        self.assertIn("labeled_at", gt["labels"]["img_001.png"])

    # ---- multiple images -----------------------------------------------

    def test_all_images_can_be_labeled_in_one_session(self):
        names = [f"img_{i:03d}.png" for i in range(5)]
        self._write_images(names)
        self._write_report()
        # 5 images × (label + note)
        inputs = []
        for _ in names:
            inputs += ["a", ""]
        gt = self._run(inputs)
        for n in names:
            self.assertIn(n, gt["labels"])

    def test_empty_dataset_returns_empty_labels(self):
        self._write_report()
        gt = self._run([])
        self.assertEqual(gt["labels"], {})

    # ---- file saved incrementally --------------------------------------

    def test_file_saved_after_first_label(self):
        self._write_images(["img_001.png", "img_002.png"])
        self._write_report()

        save_calls: list[str] = []
        original_input_responses = iter(["a", "", "q"])

        import label_ground_truth as lgt
        original_save = lgt._save_ground_truth

        def tracking_save(data, path):
            save_calls.append(path.name)
            original_save(data, path)

        with patch("builtins.input", side_effect=lambda _p="": next(original_input_responses)):
            with patch.object(lgt, "_save_ground_truth", side_effect=tracking_save):
                run_labeling_session(
                    self.dataset,
                    self.report_path,
                    self.gt_path,
                    preview=False,
                )

        # Should have been saved at least once (after the label) + once at end
        self.assertGreaterEqual(len(save_calls), 1)

    # ---- excluded dirs -------------------------------------------------

    def test_inspect_output_images_not_offered(self):
        inspect_out = self.dataset / "inspect_output"
        inspect_out.mkdir()
        _write_image(inspect_out / "inspection_report_thumb.png")
        _write_image(self.dataset / "real_img.png")
        self._write_report()

        gt = self._run(["c", ""])
        # Only real_img.png should have been offered and labeled
        self.assertIn("real_img.png", gt["labels"])
        self.assertNotIn("inspection_report_thumb.png", gt["labels"])


# ---------------------------------------------------------------------------
# Preview behavior
# ---------------------------------------------------------------------------

class TestPreviewBehavior(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.dataset = self.root / "dataset"
        self.dataset.mkdir()
        self.gt_path = self.root / "ground_truth.json"
        self.report_path = self.root / "report.json"
        _write_image(self.dataset / "img_001.png")
        _write_image(self.dataset / "img_002.png")
        _write_report(
            self.report_path,
            _minimal_report(self.dataset),
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_preview_calls_open_image_once_per_image(self):
        import label_ground_truth as lgt
        calls: list[Path] = []
        with patch.object(lgt, "_open_image", side_effect=calls.append):
            with patch("builtins.input", side_effect=iter(["a", "", "c", ""])):
                run_labeling_session(
                    self.dataset,
                    self.report_path,
                    self.gt_path,
                    preview=True,
                )
        self.assertEqual(len(calls), 2)

    def test_preview_false_never_calls_open_image(self):
        import label_ground_truth as lgt
        calls: list[Path] = []
        with patch.object(lgt, "_open_image", side_effect=calls.append):
            with patch("builtins.input", side_effect=iter(["a", "", "c", ""])):
                run_labeling_session(
                    self.dataset,
                    self.report_path,
                    self.gt_path,
                    preview=False,
                )
        self.assertEqual(len(calls), 0)

    def test_open_image_swallows_os_errors(self):
        """_open_image must never raise, even when the viewer command fails."""
        import label_ground_truth as lgt
        # Patch the underlying OS launcher to raise; _open_image's try/except
        # must absorb it so the caller loop is never interrupted.
        with patch.object(lgt.os, "startfile", side_effect=OSError("no viewer")):
            with patch.object(lgt, "sys") as mock_sys:
                mock_sys.platform = "win32"
                # Should complete without raising
                lgt._open_image(self.dataset / "img_001.png")


# ---------------------------------------------------------------------------
# Round-trip: write and re-read ground_truth.json
# ---------------------------------------------------------------------------

class TestGroundTruthRoundTrip(unittest.TestCase):

    def test_written_json_is_valid_and_reloadable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root   = Path(tmp)
            ds     = root / "ds"
            ds.mkdir()
            _write_image(ds / "img.png")

            rpt = root / "report.json"
            _write_report(rpt, _minimal_report(ds))

            gt_path = root / "ground_truth.json"

            with patch("builtins.input", side_effect=iter(["c", "nice image"])):
                run_labeling_session(ds, rpt, gt_path, preview=False)

            raw  = json.loads(gt_path.read_text(encoding="utf-8"))
            self.assertEqual(raw["schema"], GROUND_TRUTH_SCHEMA)
            self.assertIn("img.png", raw["labels"])
            self.assertEqual(raw["labels"]["img.png"]["label"], "CLEAN")
            self.assertEqual(raw["labels"]["img.png"]["notes"], "nice image")

            # Reload via the module's own loader
            reloaded = _load_ground_truth(gt_path)
            self.assertEqual(reloaded["labels"]["img.png"]["label"], "CLEAN")


if __name__ == "__main__":
    unittest.main()
