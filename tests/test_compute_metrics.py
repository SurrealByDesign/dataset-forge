"""Tests for scripts/compute_metrics.py.

Focuses on the pure-computation layer (compute_metrics, build_findings_index,
load_report, load_review) and the output shape.  No file I/O beyond fixtures.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "src"))
sys.path.insert(0, str(_REPO / "scripts"))

from compute_metrics import (
    build_findings_index,
    compute_metrics,
    load_report,
    load_review,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SCHEMA_REVIEW = "dataset-forge/decision-review/v1"


def _finding(name: str, severity: str = "MEDIUM", micro: float = 55.0,
             z: float = 1.5) -> dict:
    return {
        "image_path": name,
        "analyzer": "texture_analyzer/v1",
        "category": "texture.high_microtexture",
        "severity": severity,
        "confidence": 0.60,
        "false_positive_rate": 0.15,
        "benchmark_version": "uncalibrated",
        "evidence": {
            "microtexture_density": micro,
            "z_score": z,
            "watercolor_smoothness": 38.0,
            "highlight_speck": 5.0,
        },
        "explanation": "High micro.",
        "recommendation": "Review.",
    }


def _minimal_report(findings: list[dict] | None = None) -> dict:
    return {
        "schema": "dataset-forge/inspection/v1",
        "generated_at": "2026-06-16T00:00:00Z",
        "dataset_path": "/ds",
        "context": {
            "total_images": 5,
            "analyzed_images": 5,
            "error_images": 0,
            "texture_distributions": {
                "mean": 38.0, "stddev": 10.0,
                "p10": 25.0, "p90": 52.0, "sample_count": 5,
            },
        },
        "findings": findings or [],
        "summary": {"total_findings": 0, "images_with_findings": 0,
                    "images_clean": 5, "severity_counts": {}},
    }


def _minimal_review(reviews: dict) -> dict:
    return {
        "schema": SCHEMA_REVIEW,
        "dataset_path": "/ds",
        "report_path": "/ds/report.json",
        "reviewed_by": "human",
        "created_at": "2026-06-17T00:00:00Z",
        "updated_at": "2026-06-17T00:00:00Z",
        "reviews": reviews,
    }


def _rv(review: str, df_decision: str = "CLEAN", severity: str | None = None,
        micro: float | None = None, z: float | None = None) -> dict:
    return {
        "review": review,
        "notes": "",
        "df_decision": df_decision,
        "severity": severity,
        "micro": micro,
        "z": z,
        "smooth": None,
        "speck": None,
        "reviewed_at": "2026-06-17T00:00:00Z",
    }


# ---------------------------------------------------------------------------
# load_report / load_review
# ---------------------------------------------------------------------------

class TestLoaders(unittest.TestCase):

    def test_load_report_returns_dict(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "r.json"
            p.write_text(json.dumps(_minimal_report()), encoding="utf-8")
            self.assertIsInstance(load_report(p), dict)

    def test_load_report_raises_on_wrong_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "r.json"
            p.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_report(p)

    def test_load_review_accepts_correct_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "rv.json"
            p.write_text(json.dumps(_minimal_review({})), encoding="utf-8")
            rv = load_review(p)
            self.assertEqual(rv["schema"], SCHEMA_REVIEW)

    def test_load_review_raises_on_wrong_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "rv.json"
            p.write_text(json.dumps({"schema": "wrong/v0", "reviews": {}}),
                         encoding="utf-8")
            with self.assertRaises(ValueError):
                load_review(p)


# ---------------------------------------------------------------------------
# build_findings_index
# ---------------------------------------------------------------------------

class TestBuildFindingsIndex(unittest.TestCase):

    def test_empty(self):
        self.assertEqual(build_findings_index({"findings": []}), {})

    def test_keyed_by_basename(self):
        idx = build_findings_index(
            {"findings": [_finding("/abs/path/img.png")]}
        )
        self.assertIn("img.png", idx)

    def test_multiple(self):
        idx = build_findings_index(
            {"findings": [_finding("a.png"), _finding("b.png")]}
        )
        self.assertIn("a.png", idx)
        self.assertIn("b.png", idx)


# ---------------------------------------------------------------------------
# compute_metrics — summary counts
# ---------------------------------------------------------------------------

class TestComputeMetricsCounts(unittest.TestCase):

    def _run(self, findings, reviews):
        return compute_metrics(_minimal_report(findings), _minimal_review(reviews))

    def test_total_reviewed(self):
        m = self._run([], {"a.png": _rv("AGREE"), "b.png": _rv("DISAGREE")})
        self.assertEqual(m["summary"]["total_reviewed"], 2)

    def test_agree_count(self):
        m = self._run([], {"a.png": _rv("AGREE"), "b.png": _rv("AGREE")})
        self.assertEqual(m["summary"]["agree"], 2)

    def test_disagree_count(self):
        m = self._run([], {"a.png": _rv("DISAGREE")})
        self.assertEqual(m["summary"]["disagree"], 1)

    def test_unsure_count(self):
        m = self._run([], {"a.png": _rv("UNSURE")})
        self.assertEqual(m["summary"]["unsure"], 1)

    def test_agreement_pct_100(self):
        m = self._run([], {"a.png": _rv("AGREE")})
        self.assertAlmostEqual(m["summary"]["agreement_pct"], 100.0)

    def test_agreement_pct_partial(self):
        m = self._run([], {
            "a.png": _rv("AGREE"),
            "b.png": _rv("DISAGREE"),
        })
        self.assertAlmostEqual(m["summary"]["agreement_pct"], 50.0)

    def test_empty_review(self):
        m = self._run([], {})
        self.assertEqual(m["summary"]["total_reviewed"], 0)
        self.assertAlmostEqual(m["summary"]["agreement_pct"], 0.0)


# ---------------------------------------------------------------------------
# compute_metrics — finding review
# ---------------------------------------------------------------------------

class TestComputeMetricsFindingReview(unittest.TestCase):

    def test_finding_agree(self):
        m = compute_metrics(
            _minimal_report([_finding("img.png")]),
            _minimal_review({"img.png": _rv("AGREE", "FINDING", "MEDIUM", 55.0, 1.5)}),
        )
        self.assertEqual(m["finding_review"]["finding_agree"], 1)
        self.assertEqual(m["finding_review"]["finding_disagree"], 0)

    def test_finding_disagree(self):
        m = compute_metrics(
            _minimal_report([_finding("img.png")]),
            _minimal_review({"img.png": _rv("DISAGREE", "FINDING", "MEDIUM", 55.0, 1.5)}),
        )
        self.assertEqual(m["finding_review"]["finding_disagree"], 1)

    def test_precision_100(self):
        m = compute_metrics(
            _minimal_report([_finding("img.png")]),
            _minimal_review({"img.png": _rv("AGREE", "FINDING", "MEDIUM")}),
        )
        self.assertAlmostEqual(m["finding_review"]["precision"], 100.0)

    def test_precision_50(self):
        m = compute_metrics(
            _minimal_report([_finding("a.png"), _finding("b.png")]),
            _minimal_review({
                "a.png": _rv("AGREE",    "FINDING", "MEDIUM"),
                "b.png": _rv("DISAGREE", "FINDING", "MEDIUM"),
            }),
        )
        self.assertAlmostEqual(m["finding_review"]["precision"], 50.0)

    def test_precision_none_when_no_findings_reviewed(self):
        m = compute_metrics(_minimal_report([]), _minimal_review({}))
        self.assertIsNone(m["finding_review"]["precision"])


# ---------------------------------------------------------------------------
# compute_metrics — clean review / missed detections
# ---------------------------------------------------------------------------

class TestComputeMetricsCleanReview(unittest.TestCase):

    def test_clean_agree(self):
        m = compute_metrics(
            _minimal_report([]),
            _minimal_review({"img.png": _rv("AGREE")}),
        )
        self.assertEqual(m["clean_review"]["clean_agree"], 1)

    def test_missed_detection_counted(self):
        m = compute_metrics(
            _minimal_report([]),
            _minimal_review({"img.png": _rv("DISAGREE")}),
        )
        self.assertEqual(m["clean_review"]["clean_disagree"], 1)
        self.assertEqual(len(m["missed_detections"]), 1)

    def test_missed_detection_rate(self):
        m = compute_metrics(
            _minimal_report([]),
            _minimal_review({
                "a.png": _rv("DISAGREE"),
                "b.png": _rv("DISAGREE"),
                "c.png": _rv("AGREE"),
                "d.png": _rv("AGREE"),
            }),
        )
        self.assertAlmostEqual(m["clean_review"]["missed_detection_pct"], 50.0)

    def test_missed_detections_sorted_by_z_desc(self):
        m = compute_metrics(
            _minimal_report([]),
            _minimal_review({
                "low.png":  _rv("DISAGREE", micro=40.0, z=0.2),
                "high.png": _rv("DISAGREE", micro=48.0, z=0.9),
            }),
        )
        names = [e["filename"] for e in m["missed_detections"]]
        self.assertEqual(names[0], "high.png")

    def test_missed_detection_entry_fields(self):
        m = compute_metrics(
            _minimal_report([]),
            _minimal_review({"img.png": _rv("DISAGREE", micro=42.0, z=0.4)}),
        )
        e = m["missed_detections"][0]
        self.assertEqual(e["filename"], "img.png")
        self.assertEqual(e["df_decision"], "CLEAN")
        self.assertAlmostEqual(e["z"], 0.4)


# ---------------------------------------------------------------------------
# compute_metrics — false positives
# ---------------------------------------------------------------------------

class TestComputeMetricsFalsePositives(unittest.TestCase):

    def test_false_positive_listed(self):
        m = compute_metrics(
            _minimal_report([_finding("img.png", "HIGH", 65.0, 2.3)]),
            _minimal_review({
                "img.png": _rv("DISAGREE", "FINDING", "HIGH", 65.0, 2.3)
            }),
        )
        self.assertEqual(len(m["false_positives"]), 1)
        self.assertEqual(m["false_positives"][0]["filename"], "img.png")

    def test_no_false_positives_when_all_agree(self):
        m = compute_metrics(
            _minimal_report([_finding("img.png")]),
            _minimal_review({"img.png": _rv("AGREE", "FINDING", "MEDIUM")}),
        )
        self.assertEqual(m["false_positives"], [])


# ---------------------------------------------------------------------------
# compute_metrics — threshold diagnostics
# ---------------------------------------------------------------------------

class TestThresholdDiagnostics(unittest.TestCase):

    def test_z_stats_computed_when_data_available(self):
        m = compute_metrics(
            _minimal_report([]),
            _minimal_review({
                "a.png": _rv("DISAGREE", z=0.5),
                "b.png": _rv("DISAGREE", z=0.9),
            }),
        )
        zs = m["threshold_diagnostics"]["z_score_stats_of_disagreements"]
        self.assertIsNotNone(zs)
        self.assertEqual(zs["count"], 2)
        self.assertAlmostEqual(zs["min"], 0.5)
        self.assertAlmostEqual(zs["max"], 0.9)

    def test_z_stats_none_when_no_disagreements(self):
        m = compute_metrics(
            _minimal_report([]),
            _minimal_review({"a.png": _rv("AGREE")}),
        )
        self.assertIsNone(
            m["threshold_diagnostics"]["z_score_stats_of_disagreements"]
        )

    def test_z_stats_excludes_none_z_values(self):
        m = compute_metrics(
            _minimal_report([]),
            _minimal_review({
                "a.png": _rv("DISAGREE", z=0.7),
                "b.png": _rv("DISAGREE", z=None),   # no z available
            }),
        )
        zs = m["threshold_diagnostics"]["z_score_stats_of_disagreements"]
        self.assertEqual(zs["count"], 1)


# ---------------------------------------------------------------------------
# JSON output
# ---------------------------------------------------------------------------

class TestJSONOutput(unittest.TestCase):

    def test_output_file_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "metrics.json"
            report  = _minimal_report([_finding("img.png")])
            review  = _minimal_review({"img.png": _rv("AGREE", "FINDING", "MEDIUM")})
            m = compute_metrics(report, review)
            out.write_text(
                json.dumps(m, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            self.assertTrue(out.exists())
            raw = json.loads(out.read_text(encoding="utf-8"))
            self.assertIn("summary", raw)
            self.assertIn("missed_detections", raw)
            self.assertIn("false_positives", raw)


if __name__ == "__main__":
    unittest.main()
