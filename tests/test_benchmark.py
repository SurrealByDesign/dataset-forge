"""Tests for the Dataset Forge benchmark framework.

Tests the manifest loader, expectation evaluator, result writers, and
the end-to-end run_benchmark function with mocked analyzers. No real
images are required — temporary PIL images cover cases that need disk files.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
from PIL import Image

from dataset_forge.benchmark import (
    BENCHMARK_SCHEMA_VERSION,
    BenchmarkCase,
    BenchmarkExpectation,
    BenchmarkRun,
    ExpectationResult,
    _ANALYZER_REGISTRY,
    _build_context_for_group,
    _evaluate_expectation,
    load_manifest,
    run_benchmark,
    write_json_results,
    write_txt_results,
)
from dataset_forge.analyzers.registry import analyzer_versions, create_analyzer_registry
from dataset_forge.context import (
    CONTEXT_SCHEMA_VERSION,
    AspectRatioStats,
    DatasetContext,
    FrequencyDistributions,
    ResolutionStats,
    TextureDistributions,
)
from dataset_forge.finding import Finding, Severity


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_context() -> DatasetContext:
    return DatasetContext(
        schema_version=CONTEXT_SCHEMA_VERSION,
        analyzer_versions={},
        image_paths=(),
        image_count=0,
        error_count=0,
        resolution_stats=ResolutionStats.empty(),
        aspect_ratio_stats=AspectRatioStats.empty(),
        texture_distributions=TextureDistributions(
            mean=25.0, stddev=5.0, p10=18.0, p90=33.0, sample_count=10
        ),
        frequency_distributions=FrequencyDistributions.empty(),
        duplicate_hashes=frozenset(),
        duplicate_groups=(),
    )


def _write_solid_image(path: Path) -> None:
    arr = np.full((64, 64, 3), 128, dtype=np.uint8)
    Image.fromarray(arr).save(path)


def _minimal_manifest(cases: list[dict]) -> dict:
    return {
        "schema_version": BENCHMARK_SCHEMA_VERSION,
        "name": "Test Suite",
        "cases": cases,
    }


def _make_finding(category: str, severity: Severity) -> Finding:
    return Finding(
        image_path=Path("dummy.png"),
        analyzer="test_analyzer/v1",
        category=category,
        severity=severity,
        confidence=0.8,
        false_positive_rate=0.1,
        benchmark_version="test",
        evidence={},
        explanation="test",
        recommendation="test",
    )


# ---------------------------------------------------------------------------
# load_manifest
# ---------------------------------------------------------------------------

class TestLoadManifest(unittest.TestCase):
    def test_loads_valid_manifest(self):
        raw = _minimal_manifest([
            {
                "id": "case_a",
                "image_path": "some/image.png",
                "provenance": "synthetic",
                "private": True,
                "source_description": "desc",
                "context_group": "grp",
                "expectations": [
                    {
                        "analyzer_id": "texture_analyzer/v1",
                        "category": "texture.high_microtexture",
                        "should_detect": False,
                        "expected_severity": None,
                        "notes": "clean",
                    }
                ],
            }
        ])
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "manifest.json"
            p.write_text(json.dumps(raw), encoding="utf-8")
            name, cases = load_manifest(p)
        self.assertEqual(name, "Test Suite")
        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0].id, "case_a")
        self.assertEqual(cases[0].provenance, "synthetic")
        self.assertTrue(cases[0].private)
        self.assertEqual(len(cases[0].expectations), 1)
        self.assertFalse(cases[0].expectations[0].should_detect)

    def test_wrong_schema_version_raises(self):
        raw = {"schema_version": 99, "name": "X", "cases": []}
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "manifest.json"
            p.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_manifest(p)

    def test_empty_cases_returns_empty_list(self):
        raw = _minimal_manifest([])
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "manifest.json"
            p.write_text(json.dumps(raw), encoding="utf-8")
            _, cases = load_manifest(p)
        self.assertEqual(cases, [])

    def test_expectation_defaults(self):
        raw = _minimal_manifest([
            {
                "id": "x",
                "image_path": "x.png",
                "expectations": [
                    {
                        "analyzer_id": "a/v1",
                        "category": "cat",
                        "should_detect": True,
                    }
                ],
            }
        ])
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "m.json"
            p.write_text(json.dumps(raw), encoding="utf-8")
            _, cases = load_manifest(p)
        exp = cases[0].expectations[0]
        self.assertIsNone(exp.expected_severity)
        self.assertEqual(exp.notes, "")

    def test_case_defaults(self):
        raw = _minimal_manifest([
            {
                "id": "x",
                "image_path": "x.png",
                "expectations": [],
            }
        ])
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "m.json"
            p.write_text(json.dumps(raw), encoding="utf-8")
            _, cases = load_manifest(p)
        case = cases[0]
        self.assertTrue(case.private)
        self.assertEqual(case.provenance, "unknown")
        self.assertEqual(case.context_group, "default")


# ---------------------------------------------------------------------------
# _evaluate_expectation
# ---------------------------------------------------------------------------

class TestEvaluateExpectation(unittest.TestCase):
    def _exp(self, should_detect: bool, expected_severity: str | None = None) -> BenchmarkExpectation:
        return BenchmarkExpectation(
            analyzer_id="a/v1",
            category="cat",
            should_detect=should_detect,
            expected_severity=expected_severity,
        )

    def test_should_detect_true_and_found(self):
        self.assertTrue(_evaluate_expectation(self._exp(True), True, "MEDIUM"))

    def test_should_detect_true_not_found_fails(self):
        self.assertFalse(_evaluate_expectation(self._exp(True), False, None))

    def test_should_detect_false_not_found(self):
        self.assertTrue(_evaluate_expectation(self._exp(False), False, None))

    def test_should_detect_false_but_found_fails(self):
        self.assertFalse(_evaluate_expectation(self._exp(False), True, "LOW"))

    def test_severity_match_passes(self):
        self.assertTrue(_evaluate_expectation(self._exp(True, "LOW"), True, "LOW"))

    def test_severity_mismatch_fails(self):
        self.assertFalse(_evaluate_expectation(self._exp(True, "HIGH"), True, "LOW"))

    def test_severity_none_ignores_actual(self):
        self.assertTrue(_evaluate_expectation(self._exp(True, None), True, "CRITICAL"))

    def test_not_found_ignores_severity_expectation(self):
        self.assertFalse(_evaluate_expectation(self._exp(True, "HIGH"), False, None))


# ---------------------------------------------------------------------------
# BenchmarkRun.success
# ---------------------------------------------------------------------------

class TestBenchmarkRunSuccess(unittest.TestCase):
    def _run(self, failed: int) -> BenchmarkRun:
        return BenchmarkRun(
            manifest_path="m.json",
            timestamp="2026-01-01T00:00:00+00:00",
            total=10,
            passed=10 - failed,
            failed=failed,
            skipped=0,
            results=[],
        )

    def test_success_when_no_failures(self):
        self.assertTrue(self._run(0).success)

    def test_not_success_when_failures(self):
        self.assertFalse(self._run(1).success)


# ---------------------------------------------------------------------------
# write_json_results / write_txt_results
# ---------------------------------------------------------------------------

class TestWriteResults(unittest.TestCase):
    def _make_run(self) -> BenchmarkRun:
        exp = BenchmarkExpectation(
            analyzer_id="a/v1",
            category="cat",
            should_detect=True,
            expected_severity="LOW",
            notes="note",
        )
        result = ExpectationResult(
            case_id="case_a",
            image_path="img.png",
            expectation=exp,
            passed=True,
            skipped=False,
            skip_reason="",
            actual_found=True,
            actual_severity="LOW",
            actual_confidence=0.5,
        )
        return BenchmarkRun(
            manifest_path="manifest.json",
            timestamp="2026-01-01T00:00:00+00:00",
            total=1,
            passed=1,
            failed=0,
            skipped=0,
            results=[result],
        )

    def test_json_has_summary(self):
        run = self._make_run()
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "results.json"
            write_json_results(run, out)
            data = json.loads(out.read_text("utf-8"))
        self.assertIn("summary", data)
        self.assertEqual(data["summary"]["total"], 1)
        self.assertEqual(data["summary"]["passed"], 1)
        self.assertTrue(data["summary"]["success"])

    def test_json_has_results_list(self):
        run = self._make_run()
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "results.json"
            write_json_results(run, out)
            data = json.loads(out.read_text("utf-8"))
        self.assertEqual(len(data["results"]), 1)
        r = data["results"][0]
        self.assertEqual(r["case_id"], "case_a")
        self.assertTrue(r["passed"])
        self.assertEqual(r["actual_severity"], "LOW")

    def test_txt_contains_pass_line(self):
        run = self._make_run()
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "results.txt"
            write_txt_results(run, out)
            content = out.read_text("utf-8")
        self.assertIn("[PASS]", content)
        self.assertIn("case_a", content)

    def test_txt_contains_status(self):
        run = self._make_run()
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "results.txt"
            write_txt_results(run, out)
            content = out.read_text("utf-8")
        self.assertIn("Status    : PASS", content)

    def test_json_schema_version(self):
        run = self._make_run()
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "results.json"
            write_json_results(run, out)
            data = json.loads(out.read_text("utf-8"))
        self.assertEqual(data["schema_version"], BENCHMARK_SCHEMA_VERSION)


# ---------------------------------------------------------------------------
# run_benchmark integration (with mocked analyzers)
# ---------------------------------------------------------------------------

class TestRunBenchmark(unittest.TestCase):
    def _write_manifest(self, td: str, cases: list[dict]) -> Path:
        p = Path(td) / "manifest.json"
        p.write_text(json.dumps(_minimal_manifest(cases)), encoding="utf-8")
        return p

    def test_missing_private_image_is_skipped_not_failed(self):
        with tempfile.TemporaryDirectory() as td:
            manifest = self._write_manifest(td, [
                {
                    "id": "missing",
                    "image_path": "does_not_exist.png",
                    "private": True,
                    "context_group": "g",
                    "expectations": [
                        {
                            "analyzer_id": "texture_analyzer/v1",
                            "category": "texture.high_microtexture",
                            "should_detect": False,
                            "expected_severity": None,
                        }
                    ],
                }
            ])
            run = run_benchmark(manifest, project_root=Path(td))
        self.assertEqual(run.skipped, 1)
        self.assertEqual(run.failed, 0)
        self.assertTrue(run.success)

    def test_missing_non_private_image_is_skipped_not_failed(self):
        with tempfile.TemporaryDirectory() as td:
            manifest = self._write_manifest(td, [
                {
                    "id": "missing_pub",
                    "image_path": "nope.png",
                    "private": False,
                    "context_group": "g",
                    "expectations": [
                        {
                            "analyzer_id": "crystalline_faceting_analyzer/v1",
                            "category": "artifact.crystalline_faceting",
                            "should_detect": False,
                            "expected_severity": None,
                        }
                    ],
                }
            ])
            run = run_benchmark(manifest, project_root=Path(td))
        self.assertEqual(run.skipped, 1)
        self.assertEqual(run.failed, 0)

    def test_unknown_analyzer_is_skipped(self):
        with tempfile.TemporaryDirectory() as td:
            img_path = Path(td) / "img.png"
            _write_solid_image(img_path)
            manifest = self._write_manifest(td, [
                {
                    "id": "unknown_analyzer",
                    "image_path": "img.png",
                    "private": False,
                    "context_group": "g",
                    "expectations": [
                        {
                            "analyzer_id": "nonexistent_analyzer/v99",
                            "category": "some.category",
                            "should_detect": False,
                            "expected_severity": None,
                        }
                    ],
                }
            ])
            run = run_benchmark(manifest, project_root=Path(td))
        self.assertEqual(run.skipped, 1)
        self.assertEqual(run.failed, 0)

    def test_passing_expectation_counted_correctly(self):
        mock_analyzer = MagicMock()
        mock_analyzer.analyze.return_value = []  # no findings

        with tempfile.TemporaryDirectory() as td:
            img_path = Path(td) / "img.png"
            _write_solid_image(img_path)
            manifest = self._write_manifest(td, [
                {
                    "id": "clean_case",
                    "image_path": "img.png",
                    "private": False,
                    "context_group": "g",
                    "expectations": [
                        {
                            "analyzer_id": "texture_analyzer/v1",
                            "category": "texture.high_microtexture",
                            "should_detect": False,
                            "expected_severity": None,
                        }
                    ],
                }
            ])
            registry = {"texture_analyzer/v1": mock_analyzer}
            run = run_benchmark(manifest, project_root=Path(td), registry=registry)

        self.assertEqual(run.total, 1)
        self.assertEqual(run.passed, 1)
        self.assertEqual(run.failed, 0)
        self.assertTrue(run.success)

    def test_failing_expectation_counted_correctly(self):
        mock_finding = _make_finding("texture.high_microtexture", Severity.MEDIUM)
        mock_analyzer = MagicMock()
        mock_analyzer.analyze.return_value = [mock_finding]

        with tempfile.TemporaryDirectory() as td:
            img_path = Path(td) / "img.png"
            _write_solid_image(img_path)
            manifest = self._write_manifest(td, [
                {
                    "id": "should_be_clean",
                    "image_path": "img.png",
                    "private": False,
                    "context_group": "g",
                    "expectations": [
                        {
                            "analyzer_id": "texture_analyzer/v1",
                            "category": "texture.high_microtexture",
                            "should_detect": False,
                            "expected_severity": None,
                        }
                    ],
                }
            ])
            registry = {"texture_analyzer/v1": mock_analyzer}
            run = run_benchmark(manifest, project_root=Path(td), registry=registry)

        self.assertEqual(run.failed, 1)
        self.assertFalse(run.success)

    def test_severity_mismatch_is_failure(self):
        mock_finding = _make_finding("artifact.crystalline_faceting", Severity.LOW)
        mock_analyzer = MagicMock()
        mock_analyzer.analyze.return_value = [mock_finding]

        with tempfile.TemporaryDirectory() as td:
            img_path = Path(td) / "img.png"
            _write_solid_image(img_path)
            manifest = self._write_manifest(td, [
                {
                    "id": "sev_check",
                    "image_path": "img.png",
                    "private": False,
                    "context_group": "g",
                    "expectations": [
                        {
                            "analyzer_id": "crystalline_faceting_analyzer/v1",
                            "category": "artifact.crystalline_faceting",
                            "should_detect": True,
                            "expected_severity": "HIGH",
                        }
                    ],
                }
            ])
            registry = {"crystalline_faceting_analyzer/v1": mock_analyzer}
            run = run_benchmark(manifest, project_root=Path(td), registry=registry)

        self.assertEqual(run.failed, 1)
        r = run.results[0]
        self.assertEqual(r.actual_severity, "LOW")

    def test_null_expected_severity_ignores_actual(self):
        mock_finding = _make_finding("texture.high_microtexture", Severity.CRITICAL)
        mock_analyzer = MagicMock()
        mock_analyzer.analyze.return_value = [mock_finding]

        with tempfile.TemporaryDirectory() as td:
            img_path = Path(td) / "img.png"
            _write_solid_image(img_path)
            manifest = self._write_manifest(td, [
                {
                    "id": "any_sev",
                    "image_path": "img.png",
                    "private": False,
                    "context_group": "g",
                    "expectations": [
                        {
                            "analyzer_id": "texture_analyzer/v1",
                            "category": "texture.high_microtexture",
                            "should_detect": True,
                            "expected_severity": None,
                        }
                    ],
                }
            ])
            registry = {"texture_analyzer/v1": mock_analyzer}
            run = run_benchmark(manifest, project_root=Path(td), registry=registry)

        self.assertEqual(run.passed, 1)
        self.assertTrue(run.success)

    def test_multiple_expectations_per_case(self):
        mock_tex = MagicMock()
        mock_tex.analyze.return_value = []
        mock_cryst = MagicMock()
        mock_cryst.analyze.return_value = []

        with tempfile.TemporaryDirectory() as td:
            img_path = Path(td) / "img.png"
            _write_solid_image(img_path)
            manifest = self._write_manifest(td, [
                {
                    "id": "two_exps",
                    "image_path": "img.png",
                    "private": False,
                    "context_group": "g",
                    "expectations": [
                        {
                            "analyzer_id": "texture_analyzer/v1",
                            "category": "texture.high_microtexture",
                            "should_detect": False,
                            "expected_severity": None,
                        },
                        {
                            "analyzer_id": "crystalline_faceting_analyzer/v1",
                            "category": "artifact.crystalline_faceting",
                            "should_detect": False,
                            "expected_severity": None,
                        },
                    ],
                }
            ])
            registry = {
                "texture_analyzer/v1": mock_tex,
                "crystalline_faceting_analyzer/v1": mock_cryst,
            }
            run = run_benchmark(manifest, project_root=Path(td), registry=registry)

        self.assertEqual(run.total, 2)
        self.assertEqual(run.passed, 2)

    def test_output_files_written_by_runner(self):
        mock_analyzer = MagicMock()
        mock_analyzer.analyze.return_value = []

        with tempfile.TemporaryDirectory() as td:
            img_path = Path(td) / "img.png"
            _write_solid_image(img_path)
            manifest = self._write_manifest(td, [
                {
                    "id": "write_test",
                    "image_path": "img.png",
                    "private": False,
                    "context_group": "g",
                    "expectations": [
                        {
                            "analyzer_id": "texture_analyzer/v1",
                            "category": "texture.high_microtexture",
                            "should_detect": False,
                            "expected_severity": None,
                        }
                    ],
                }
            ])
            registry = {"texture_analyzer/v1": mock_analyzer}
            run = run_benchmark(manifest, project_root=Path(td), registry=registry)

            out_dir = Path(td) / "results"
            out_dir.mkdir()
            json_out = out_dir / "results.json"
            txt_out  = out_dir / "results.txt"
            write_json_results(run, json_out)
            write_txt_results(run, txt_out)

            self.assertTrue(json_out.exists())
            self.assertTrue(txt_out.exists())
            data = json.loads(json_out.read_text("utf-8"))
            self.assertEqual(data["summary"]["total"], 1)


class TestBenchmarkAnalyzerRegistry(unittest.TestCase):
    def test_benchmark_registry_comes_from_analyzer_registry(self):
        self.assertEqual(
            tuple(_ANALYZER_REGISTRY),
            tuple(create_analyzer_registry()),
        )

    def test_benchmark_context_uses_complete_analyzer_versions(self):
        with tempfile.TemporaryDirectory() as td:
            image_path = Path(td) / "img.png"
            _write_solid_image(image_path)
            context, _ = _build_context_for_group([image_path])

        self.assertEqual(context.analyzer_versions, analyzer_versions())


if __name__ == "__main__":
    unittest.main()
