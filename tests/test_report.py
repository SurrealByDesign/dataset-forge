"""Tests for report.py — JSON and TXT report writers."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from dataset_forge.context import (
    CONTEXT_SCHEMA_VERSION,
    AspectRatioStats,
    DatasetContext,
    FrequencyDistributions,
    ResolutionStats,
    TextureDistributions,
)
from dataset_forge.finding import Finding, Severity
from dataset_forge.report import (
    REPORT_SCHEMA,
    write_inspection_report,
    write_json_report,
    write_txt_report,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _ctx(n: int = 10, errors: int = 0) -> DatasetContext:
    return DatasetContext(
        schema_version=CONTEXT_SCHEMA_VERSION,
        analyzer_versions={"texture_analyzer": "v1"},
        image_paths=tuple(Path(f"img_{i:03d}.png") for i in range(n)),
        image_count=n,
        error_count=errors,
        resolution_stats=ResolutionStats(
            mean_w=512.0, mean_h=768.0, stddev_w=10.0, stddev_h=15.0,
            min_w=480, min_h=640, max_w=540, max_h=800, sample_count=n,
        ),
        aspect_ratio_stats=AspectRatioStats(
            mean=0.667, stddev=0.02, min=0.60, max=0.75, sample_count=n,
        ),
        texture_distributions=TextureDistributions(
            mean=39.9, stddev=11.6, p10=24.1, p90=55.2, sample_count=n,
        ),
        frequency_distributions=FrequencyDistributions(
            dominant_freq_mean=0.12, dominant_freq_stddev=0.04, sample_count=n,
        ),
        duplicate_hashes=frozenset(),
        duplicate_groups=(),
    )


def _finding(
    image: str = "img_001.png",
    severity: Severity = Severity.HIGH,
    category: str = "texture.high_microtexture",
    confidence: float = 0.65,
) -> Finding:
    return Finding(
        image_path=Path(image),
        analyzer="texture_analyzer/v1",
        category=category,
        severity=severity,
        confidence=confidence,
        false_positive_rate=0.15,
        benchmark_version="uncalibrated",
        evidence={"z_score": 2.5, "microtexture_density": 58.0, "calibrated": False},
        explanation="High microtexture detected.",
        recommendation="Review before making any dataset changes.",
    )


TS = "2026-01-01T00:00:00Z"
TS_DISPLAY = "2026-01-01 00:00:00"


# ---------------------------------------------------------------------------
# JSON report tests
# ---------------------------------------------------------------------------

class TestJSONReportSchema(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name) / "inspection_report.json"
        self.ctx = _ctx(n=10)

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, findings):
        return write_json_report(findings, self.ctx, self.out,
                                 dataset_path="dataset/", generated_at=TS)

    def test_schema_field_present(self):
        d = self._write([])
        self.assertEqual(d["schema"], REPORT_SCHEMA)

    def test_generated_at_field(self):
        d = self._write([])
        self.assertEqual(d["generated_at"], TS)

    def test_context_section_present(self):
        d = self._write([])
        self.assertIn("context", d)

    def test_context_total_images(self):
        d = self._write([])
        self.assertEqual(d["context"]["total_images"], 10)

    def test_context_analyzed_images(self):
        d = self._write([])
        self.assertEqual(d["context"]["analyzed_images"], 10)

    def test_context_error_images_zero(self):
        d = self._write([])
        self.assertEqual(d["context"]["error_images"], 0)

    def test_context_contains_texture_distributions(self):
        d = self._write([])
        td = d["context"]["texture_distributions"]
        self.assertAlmostEqual(td["mean"], 39.9)

    def test_findings_section_is_list(self):
        d = self._write([_finding()])
        self.assertIsInstance(d["findings"], list)

    def test_findings_count(self):
        d = self._write([_finding(), _finding("img_002.png")])
        self.assertEqual(len(d["findings"]), 2)

    def test_finding_has_required_fields(self):
        d = self._write([_finding()])
        f = d["findings"][0]
        for field in ("image_path", "analyzer", "category", "severity",
                      "confidence", "false_positive_rate", "benchmark_version",
                      "evidence", "explanation", "recommendation"):
            self.assertIn(field, f)

    def test_finding_severity_is_string(self):
        d = self._write([_finding(severity=Severity.HIGH)])
        self.assertEqual(d["findings"][0]["severity"], "HIGH")

    def test_summary_section_present(self):
        d = self._write([_finding()])
        self.assertIn("summary", d)

    def test_summary_total_findings(self):
        d = self._write([_finding(), _finding()])
        self.assertEqual(d["summary"]["total_findings"], 2)

    def test_summary_images_with_findings(self):
        # Two findings on the same image → 1 affected image
        d = self._write([_finding("img_001.png"), _finding("img_001.png")])
        self.assertEqual(d["summary"]["images_with_findings"], 1)

    def test_summary_images_clean(self):
        d = self._write([_finding()])   # 1 of 10 affected
        self.assertEqual(d["summary"]["images_clean"], 9)

    def test_summary_severity_counts(self):
        findings = [
            _finding(severity=Severity.HIGH),
            _finding(severity=Severity.MEDIUM),
            _finding(severity=Severity.MEDIUM),
        ]
        d = self._write(findings)
        sc = d["summary"]["severity_counts"]
        self.assertEqual(sc["HIGH"], 1)
        self.assertEqual(sc["MEDIUM"], 2)

    def test_empty_findings_valid_report(self):
        d = self._write([])
        self.assertEqual(d["summary"]["total_findings"], 0)
        self.assertEqual(d["summary"]["images_clean"], 10)

    def test_file_is_written(self):
        self._write([_finding()])
        self.assertTrue(self.out.exists())

    def test_file_is_valid_json(self):
        self._write([_finding()])
        parsed = json.loads(self.out.read_text(encoding="utf-8"))
        self.assertIn("schema", parsed)

    def test_findings_sorted_deterministically(self):
        findings = [_finding("img_003.png"), _finding("img_001.png")]
        d = self._write(findings)
        paths = [f["image_path"] for f in d["findings"]]
        self.assertEqual(paths, sorted(paths))


# ---------------------------------------------------------------------------
# TXT report tests
# ---------------------------------------------------------------------------

class TestTXTReportContent(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name) / "inspection_report.txt"
        self.ctx = _ctx(n=10)

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, findings) -> str:
        return write_txt_report(findings, self.ctx, self.out,
                                dataset_path="dataset/",
                                generated_at_display=TS_DISPLAY)

    def test_header_present(self):
        txt = self._write([])
        self.assertIn("Dataset Forge Inspection Report", txt)

    def test_generated_at_present(self):
        txt = self._write([])
        self.assertIn(TS_DISPLAY, txt)

    def test_findings_section_present(self):
        txt = self._write([_finding()])
        self.assertIn("FINDINGS BY IMAGE", txt)

    def test_finding_severity_shown(self):
        txt = self._write([_finding(severity=Severity.HIGH)])
        self.assertIn("[HIGH]", txt)

    def test_finding_category_shown(self):
        txt = self._write([_finding(category="texture.high_microtexture")])
        self.assertIn("texture.high_microtexture", txt)

    def test_finding_confidence_shown(self):
        txt = self._write([_finding(confidence=0.65)])
        self.assertIn("0.65", txt)

    def test_finding_fp_rate_shown(self):
        txt = self._write([_finding()])
        self.assertIn("FP rate", txt)

    def test_finding_benchmark_shown(self):
        txt = self._write([_finding()])
        self.assertIn("uncalibrated", txt)

    def test_finding_explanation_shown(self):
        txt = self._write([_finding()])
        self.assertIn("High microtexture detected", txt)

    def test_finding_recommendation_shown(self):
        txt = self._write([_finding()])
        self.assertIn("Review before making any dataset changes", txt)

    def test_summary_does_not_advertise_cleanup_command(self):
        txt = self._write([_finding()])
        self.assertNotIn("dataset-forge clean", txt)
        self.assertIn("inspect is read-only", txt)

    def test_clean_images_section_present(self):
        txt = self._write([_finding()])
        self.assertIn("CLEAN IMAGES", txt)

    def test_clean_count_in_txt(self):
        txt = self._write([_finding()])  # 1 of 10 affected → 9 clean
        self.assertIn("9 image", txt)

    def test_summary_section_present(self):
        txt = self._write([_finding()])
        self.assertIn("SUMMARY", txt)

    def test_no_findings_message(self):
        txt = self._write([])
        self.assertIn("No findings", txt)

    def test_all_clean_zero_findings(self):
        txt = self._write([])
        self.assertIn("10 image", txt)

    def test_file_written(self):
        self._write([_finding()])
        self.assertTrue(self.out.exists())

    def test_file_content_matches_return(self):
        txt = self._write([_finding()])
        self.assertEqual(self.out.read_text(encoding="utf-8"), txt)


# ---------------------------------------------------------------------------
# Convenience wrapper
# ---------------------------------------------------------------------------

class TestWriteInspectionReport(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out_dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_both_files_written(self):
        json_p, txt_p = write_inspection_report(
            [_finding()], _ctx(), self.out_dir, dataset_path="dataset/"
        )
        self.assertTrue(json_p.exists())
        self.assertTrue(txt_p.exists())

    def test_json_filename(self):
        json_p, _ = write_inspection_report([], _ctx(), self.out_dir)
        self.assertEqual(json_p.name, "inspection_report.json")

    def test_txt_filename(self):
        _, txt_p = write_inspection_report([], _ctx(), self.out_dir)
        self.assertEqual(txt_p.name, "inspection_report.txt")


# ---------------------------------------------------------------------------
# Score table tests
# ---------------------------------------------------------------------------

def _scores(paths: list[str], micro_values: list[float]) -> dict[str, dict]:
    """Build a minimal image_scores dict for testing."""
    return {
        p: {
            "microtexture_density": m,
            "watercolor_smoothness": 80.0 - m,
            "highlight_speck": m * 0.1,
        }
        for p, m in zip(paths, micro_values)
    }


class TestScoreTable(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name) / "inspection_report.txt"
        self.ctx = _ctx(n=3)

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, findings, scores) -> str:
        return write_txt_report(
            findings, self.ctx, self.out,
            dataset_path="dataset/",
            generated_at_display=TS_DISPLAY,
            image_scores=scores,
        )

    def test_score_table_section_present_when_scores_provided(self):
        paths = ["img_000.png", "img_001.png", "img_002.png"]
        scores = _scores(paths, [50.0, 35.0, 20.0])
        txt = self._write([], scores)
        self.assertIn("DATASET TEXTURE SCORES", txt)

    def test_score_table_absent_when_no_scores(self):
        txt = self._write([], None)
        self.assertNotIn("DATASET TEXTURE SCORES", txt)

    def test_all_images_appear_in_score_table(self):
        paths = ["img_000.png", "img_001.png", "img_002.png"]
        scores = _scores(paths, [50.0, 35.0, 20.0])
        txt = self._write([], scores)
        for p in paths:
            self.assertIn(Path(p).name, txt)

    def test_finding_images_tagged_as_finding(self):
        paths = ["img_000.png", "img_001.png", "img_002.png"]
        scores = _scores(paths, [50.0, 35.0, 20.0])
        f = _finding(image="img_000.png")
        txt = self._write([f], scores)
        # The high-micro image (img_000) should be tagged FINDING
        self.assertIn("[FINDING]", txt)

    def test_clean_images_tagged_as_clean(self):
        paths = ["img_000.png", "img_001.png", "img_002.png"]
        scores = _scores(paths, [50.0, 35.0, 20.0])
        f = _finding(image="img_000.png")
        txt = self._write([f], scores)
        self.assertIn("[clean  ]", txt)

    def test_score_table_sorted_descending_by_microtexture(self):
        paths = ["img_000.png", "img_001.png", "img_002.png"]
        # Assign micro in reverse order so default sort would be wrong
        scores = _scores(paths, [20.0, 50.0, 35.0])
        txt = self._write([], scores)
        table_start = txt.index("DATASET TEXTURE SCORES")
        summary_start = txt.index("SUMMARY")
        table_section = txt[table_start:summary_start]
        # img_001 (micro=50) should appear before img_002 (micro=35)
        pos_001 = table_section.find("img_001")
        pos_002 = table_section.find("img_002")
        pos_000 = table_section.find("img_000")
        self.assertLess(pos_001, pos_002)
        self.assertLess(pos_002, pos_000)

    def test_score_table_shows_microtexture_values(self):
        paths = ["img_000.png"]
        scores = _scores(paths, [42.7])
        txt = self._write([], scores)
        self.assertIn("42.7", txt)

    def test_score_table_shows_baseline(self):
        paths = ["img_000.png"]
        scores = _scores(paths, [30.0])
        txt = self._write([], scores)
        self.assertIn("mean=", txt)
        self.assertIn("stddev=", txt)

    def test_score_table_shows_z_score(self):
        paths = ["img_000.png"]
        scores = _scores(paths, [70.0])   # well above dataset mean of 39.9
        f = _finding(image="img_000.png")
        txt = self._write([f], scores)
        # z-score should appear as a signed float
        self.assertIn("+", txt)

    def test_end_to_end_score_table_via_run_inspect(self):
        """Score table appears in the TXT report produced by run_inspect()."""
        import numpy as np
        from PIL import Image
        from dataset_forge.inspect import run_inspect
        tmp2 = tempfile.TemporaryDirectory()
        try:
            ds = Path(tmp2.name) / "ds"
            out = Path(tmp2.name) / "out"
            ds.mkdir()
            for i in range(3):
                arr = np.full((64, 64, 3), 128 + i * 10, dtype=np.uint8)
                Image.fromarray(arr).save(ds / f"img_{i}.png")
            result = run_inspect(ds, out)
            txt = result.txt_report.read_text(encoding="utf-8")
            self.assertIn("DATASET TEXTURE SCORES", txt)
            self.assertIn("img_0", txt)
        finally:
            tmp2.cleanup()


if __name__ == "__main__":
    unittest.main()
