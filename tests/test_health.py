"""Tests for the Dataset Health Report (src/dataset_forge/analysis/health.py)."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from dataset_forge.analysis.health import (
    generate_health_report,
    ConsistencyScores,
    DatasetHealthReport,
    LoRAReadiness,
)
from dataset_forge.analysis.texture import (
    TextureImageResult,
    TextureReportSummary,
    generate_texture_report,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_result(
    filename: str = "img.jpg",
    *,
    status: str = "analyzed",
    microtexture: float = 30.0,
    highlight_speck: float = 10.0,
    watercolor_smoothness: float = 65.0,
    texture_consistency: float = 70.0,
    engine_recommendation: str = "LEAVE_ALONE",
    engine_confidence: int = 88,
    engine_deciding_factor: str = "low_net_benefit",
    engine_explanation: str = "No intervention needed.",
) -> TextureImageResult:
    return TextureImageResult(
        filename=filename,
        original_path=f"/fake/{filename}",
        status=status,
        microtexture_density_score=microtexture,
        local_contrast_score=40.0,
        edge_sharpness_score=50.0,
        highlight_speck_score=highlight_speck,
        texture_consistency_score=texture_consistency,
        watercolor_smoothness_score=watercolor_smoothness,
        pencil_grain_score=30.0,
        representative_score=60.0,
        cleanliness_score=70.0,
        texture_delta_from_average=0.0,
        recommendation="KEEP",
        explanation="Looks good.",
        engine_recommendation=engine_recommendation,
        engine_confidence=engine_confidence,
        engine_deciding_factor=engine_deciding_factor,
        engine_explanation=engine_explanation,
    )


def _make_summary(
    results: list[TextureImageResult],
    average: float = 30.0,
    stddev: float = 5.0,
) -> TextureReportSummary:
    analyzed = [r for r in results if r.status == "analyzed"]
    return TextureReportSummary(
        total_images=len(results),
        analyzed_images=len(analyzed),
        error_images=len(results) - len(analyzed),
        average_microtexture_density=average,
        microtexture_standard_deviation=stddev,
        above_average_outliers=[],
        below_average_outliers=[],
        most_over_textured=analyzed[0].filename if analyzed else "",
        most_under_textured=analyzed[0].filename if analyzed else "",
        most_representative=analyzed[0].filename if analyzed else "",
        cleanest=analyzed[0].filename if analyzed else "",
        recommendation_counts={"KEEP": len(analyzed)},
    )


def _all_leave_alone(n: int = 10) -> tuple[list[TextureImageResult], TextureReportSummary]:
    results = [_make_result(f"img_{i}.jpg") for i in range(n)]
    summary = _make_summary(results)
    return results, summary


# ---------------------------------------------------------------------------
# JSON schema tests
# ---------------------------------------------------------------------------

class TestJSONSchema(unittest.TestCase):
    def test_required_top_level_keys(self) -> None:
        with TemporaryDirectory() as tmp:
            results, summary = _all_leave_alone()
            generate_health_report(results, summary, Path(tmp))
            data = json.loads(
                (Path(tmp) / "dataset_health_report.json").read_text(encoding="utf-8")
            )
        required = {
            "version", "generated_at", "executive_summary",
            "decision_engine_summary", "cleanup_summary", "dataset_statistics",
            "consistency_scores", "lora_readiness", "export_guidance",
            "future_sections",
        }
        self.assertEqual(required, required & data.keys())

    def test_future_sections_all_null(self) -> None:
        with TemporaryDirectory() as tmp:
            results, summary = _all_leave_alone()
            generate_health_report(results, summary, Path(tmp))
            data = json.loads(
                (Path(tmp) / "dataset_health_report.json").read_text(encoding="utf-8")
            )
        fs = data["future_sections"]
        expected_keys = {
            "ai_conservator_statistics", "caption_quality", "prompt_consistency",
            "lora_validation_results", "training_history", "style_clustering",
            "outlier_detection",
        }
        self.assertEqual(expected_keys, expected_keys & fs.keys())
        for k in expected_keys:
            self.assertIsNone(fs[k], msg=f"future_sections.{k} should be null")

    def test_future_data_fields_null(self) -> None:
        with TemporaryDirectory() as tmp:
            results, summary = _all_leave_alone()
            generate_health_report(results, summary, Path(tmp))
            data = json.loads(
                (Path(tmp) / "dataset_health_report.json").read_text(encoding="utf-8")
            )
        future = data["dataset_statistics"]["future"]
        for k in ("caption_completeness", "caption_consistency", "prompt_consistency"):
            self.assertIn(k, future)
            self.assertIsNone(future[k])

    def test_executive_summary_keys(self) -> None:
        with TemporaryDirectory() as tmp:
            results, summary = _all_leave_alone()
            generate_health_report(results, summary, Path(tmp))
            data = json.loads(
                (Path(tmp) / "dataset_health_report.json").read_text(encoding="utf-8")
            )
        es = data["executive_summary"]
        for key in (
            "total_images", "analyzed_images", "error_images",
            "dataset_health_score", "lora_readiness_score",
            "lora_readiness_disclaimer", "headline", "recommendations",
        ):
            self.assertIn(key, es)

    def test_decision_engine_summary_keys(self) -> None:
        with TemporaryDirectory() as tmp:
            results, summary = _all_leave_alone()
            generate_health_report(results, summary, Path(tmp))
            data = json.loads(
                (Path(tmp) / "dataset_health_report.json").read_text(encoding="utf-8")
            )
        des = data["decision_engine_summary"]
        for key in (
            "leave_alone_count", "leave_alone_pct",
            "deterministic_only_count", "deterministic_only_pct",
            "ai_conservation_count", "ai_conservation_pct",
            "manual_review_count", "manual_review_pct",
            "intervention_ratio", "high_confidence_decisions",
            "low_confidence_decisions",
        ):
            self.assertIn(key, des)

    def test_cleanup_summary_not_applied(self) -> None:
        with TemporaryDirectory() as tmp:
            results, summary = _all_leave_alone()
            generate_health_report(results, summary, Path(tmp))
            data = json.loads(
                (Path(tmp) / "dataset_health_report.json").read_text(encoding="utf-8")
            )
        cs = data["cleanup_summary"]
        self.assertEqual(cs["status"], "not_applied")
        self.assertIn("projected_images_to_clean", cs)

    def test_cleanup_summary_applied(self) -> None:
        with TemporaryDirectory() as tmp:
            results, summary = _all_leave_alone()
            cleanup_report = {"images_cleaned": 3, "images_rejected": 0}
            generate_health_report(
                results, summary, Path(tmp),
                cleanup_execution_report=cleanup_report,
            )
            data = json.loads(
                (Path(tmp) / "dataset_health_report.json").read_text(encoding="utf-8")
            )
        self.assertEqual(data["cleanup_summary"]["status"], "applied")

    def test_version_is_1(self) -> None:
        with TemporaryDirectory() as tmp:
            results, summary = _all_leave_alone()
            generate_health_report(results, summary, Path(tmp))
            data = json.loads(
                (Path(tmp) / "dataset_health_report.json").read_text(encoding="utf-8")
            )
        self.assertEqual(data["version"], 1)


# ---------------------------------------------------------------------------
# Score calculation tests
# ---------------------------------------------------------------------------

class TestScoreCalculation(unittest.TestCase):
    def test_health_score_is_0_to_100(self) -> None:
        results, summary = _all_leave_alone()
        with TemporaryDirectory() as tmp:
            report = generate_health_report(results, summary, Path(tmp))
        self.assertGreaterEqual(report.dataset_health_score, 0.0)
        self.assertLessEqual(report.dataset_health_score, 100.0)

    def test_readiness_score_is_int_0_to_100(self) -> None:
        results, summary = _all_leave_alone()
        with TemporaryDirectory() as tmp:
            report = generate_health_report(results, summary, Path(tmp))
        self.assertIsInstance(report.lora_readiness_score, int)
        self.assertGreaterEqual(report.lora_readiness_score, 0)
        self.assertLessEqual(report.lora_readiness_score, 100)

    def test_many_manual_review_lowers_readiness(self) -> None:
        clean_results = [_make_result(f"c{i}.jpg") for i in range(60)]
        mr_results = [
            _make_result(
                f"mr{i}.jpg",
                microtexture=60.0,
                engine_recommendation="MANUAL_REVIEW",
                engine_confidence=50,
            )
            for i in range(40)
        ]
        results = clean_results + mr_results
        summary = _make_summary(results, average=42.0, stddev=15.0)
        with TemporaryDirectory() as tmp:
            report_heavy = generate_health_report(results, summary, Path(tmp))
        with TemporaryDirectory() as tmp2:
            clean_only_results, clean_summary = _all_leave_alone(100)
            report_clean = generate_health_report(clean_only_results, clean_summary, Path(tmp2))
        self.assertLess(
            report_heavy.lora_readiness_score,
            report_clean.lora_readiness_score,
        )

    def test_no_penalty_on_all_leave_alone(self) -> None:
        results, summary = _all_leave_alone(50)
        with TemporaryDirectory() as tmp:
            report = generate_health_report(results, summary, Path(tmp))
        # Only gap-from-reference penalty should apply (30 − 26.86 = ~3.14, under 10)
        pb = report.lora_readiness.penalty_breakdown
        self.assertNotIn("manual_review_penalty", pb)
        self.assertNotIn("ai_conservation_penalty", pb)
        self.assertNotIn("high_intervention_ratio_penalty", pb)

    def test_duplicate_penalty_applied(self) -> None:
        results, summary = _all_leave_alone()
        with TemporaryDirectory() as tmp:
            report_no_dup = generate_health_report(results, summary, Path(tmp))
        with TemporaryDirectory() as tmp2:
            report_with_dup = generate_health_report(
                results, summary, Path(tmp2), duplicate_count=5
            )
        self.assertLess(
            report_with_dup.lora_readiness_score,
            report_no_dup.lora_readiness_score,
        )

    def test_high_microtexture_above_v1_ceiling_penalty(self) -> None:
        results = [
            _make_result(f"img{i}.jpg", microtexture=55.0, engine_recommendation="MANUAL_REVIEW", engine_confidence=50)
            for i in range(10)
        ]
        summary = _make_summary(results, average=55.0, stddev=5.0)
        with TemporaryDirectory() as tmp:
            report = generate_health_report(results, summary, Path(tmp))
        pb = report.lora_readiness.penalty_breakdown
        self.assertIn("above_v1_ceiling_penalty", pb)

    def test_error_images_penalty(self) -> None:
        good = [_make_result(f"g{i}.jpg") for i in range(9)]
        bad = [_make_result(f"e{i}.jpg", status="error") for i in range(5)]
        results = good + bad
        summary = _make_summary(results)
        with TemporaryDirectory() as tmp:
            report = generate_health_report(results, summary, Path(tmp))
        pb = report.lora_readiness.penalty_breakdown
        self.assertIn("error_rate_penalty", pb)

    def test_consistency_overall_no_crash_without_resolution(self) -> None:
        results, summary = _all_leave_alone()
        with TemporaryDirectory() as tmp:
            report = generate_health_report(results, summary, Path(tmp))
        cs = report.consistency_scores
        self.assertIsNone(cs.resolution_consistency)
        self.assertIsNone(cs.aspect_ratio_consistency)
        self.assertGreaterEqual(cs.overall_dataset_consistency, 0.0)
        self.assertLessEqual(cs.overall_dataset_consistency, 100.0)

    def test_deterministic(self) -> None:
        results, summary = _all_leave_alone()
        with TemporaryDirectory() as tmp1:
            r1 = generate_health_report(results, summary, Path(tmp1))
        with TemporaryDirectory() as tmp2:
            r2 = generate_health_report(results, summary, Path(tmp2))
        # Exclude generated_at timestamp from comparison
        d1 = r1.to_dict()
        d2 = r2.to_dict()
        d1.pop("generated_at"); d2.pop("generated_at")
        self.assertEqual(d1, d2)


# ---------------------------------------------------------------------------
# Recommendation generation tests
# ---------------------------------------------------------------------------

class TestRecommendations(unittest.TestCase):
    def test_positive_statement_when_leave_alone_majority(self) -> None:
        results, summary = _all_leave_alone(10)
        with TemporaryDirectory() as tmp:
            report = generate_health_report(results, summary, Path(tmp))
        recs = "\n".join(report.recommendations)
        self.assertIn("already excellent training examples", recs)

    def test_no_cleanup_rec_when_all_leave_alone(self) -> None:
        results, summary = _all_leave_alone(10)
        with TemporaryDirectory() as tmp:
            report = generate_health_report(results, summary, Path(tmp))
        recs = "\n".join(report.recommendations)
        self.assertNotIn("Run deterministic cleanup", recs)

    def test_cleanup_rec_when_deterministic_only(self) -> None:
        results = [
            _make_result(
                f"img{i}.jpg",
                engine_recommendation="DETERMINISTIC_ONLY",
                engine_confidence=91,
            )
            for i in range(5)
        ]
        summary = _make_summary(results)
        with TemporaryDirectory() as tmp:
            report = generate_health_report(results, summary, Path(tmp))
        recs = "\n".join(report.recommendations)
        self.assertIn("deterministic cleanup", recs.lower())

    def test_duplicate_warning_when_duplicates(self) -> None:
        results, summary = _all_leave_alone()
        with TemporaryDirectory() as tmp:
            report = generate_health_report(
                results, summary, Path(tmp), duplicate_count=3
            )
        recs = "\n".join(report.recommendations)
        self.assertIn("duplicate", recs.lower())

    def test_error_warning_when_errors(self) -> None:
        good = [_make_result("ok.jpg")]
        bad = [_make_result("bad.jpg", status="error")]
        results = good + bad
        summary = _make_summary(results)
        with TemporaryDirectory() as tmp:
            report = generate_health_report(results, summary, Path(tmp))
        recs = "\n".join(report.recommendations)
        self.assertIn("could not be analyzed", recs)

    def test_restraint_statement_low_intervention(self) -> None:
        # All LEAVE_ALONE = 0% intervention
        results, summary = _all_leave_alone(20)
        with TemporaryDirectory() as tmp:
            report = generate_health_report(results, summary, Path(tmp))
        recs = "\n".join(report.recommendations)
        self.assertIn("expected benefit of further cleanup is low", recs)

    def test_export_ready_now_when_no_actions(self) -> None:
        results, summary = _all_leave_alone()
        with TemporaryDirectory() as tmp:
            report = generate_health_report(results, summary, Path(tmp))
        last_rec = report.recommendations[-1]
        self.assertIn("Ready for LoRA export", last_rec)

    def test_export_after_actions_when_cleanup_needed(self) -> None:
        results = [
            _make_result(f"img{i}.jpg", engine_recommendation="DETERMINISTIC_ONLY", engine_confidence=91)
            for i in range(5)
        ]
        summary = _make_summary(results)
        with TemporaryDirectory() as tmp:
            report = generate_health_report(results, summary, Path(tmp))
        last_rec = report.recommendations[-1]
        self.assertIn("Ready for LoRA export", last_rec)

    def test_ai_backend_not_configured_note(self) -> None:
        results = [
            _make_result(
                f"img{i}.jpg",
                microtexture=55.0,
                engine_recommendation="MANUAL_REVIEW",
                engine_confidence=50,
            )
            for i in range(5)
        ]
        summary = _make_summary(results, average=55.0)
        with TemporaryDirectory() as tmp:
            report = generate_health_report(results, summary, Path(tmp))
        recs = "\n".join(report.recommendations)
        self.assertIn("No AI conservation backend is configured", recs)


# ---------------------------------------------------------------------------
# Positive reporting tests
# ---------------------------------------------------------------------------

class TestPositiveReporting(unittest.TestCase):
    def test_all_leave_alone_headline_positive(self) -> None:
        results, summary = _all_leave_alone(100)
        with TemporaryDirectory() as tmp:
            report = generate_health_report(results, summary, Path(tmp))
        # Headline should not say "requires" anything
        self.assertNotIn("requires", report.headline.lower())

    def test_all_leave_alone_no_intervention_suggestions(self) -> None:
        results, summary = _all_leave_alone(50)
        with TemporaryDirectory() as tmp:
            report = generate_health_report(results, summary, Path(tmp))
        recs = "\n".join(report.recommendations)
        self.assertNotIn("Run deterministic cleanup", recs)
        self.assertNotIn("AI conservation", recs.split("No AI")[0] if "No AI" in recs else recs)

    def test_positive_rec_is_first_when_warranted(self) -> None:
        results, summary = _all_leave_alone(10)
        with TemporaryDirectory() as tmp:
            report = generate_health_report(results, summary, Path(tmp))
        self.assertIn("excellent training examples", report.recommendations[0])

    def test_high_leave_alone_does_not_manufacture_interventions(self) -> None:
        # 80% LEAVE_ALONE, 20% DETERMINISTIC
        la = [_make_result(f"la{i}.jpg") for i in range(80)]
        det = [
            _make_result(
                f"det{i}.jpg",
                engine_recommendation="DETERMINISTIC_ONLY",
                engine_confidence=91,
            )
            for i in range(20)
        ]
        results = la + det
        summary = _make_summary(results)
        with TemporaryDirectory() as tmp:
            report = generate_health_report(results, summary, Path(tmp))
        recs = report.recommendations
        # First rec should still be positive
        self.assertIn("excellent training examples", recs[0])
        # Should have cleanup rec but nothing invented
        self.assertTrue(any("deterministic cleanup" in r.lower() for r in recs))
        # Should NOT have AI candidate rec (none present)
        self.assertFalse(
            any("AI conservation candidate" in r for r in recs
                if "No AI" not in r),
        )


# ---------------------------------------------------------------------------
# Disclaimer tests
# ---------------------------------------------------------------------------

class TestDisclaimer(unittest.TestCase):
    def test_disclaimer_in_json(self) -> None:
        with TemporaryDirectory() as tmp:
            results, summary = _all_leave_alone()
            generate_health_report(results, summary, Path(tmp))
            data = json.loads(
                (Path(tmp) / "dataset_health_report.json").read_text(encoding="utf-8")
            )
        disclaimer = data["lora_readiness"]["disclaimer"]
        self.assertIn("estimate", disclaimer.lower())
        self.assertIn("not predict", disclaimer.lower())

    def test_disclaimer_in_executive_summary(self) -> None:
        with TemporaryDirectory() as tmp:
            results, summary = _all_leave_alone()
            generate_health_report(results, summary, Path(tmp))
            data = json.loads(
                (Path(tmp) / "dataset_health_report.json").read_text(encoding="utf-8")
            )
        es = data["executive_summary"]
        self.assertIn("lora_readiness_disclaimer", es)
        self.assertIn("estimate", es["lora_readiness_disclaimer"].lower())

    def test_disclaimer_in_html(self) -> None:
        with TemporaryDirectory() as tmp:
            results, summary = _all_leave_alone()
            generate_health_report(results, summary, Path(tmp))
            html_text = (Path(tmp) / "dataset_health_report.html").read_text(
                encoding="utf-8"
            )
        self.assertIn("estimate", html_text.lower())
        self.assertIn("not predict", html_text.lower())


# ---------------------------------------------------------------------------
# Output file tests
# ---------------------------------------------------------------------------

class TestOutputFiles(unittest.TestCase):
    def _run(self, tmp: str) -> None:
        results, summary = _all_leave_alone()
        generate_health_report(results, summary, Path(tmp))

    def test_json_file_exists(self) -> None:
        with TemporaryDirectory() as tmp:
            self._run(tmp)
            self.assertTrue((Path(tmp) / "dataset_health_report.json").is_file())

    def test_html_file_exists(self) -> None:
        with TemporaryDirectory() as tmp:
            self._run(tmp)
            self.assertTrue((Path(tmp) / "dataset_health_report.html").is_file())

    def test_txt_file_exists(self) -> None:
        with TemporaryDirectory() as tmp:
            self._run(tmp)
            self.assertTrue((Path(tmp) / "dataset_health_report.txt").is_file())

    def test_html_is_offline(self) -> None:
        with TemporaryDirectory() as tmp:
            self._run(tmp)
            content = (Path(tmp) / "dataset_health_report.html").read_text(
                encoding="utf-8"
            )
        self.assertNotIn("https://", content)
        self.assertNotIn("http://", content)

    def test_html_has_required_sections(self) -> None:
        with TemporaryDirectory() as tmp:
            self._run(tmp)
            content = (Path(tmp) / "dataset_health_report.html").read_text(
                encoding="utf-8"
            )
        for section in (
            "Executive Summary",
            "Decision Engine Summary",
            "Consistency Scores",
            "Dataset Statistics",
            "Cleanup Summary",
            "Export Guidance",
            "LoRA Readiness",
        ):
            self.assertIn(section, content, msg=f"HTML missing section: {section}")

    def test_txt_contains_scores(self) -> None:
        with TemporaryDirectory() as tmp:
            self._run(tmp)
            content = (Path(tmp) / "dataset_health_report.txt").read_text(
                encoding="utf-8"
            )
        self.assertIn("Dataset Health", content)
        self.assertIn("LoRA Readiness", content)
        self.assertIn("Export Guidance", content)

    def test_json_is_valid(self) -> None:
        with TemporaryDirectory() as tmp:
            self._run(tmp)
            text = (Path(tmp) / "dataset_health_report.json").read_text(
                encoding="utf-8"
            )
        data = json.loads(text)
        self.assertIsInstance(data, dict)

    def test_existing_reports_untouched(self) -> None:
        """generate_health_report must not overwrite texture_report.* files."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Write a sentinel texture report
            sentinel = root / "texture_report.json"
            sentinel.write_text('{"sentinel": true}', encoding="utf-8")
            results, summary = _all_leave_alone()
            generate_health_report(results, summary, root)
            content = json.loads(sentinel.read_text(encoding="utf-8"))
        self.assertEqual(content, {"sentinel": True})


# ---------------------------------------------------------------------------
# Non-destructive tests
# ---------------------------------------------------------------------------

class TestNonDestructive(unittest.TestCase):
    def test_source_images_unmodified(self) -> None:
        """health report must not open, modify, or write to source images."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "source"
            out = root / "output"
            src.mkdir()
            # Write two real images
            img_a = src / "a.png"
            img_b = src / "b.png"
            Image.new("RGB", (64, 64), "red").save(img_a)
            Image.new("RGB", (64, 64), "blue").save(img_b)
            before_a = img_a.read_bytes()
            before_b = img_b.read_bytes()
            mtime_a = img_a.stat().st_mtime
            mtime_b = img_b.stat().st_mtime

            # Run texture report then health report
            summary_obj = generate_texture_report(
                src, out, create_thumbnails=False
            )
            # Load results from JSON (simulate real pipeline)
            import csv as csv_mod
            with (out / "texture_report.csv").open(encoding="utf-8") as f:
                rows = list(csv_mod.DictReader(f))
            results = [
                TextureImageResult(
                    filename=r["filename"],
                    original_path=r["original_path"],
                    status=r["status"],
                    microtexture_density_score=float(r["microtexture_density_score"]),
                    local_contrast_score=float(r["local_contrast_score"]),
                    edge_sharpness_score=float(r["edge_sharpness_score"]),
                    highlight_speck_score=float(r["highlight_speck_score"]),
                    texture_consistency_score=float(r["texture_consistency_score"]),
                    watercolor_smoothness_score=float(r["watercolor_smoothness_score"]),
                    pencil_grain_score=float(r["pencil_grain_score"]),
                    representative_score=float(r["representative_score"]),
                    cleanliness_score=float(r["cleanliness_score"]),
                    texture_delta_from_average=float(r["texture_delta_from_average"]),
                    recommendation=r["recommendation"],
                    explanation=r["explanation"],
                    engine_recommendation=r.get("engine_recommendation", ""),
                    engine_confidence=int(r.get("engine_confidence", 0)),
                    engine_deciding_factor=r.get("engine_deciding_factor", ""),
                    engine_explanation=r.get("engine_explanation", ""),
                )
                for r in rows
            ]
            generate_health_report(results, summary_obj, out)

            # Source images must be identical
            self.assertEqual(img_a.read_bytes(), before_a)
            self.assertEqual(img_b.read_bytes(), before_b)
            self.assertAlmostEqual(img_a.stat().st_mtime, mtime_a, places=1)
            self.assertAlmostEqual(img_b.stat().st_mtime, mtime_b, places=1)


# ---------------------------------------------------------------------------
# Existing behaviour guard
# ---------------------------------------------------------------------------

class TestExistingBehaviourUnchanged(unittest.TestCase):
    def test_texture_report_fields_unchanged(self) -> None:
        from dataset_forge.analysis.texture import TextureImageResult
        fields = set(TextureImageResult.__dataclass_fields__)
        # All original fields still present
        for f in (
            "filename", "original_path", "status", "error",
            "microtexture_density_score", "local_contrast_score",
            "edge_sharpness_score", "highlight_speck_score",
            "texture_consistency_score", "watercolor_smoothness_score",
            "pencil_grain_score", "representative_score", "cleanliness_score",
            "texture_delta_from_average", "recommendation", "explanation",
        ):
            self.assertIn(f, fields, msg=f"Field {f!r} removed from TextureImageResult")

    def test_recommend_evidence_still_importable(self) -> None:
        from dataset_forge.recommendations.engine import recommend_evidence
        self.assertTrue(callable(recommend_evidence))

    def test_health_py_does_not_import_cleanup(self) -> None:
        """health.py must not import cleanup or transformation modules."""
        import pathlib
        src = pathlib.Path("src/dataset_forge/analysis/health.py").read_text(
            encoding="utf-8"
        )
        forbidden = ["from dataset_forge.cleanup", "import cleanup"]
        for phrase in forbidden:
            self.assertNotIn(phrase, src, msg=f"health.py imports cleanup: {phrase!r}")

    def test_generate_texture_report_still_works(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "src"
            src.mkdir()
            Image.new("RGB", (64, 64), "green").save(src / "test.png")
            summary = generate_texture_report(
                src, root / "out", create_thumbnails=False
            )
        self.assertEqual(summary.analyzed_images, 1)
        self.assertEqual(summary.error_images, 0)


# ---------------------------------------------------------------------------
# Integration: run against real dataset output
# ---------------------------------------------------------------------------

class TestIntegrationWithRealRun(unittest.TestCase):
    """Smoke-test against the ANTHROPOMORPHS CSV produced in earlier sessions."""

    CSV_PATH = Path(
        "C:/Users/someo/AppData/Local/Temp/df_lora/decision_engine_run2"
        "/texture_report.csv"
    )

    def setUp(self) -> None:
        if not self.CSV_PATH.exists():
            self.skipTest("Real dataset CSV not available in this environment")

    def test_health_report_from_real_dataset(self) -> None:
        import csv as csv_mod
        with self.CSV_PATH.open(encoding="utf-8") as f:
            rows = list(csv_mod.DictReader(f))

        results = []
        for r in rows:
            results.append(TextureImageResult(
                filename=r["filename"],
                original_path=r["original_path"],
                status=r["status"],
                microtexture_density_score=float(r.get("microtexture_density_score", 0)),
                local_contrast_score=float(r.get("local_contrast_score", 0)),
                edge_sharpness_score=float(r.get("edge_sharpness_score", 0)),
                highlight_speck_score=float(r.get("highlight_speck_score", 0)),
                texture_consistency_score=float(r.get("texture_consistency_score", 0)),
                watercolor_smoothness_score=float(r.get("watercolor_smoothness_score", 0)),
                pencil_grain_score=float(r.get("pencil_grain_score", 0)),
                representative_score=float(r.get("representative_score", 0)),
                cleanliness_score=float(r.get("cleanliness_score", 0)),
                texture_delta_from_average=float(r.get("texture_delta_from_average", 0)),
                recommendation=r.get("recommendation", ""),
                explanation=r.get("explanation", ""),
                engine_recommendation=r.get("engine_recommendation", ""),
                engine_confidence=int(r.get("engine_confidence", 0)),
                engine_deciding_factor=r.get("engine_deciding_factor", ""),
                engine_explanation=r.get("engine_explanation", ""),
            ))

        analyzed = [r for r in results if r.status == "analyzed"]
        import statistics as st
        vals = [r.microtexture_density_score for r in analyzed]
        avg = st.mean(vals) if vals else 0.0
        std = st.pstdev(vals) if vals else 0.0

        summary = TextureReportSummary(
            total_images=len(results),
            analyzed_images=len(analyzed),
            error_images=len(results) - len(analyzed),
            average_microtexture_density=round(avg, 2),
            microtexture_standard_deviation=round(std, 2),
            above_average_outliers=[],
            below_average_outliers=[],
            most_over_textured="",
            most_under_textured="",
            most_representative="",
            cleanest="",
            recommendation_counts={},
        )

        with TemporaryDirectory() as tmp:
            report = generate_health_report(results, summary, Path(tmp))

            # Basic sanity
            self.assertEqual(report.total_images, 100)
            self.assertEqual(report.analyzed_images, 100)
            self.assertEqual(report.leave_alone_count, 51)
            self.assertEqual(report.deterministic_only_count, 25)
            self.assertEqual(report.manual_review_count, 24)
            self.assertEqual(report.ai_conservation_count, 0)

            # Readiness should be ~83 per spec example
            self.assertGreaterEqual(report.lora_readiness_score, 75)
            self.assertLessEqual(report.lora_readiness_score, 90)

            # Files written
            self.assertTrue((Path(tmp) / "dataset_health_report.json").is_file())
            self.assertTrue((Path(tmp) / "dataset_health_report.html").is_file())
            self.assertTrue((Path(tmp) / "dataset_health_report.txt").is_file())

            print(f"\nANTHROPOMORPHS Health Score:    {report.dataset_health_score:.0f}/100")
            print(f"ANTHROPOMORPHS LoRA Readiness:  {report.lora_readiness_score}/100")
            print(f"Headline: {report.headline}")
            print("Recommendations:")
            for r in report.recommendations:
                print(f"  * {r}")


if __name__ == "__main__":
    unittest.main()
