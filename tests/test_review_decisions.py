"""Tests for scripts/review_decisions.py.

The session is interactive (calls input()), so tests patch builtins.input.
run_review_session() is the unit under test.

Coverage:
  - Schema written correctly
  - Resumability (skip already-reviewed, re-review with --review)
  - Review routing (A→AGREE, D→DISAGREE, U→UNSURE, full words)
  - Skip (S) and quit (Q) mid-session
  - Notes attached to reviews
  - df_decision set to FINDING for flagged images, CLEAN for clean
  - Severity and metrics stored from findings index
  - Clean images get null severity/metrics
  - Output file written after every review
  - Excluded output sub-directories are not offered for review
  - decision_review.json can be reloaded by _load_review_file
  - Preview behavior (called/not-called, errors swallowed)
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

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "src"))
sys.path.insert(0, str(_REPO / "scripts"))

from review_decisions import (
    DECISION_REVIEW_SCHEMA,
    VALID_REVIEWS,
    _PreviewWindow,
    _build_crystalline_index,
    _build_findings_index,
    _extract_crystalline_evidence,
    _extract_metrics,
    _is_excluded,
    _load_review_file,
    run_review_session,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _write_image(path: Path) -> None:
    Image.fromarray(
        np.full((32, 32, 3), 128, dtype=np.uint8)
    ).save(path)


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


def _crystalline_finding_entry(
    image_name: str,
    grain: float = 50.0,
    smooth: float = 45.0,
    micro: float = 38.0,
) -> dict:
    return {
        "image_path": image_name,
        "analyzer": "crystalline_faceting_analyzer/v1",
        "category": "artifact.crystalline_faceting",
        "severity": "MEDIUM",
        "confidence": 0.45,
        "false_positive_rate": 0.28,
        "benchmark_version": "uncalibrated",
        "evidence": {
            "pencil_grain_score": grain,
            "watercolor_smoothness_score": smooth,
            "microtexture_density_score": micro,
            "grain_threshold": 45.0,
            "smoothness_ceiling": 52.0,
            "micro_floor": 20.0,
            "calibrated": False,
        },
        "explanation": "Crystalline faceting detected.",
        "recommendation": "Review manually.",
        "schema": "dataset-forge/finding/v1",
    }


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


def _write_report(path: Path, report: dict) -> None:
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# _load_review_file
# ---------------------------------------------------------------------------

class TestLoadReviewFile(unittest.TestCase):

    def test_returns_skeleton_when_file_missing(self):
        rv = _load_review_file(Path("/nonexistent/decision_review.json"))
        self.assertEqual(rv["schema"], DECISION_REVIEW_SCHEMA)
        self.assertIn("reviews", rv)

    def test_returns_skeleton_when_schema_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "rv.json"
            p.write_text(json.dumps({"schema": "wrong/v99", "reviews": {}}),
                         encoding="utf-8")
            rv = _load_review_file(p)
            self.assertEqual(rv["schema"], DECISION_REVIEW_SCHEMA)

    def test_loads_existing_reviews(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "rv.json"
            data = {
                "schema": DECISION_REVIEW_SCHEMA,
                "reviews": {"img.png": {"review": "AGREE"}},
            }
            p.write_text(json.dumps(data), encoding="utf-8")
            rv = _load_review_file(p)
            self.assertEqual(rv["reviews"]["img.png"]["review"], "AGREE")


# ---------------------------------------------------------------------------
# _build_findings_index
# ---------------------------------------------------------------------------

class TestBuildFindingsIndex(unittest.TestCase):

    def test_empty_report_returns_empty(self):
        self.assertEqual(_build_findings_index({"findings": []}), {})

    def test_finding_keyed_by_basename(self):
        idx = _build_findings_index({"findings": [_finding_entry("/abs/img.png")]})
        self.assertIn("img.png", idx)

    def test_multiple_findings_indexed(self):
        idx = _build_findings_index({"findings": [
            _finding_entry("a.png"), _finding_entry("b.png"),
        ]})
        self.assertIn("a.png", idx)
        self.assertIn("b.png", idx)


# ---------------------------------------------------------------------------
# _extract_metrics
# ---------------------------------------------------------------------------

class TestExtractMetrics(unittest.TestCase):

    def test_none_returns_all_null(self):
        m = _extract_metrics(None)
        for k in ("severity", "micro", "z", "smooth", "speck"):
            self.assertIsNone(m[k])

    def test_severity_extracted(self):
        self.assertEqual(_extract_metrics(_finding_entry("img.png", "HIGH"))["severity"], "HIGH")

    def test_evidence_values_extracted(self):
        m = _extract_metrics(_finding_entry("img.png"))
        self.assertAlmostEqual(m["micro"], 58.2)
        self.assertAlmostEqual(m["z"], 1.57)


# ---------------------------------------------------------------------------
# _is_excluded
# ---------------------------------------------------------------------------

class TestIsExcluded(unittest.TestCase):

    def setUp(self):
        self.root = Path("/dataset")

    def test_inspect_output_excluded(self):
        self.assertTrue(_is_excluded(self.root / "inspect_output" / "x.png", self.root))

    def test_normal_image_not_excluded(self):
        self.assertFalse(_is_excluded(self.root / "img.png", self.root))

    def test_output_excluded(self):
        self.assertTrue(_is_excluded(self.root / "output" / "x.png", self.root))

    def test_normal_subdir_not_excluded(self):
        self.assertFalse(_is_excluded(self.root / "subfolder" / "img.png", self.root))


# ---------------------------------------------------------------------------
# run_review_session — core behaviour
# ---------------------------------------------------------------------------

class TestRunReviewSession(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.dataset = self.root / "dataset"
        self.dataset.mkdir()
        self.rv_path = self.root / "decision_review.json"
        self.report_path = self.root / "report.json"

    def tearDown(self):
        self.tmp.cleanup()

    def _write_images(self, names: list[str]) -> None:
        for n in names:
            _write_image(self.dataset / n)

    def _write_report(self, findings: list[dict] | None = None) -> None:
        _write_report(self.report_path, _minimal_report(self.dataset, findings))

    def _run(self, inputs: list[str], *, review: bool = False) -> dict:
        responses = iter(inputs)
        with patch("builtins.input", side_effect=lambda _p="": next(responses)):
            return run_review_session(
                self.dataset,
                self.report_path,
                self.rv_path,
                review=review,
                preview=False,
            )

    # ---- output file structure ----------------------------------------

    def test_output_file_written(self):
        self._write_images(["img_001.png"])
        self._write_report()
        self._run(["a", ""])
        self.assertTrue(self.rv_path.exists())

    def test_schema_correct(self):
        self._write_images(["img_001.png"])
        self._write_report()
        rv = self._run(["a", ""])
        self.assertEqual(rv["schema"], DECISION_REVIEW_SCHEMA)

    def test_dataset_path_recorded(self):
        self._write_images(["img_001.png"])
        self._write_report()
        rv = self._run(["a", ""])
        self.assertEqual(Path(rv["dataset_path"]).resolve(), self.dataset.resolve())

    def test_report_path_recorded(self):
        self._write_images(["img_001.png"])
        self._write_report()
        rv = self._run(["a", ""])
        self.assertEqual(Path(rv["report_path"]).resolve(), self.report_path.resolve())

    def test_reviewed_by_is_human(self):
        self._write_images(["img_001.png"])
        self._write_report()
        rv = self._run(["a", ""])
        self.assertEqual(rv["reviewed_by"], "human")

    # ---- review routing ----------------------------------------------

    def test_a_maps_to_agree(self):
        self._write_images(["img_001.png"])
        self._write_report()
        rv = self._run(["a", ""])
        self.assertEqual(rv["reviews"]["img_001.png"]["review"], "AGREE")

    def test_d_maps_to_disagree(self):
        self._write_images(["img_001.png"])
        self._write_report()
        rv = self._run(["d", ""])
        self.assertEqual(rv["reviews"]["img_001.png"]["review"], "DISAGREE")

    def test_u_maps_to_unsure(self):
        self._write_images(["img_001.png"])
        self._write_report()
        rv = self._run(["u", ""])
        self.assertEqual(rv["reviews"]["img_001.png"]["review"], "UNSURE")

    def test_full_word_agree_accepted(self):
        self._write_images(["img_001.png"])
        self._write_report()
        rv = self._run(["AGREE", ""])
        self.assertEqual(rv["reviews"]["img_001.png"]["review"], "AGREE")

    # ---- df_decision field -------------------------------------------

    def test_flagged_image_has_finding_decision(self):
        self._write_images(["img_001.png"])
        self._write_report(findings=[_finding_entry("img_001.png", "HIGH")])
        rv = self._run(["a", ""])
        self.assertEqual(rv["reviews"]["img_001.png"]["df_decision"], "FINDING")

    def test_clean_image_has_clean_decision(self):
        self._write_images(["img_001.png"])
        self._write_report(findings=[])
        rv = self._run(["a", ""])
        self.assertEqual(rv["reviews"]["img_001.png"]["df_decision"], "CLEAN")

    # ---- metrics stored with review ----------------------------------

    def test_finding_metrics_stored(self):
        self._write_images(["img_001.png"])
        self._write_report(findings=[_finding_entry("img_001.png", "HIGH")])
        rv = self._run(["a", ""])
        entry = rv["reviews"]["img_001.png"]
        self.assertEqual(entry["severity"], "HIGH")
        self.assertAlmostEqual(entry["micro"], 58.2)
        self.assertAlmostEqual(entry["z"], 1.57)

    def test_clean_image_has_null_metrics(self):
        self._write_images(["img_001.png"])
        self._write_report(findings=[])
        rv = self._run(["a", ""])
        entry = rv["reviews"]["img_001.png"]
        self.assertIsNone(entry["severity"])
        self.assertIsNone(entry["micro"])

    def test_reviewed_at_present(self):
        self._write_images(["img_001.png"])
        self._write_report()
        rv = self._run(["a", ""])
        self.assertIn("reviewed_at", rv["reviews"]["img_001.png"])

    # ---- notes -------------------------------------------------------

    def test_note_stored(self):
        self._write_images(["img_001.png"])
        self._write_report()
        rv = self._run(["a", "looks clean to me"])
        self.assertEqual(rv["reviews"]["img_001.png"]["notes"], "looks clean to me")

    def test_empty_note_stored(self):
        self._write_images(["img_001.png"])
        self._write_report()
        rv = self._run(["d", ""])
        self.assertEqual(rv["reviews"]["img_001.png"]["notes"], "")

    # ---- skip --------------------------------------------------------

    def test_s_skips_without_recording(self):
        self._write_images(["img_001.png"])
        self._write_report()
        rv = self._run(["s"])
        self.assertNotIn("img_001.png", rv["reviews"])

    # ---- quit --------------------------------------------------------

    def test_q_stops_session(self):
        self._write_images(["img_001.png", "img_002.png"])
        self._write_report()
        rv = self._run(["q"])
        self.assertNotIn("img_001.png", rv["reviews"])

    def test_q_saves_reviews_already_made(self):
        self._write_images(["img_001.png", "img_002.png"])
        self._write_report()
        rv = self._run(["a", "", "q"])
        self.assertIn("img_001.png", rv["reviews"])
        self.assertNotIn("img_002.png", rv["reviews"])

    # ---- resumability ------------------------------------------------

    def test_already_reviewed_skipped_by_default(self):
        self._write_images(["img_001.png", "img_002.png"])
        self._write_report()
        self._run(["a", "", "d", ""])
        rv2 = self._run([])
        self.assertEqual(rv2["reviews"]["img_001.png"]["review"], "AGREE")
        self.assertEqual(rv2["reviews"]["img_002.png"]["review"], "DISAGREE")

    def test_review_flag_re_presents_reviewed_images(self):
        self._write_images(["img_001.png"])
        self._write_report()
        self._run(["a", ""])
        rv = self._run(["d", "changed my mind"], review=True)
        self.assertEqual(rv["reviews"]["img_001.png"]["review"], "DISAGREE")
        self.assertEqual(rv["reviews"]["img_001.png"]["notes"], "changed my mind")

    # ---- multiple images ---------------------------------------------

    def test_all_images_labeled_in_one_session(self):
        names = [f"img_{i:03d}.png" for i in range(5)]
        self._write_images(names)
        self._write_report()
        inputs = []
        for _ in names:
            inputs += ["a", ""]
        rv = self._run(inputs)
        for n in names:
            self.assertIn(n, rv["reviews"])

    def test_empty_dataset_returns_empty_reviews(self):
        self._write_report()
        rv = self._run([])
        self.assertEqual(rv["reviews"], {})

    # ---- incremental save --------------------------------------------

    def test_file_saved_after_first_review(self):
        self._write_images(["img_001.png", "img_002.png"])
        self._write_report()

        save_calls: list[str] = []
        import review_decisions as rd
        original_save = rd._save_review_file

        def tracking_save(data, path):
            save_calls.append(path.name)
            original_save(data, path)

        with patch("builtins.input", side_effect=iter(["a", "", "q"])):
            with patch.object(rd, "_save_review_file", side_effect=tracking_save):
                run_review_session(
                    self.dataset,
                    self.report_path,
                    self.rv_path,
                    preview=False,
                )

        self.assertGreaterEqual(len(save_calls), 1)

    # ---- excluded dirs -----------------------------------------------

    def test_inspect_output_not_offered(self):
        inspect_out = self.dataset / "inspect_output"
        inspect_out.mkdir()
        _write_image(inspect_out / "thumb.png")
        _write_image(self.dataset / "real.png")
        self._write_report()

        rv = self._run(["a", ""])
        self.assertIn("real.png", rv["reviews"])
        self.assertNotIn("thumb.png", rv["reviews"])


# ---------------------------------------------------------------------------
# Focus mode
# ---------------------------------------------------------------------------

class TestFocusMode(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.dataset = self.root / "dataset"
        self.dataset.mkdir()
        self.rv_path = self.root / "decision_review.json"
        self.report_path = self.root / "report.json"
        _write_image(self.dataset / "img_001.png")
        _write_image(self.dataset / "img_002.png")
        _write_image(self.dataset / "img_003.png")
        _write_report(self.report_path, _minimal_report(self.dataset))

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, inputs, focus=None):
        responses = iter(inputs)
        with patch("builtins.input", side_effect=lambda _p="": next(responses)):
            return run_review_session(
                self.dataset, self.report_path, self.rv_path,
                preview=False, focus=focus,
            )

    def test_focus_only_presents_named_images(self):
        rv = self._run(["a", ""], focus={"img_001.png"})
        self.assertIn("img_001.png", rv["reviews"])
        self.assertNotIn("img_002.png", rv["reviews"])
        self.assertNotIn("img_003.png", rv["reviews"])

    def test_focus_overwrites_existing_review(self):
        # First pass: label all three
        self._run(["a", "", "a", "", "a", ""])
        # Focus re-review just img_001 with different answer
        rv = self._run(["d", "changed"], focus={"img_001.png"})
        self.assertEqual(rv["reviews"]["img_001.png"]["review"], "DISAGREE")
        # Others unchanged
        self.assertEqual(rv["reviews"]["img_002.png"]["review"], "AGREE")

    def test_focus_empty_set_reviews_nothing(self):
        rv = self._run([], focus=set())
        self.assertEqual(rv["reviews"], {})

    def test_focus_unknown_filename_reviews_nothing(self):
        rv = self._run([], focus={"nonexistent.png"})
        self.assertEqual(rv["reviews"], {})

    def test_focus_multiple_filenames(self):
        rv = self._run(["a", "", "d", ""], focus={"img_001.png", "img_002.png"})
        self.assertIn("img_001.png", rv["reviews"])
        self.assertIn("img_002.png", rv["reviews"])
        self.assertNotIn("img_003.png", rv["reviews"])


# ---------------------------------------------------------------------------
# Preview behavior
# ---------------------------------------------------------------------------

class TestPreviewBehavior(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.dataset = self.root / "dataset"
        self.dataset.mkdir()
        self.rv_path = self.root / "decision_review.json"
        self.report_path = self.root / "report.json"
        _write_image(self.dataset / "img_001.png")
        _write_image(self.dataset / "img_002.png")
        _write_report(self.report_path, _minimal_report(self.dataset))

    def tearDown(self):
        self.tmp.cleanup()

    def test_preview_shows_image_once_per_image(self):
        import review_decisions as rd
        show_calls: list[Path] = []

        class _FakeWin:
            def show(self, p): show_calls.append(p)
            def hide(self): pass
            def close(self): pass

        with patch.object(rd, "_PreviewWindow", return_value=_FakeWin()):
            with patch("builtins.input", side_effect=iter(["a", "", "d", ""])):
                run_review_session(
                    self.dataset, self.report_path, self.rv_path, preview=True
                )
        self.assertEqual(len(show_calls), 2)

    def test_preview_false_never_creates_window(self):
        import review_decisions as rd
        with patch.object(rd, "_PreviewWindow") as mock_cls:
            with patch("builtins.input", side_effect=iter(["a", "", "d", ""])):
                run_review_session(
                    self.dataset, self.report_path, self.rv_path, preview=False
                )
        mock_cls.assert_not_called()

    def test_preview_window_hide_called_after_each_review(self):
        import review_decisions as rd
        hide_calls: list = []

        class _FakeWin:
            def show(self, p): pass
            def hide(self): hide_calls.append(1)
            def close(self): pass

        with patch.object(rd, "_PreviewWindow", return_value=_FakeWin()):
            with patch("builtins.input", side_effect=iter(["a", "", "d", ""])):
                run_review_session(
                    self.dataset, self.report_path, self.rv_path, preview=True
                )
        self.assertEqual(len(hide_calls), 2)

    def test_preview_window_closed_at_end_of_session(self):
        import review_decisions as rd
        closed: list = []

        class _FakeWin:
            def show(self, p): pass
            def hide(self): pass
            def close(self): closed.append(1)

        with patch.object(rd, "_PreviewWindow", return_value=_FakeWin()):
            with patch("builtins.input", side_effect=iter(["a", "", "a", ""])):
                run_review_session(
                    self.dataset, self.report_path, self.rv_path, preview=True
                )
        self.assertEqual(len(closed), 1)


# ---------------------------------------------------------------------------
# _build_crystalline_index
# ---------------------------------------------------------------------------

class TestBuildCrystallineIndex(unittest.TestCase):

    def test_empty_report_returns_empty(self):
        self.assertEqual(_build_crystalline_index({"findings": []}), {})

    def test_crystalline_finding_indexed(self):
        idx = _build_crystalline_index(
            {"findings": [_crystalline_finding_entry("img.png")]}
        )
        self.assertIn("img.png", idx)

    def test_non_crystalline_finding_not_indexed(self):
        idx = _build_crystalline_index(
            {"findings": [_finding_entry("img.png")]}
        )
        self.assertNotIn("img.png", idx)

    def test_indexes_by_basename(self):
        idx = _build_crystalline_index(
            {"findings": [_crystalline_finding_entry("/abs/path/img.png")]}
        )
        self.assertIn("img.png", idx)

    def test_both_types_only_crystalline_returned(self):
        idx = _build_crystalline_index({"findings": [
            _finding_entry("img.png"),
            _crystalline_finding_entry("img.png"),
        ]})
        self.assertIn("img.png", idx)
        self.assertEqual(idx["img.png"]["category"], "artifact.crystalline_faceting")


# ---------------------------------------------------------------------------
# _build_findings_index keeps first finding per image
# ---------------------------------------------------------------------------

class TestBuildFindingsIndexKeepsFirst(unittest.TestCase):

    def test_multiple_findings_same_image_keeps_first(self):
        """Texture finding must not be overwritten by a later crystalline finding."""
        idx = _build_findings_index({"findings": [
            _finding_entry("img.png", "HIGH"),
            _crystalline_finding_entry("img.png"),
        ]})
        self.assertEqual(idx["img.png"]["category"], "texture.high_microtexture")

    def test_single_finding_unchanged(self):
        idx = _build_findings_index({"findings": [_finding_entry("img.png")]})
        self.assertIn("img.png", idx)


# ---------------------------------------------------------------------------
# _extract_crystalline_evidence
# ---------------------------------------------------------------------------

class TestExtractCrystallineEvidence(unittest.TestCase):

    def test_none_returns_none(self):
        self.assertIsNone(_extract_crystalline_evidence(None))

    def test_extracts_all_three_fields(self):
        ev = _extract_crystalline_evidence(
            _crystalline_finding_entry("img.png", grain=60.1, smooth=45.9, micro=50.1)
        )
        self.assertAlmostEqual(ev["grain"],  60.1)
        self.assertAlmostEqual(ev["smooth"], 45.9)
        self.assertAlmostEqual(ev["micro"],  50.1)

    def test_missing_evidence_returns_none_values(self):
        finding = {"category": "artifact.crystalline_faceting", "evidence": {}}
        ev = _extract_crystalline_evidence(finding)
        self.assertIsNone(ev["grain"])
        self.assertIsNone(ev["smooth"])
        self.assertIsNone(ev["micro"])

    def test_non_crystalline_finding_still_extracts_if_keys_present(self):
        """_extract_crystalline_evidence works on any finding dict with the right keys."""
        finding = {
            "evidence": {
                "pencil_grain_score": 55.0,
                "watercolor_smoothness_score": 44.0,
                "microtexture_density_score": 40.0,
            }
        }
        ev = _extract_crystalline_evidence(finding)
        self.assertAlmostEqual(ev["grain"], 55.0)


# ---------------------------------------------------------------------------
# _extract_metrics — category field
# ---------------------------------------------------------------------------

class TestExtractMetricsCategory(unittest.TestCase):

    def test_none_finding_returns_null_category(self):
        m = _extract_metrics(None)
        self.assertIsNone(m["category"])

    def test_category_extracted_from_finding(self):
        m = _extract_metrics(_finding_entry("img.png"))
        self.assertEqual(m["category"], "texture.high_microtexture")

    def test_crystalline_category_extracted(self):
        m = _extract_metrics(_crystalline_finding_entry("img.png"))
        self.assertEqual(m["category"], "artifact.crystalline_faceting")


# ---------------------------------------------------------------------------
# Crystalline evidence in review session
# ---------------------------------------------------------------------------

class TestCrystallineInReviewSession(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.dataset = self.root / "dataset"
        self.dataset.mkdir()
        self.rv_path = self.root / "decision_review.json"
        self.report_path = self.root / "report.json"

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, inputs, findings=None):
        _write_image(self.dataset / "img_001.png")
        _write_report(
            self.report_path,
            _minimal_report(self.dataset, findings or []),
        )
        responses = iter(inputs)
        with patch("builtins.input", side_effect=lambda _p="": next(responses)):
            return run_review_session(
                self.dataset, self.report_path, self.rv_path, preview=False
            )

    def test_grain_stored_when_crystalline_present(self):
        rv = self._run(
            ["a", ""],
            findings=[_crystalline_finding_entry("img_001.png", grain=60.1)],
        )
        self.assertAlmostEqual(rv["reviews"]["img_001.png"]["grain"], 60.1)

    def test_grain_null_when_no_crystalline_finding(self):
        rv = self._run(
            ["a", ""],
            findings=[_finding_entry("img_001.png")],
        )
        self.assertIsNone(rv["reviews"]["img_001.png"]["grain"])

    def test_grain_null_when_no_findings_at_all(self):
        rv = self._run(["a", ""], findings=[])
        self.assertIsNone(rv["reviews"]["img_001.png"]["grain"])

    def test_category_stored_from_primary_finding(self):
        rv = self._run(
            ["a", ""],
            findings=[_finding_entry("img_001.png", "HIGH")],
        )
        self.assertEqual(
            rv["reviews"]["img_001.png"]["category"],
            "texture.high_microtexture",
        )

    def test_category_null_for_clean_image(self):
        rv = self._run(["a", ""], findings=[])
        self.assertIsNone(rv["reviews"]["img_001.png"]["category"])

    def test_both_findings_grain_stored_category_is_texture(self):
        """When both texture and crystalline findings exist, texture is primary
        (df_decision=FINDING, category=texture.high_microtexture) and grain
        comes from the crystalline finding."""
        rv = self._run(
            ["a", ""],
            findings=[
                _finding_entry("img_001.png", "MEDIUM"),
                _crystalline_finding_entry("img_001.png", grain=55.0),
            ],
        )
        entry = rv["reviews"]["img_001.png"]
        self.assertEqual(entry["category"], "texture.high_microtexture")
        self.assertAlmostEqual(entry["grain"], 55.0)

    def test_only_crystalline_finding_df_decision_is_finding(self):
        """Crystalline-only finding should still produce df_decision=FINDING."""
        rv = self._run(
            ["a", ""],
            findings=[_crystalline_finding_entry("img_001.png")],
        )
        self.assertEqual(rv["reviews"]["img_001.png"]["df_decision"], "FINDING")

    def test_only_crystalline_finding_category_is_crystalline(self):
        rv = self._run(
            ["a", ""],
            findings=[_crystalline_finding_entry("img_001.png")],
        )
        self.assertEqual(
            rv["reviews"]["img_001.png"]["category"],
            "artifact.crystalline_faceting",
        )


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------

class TestRoundTrip(unittest.TestCase):

    def test_written_json_is_reloadable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ds   = root / "ds"
            ds.mkdir()
            _write_image(ds / "img.png")

            rpt = root / "report.json"
            _write_report(rpt, _minimal_report(ds))

            rv_path = root / "decision_review.json"

            with patch("builtins.input", side_effect=iter(["d", "too noisy"])):
                run_review_session(ds, rpt, rv_path, preview=False)

            raw = json.loads(rv_path.read_text(encoding="utf-8"))
            self.assertEqual(raw["schema"], DECISION_REVIEW_SCHEMA)
            self.assertIn("img.png", raw["reviews"])
            self.assertEqual(raw["reviews"]["img.png"]["review"], "DISAGREE")
            self.assertEqual(raw["reviews"]["img.png"]["notes"], "too noisy")

            reloaded = _load_review_file(rv_path)
            self.assertEqual(reloaded["reviews"]["img.png"]["review"], "DISAGREE")


if __name__ == "__main__":
    unittest.main()
