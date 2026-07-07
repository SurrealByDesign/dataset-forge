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
from dataset_forge.recommendation_summary import (
    NEEDS_REVIEW,
    PRIORITY_REVIEW,
    READY_FOR_TRAINING,
    RECOMMENDATION_SUMMARY_SCHEMA,
    build_recommendation_summary,
    build_recommendation_summary_from_report,
    render_recommendation_summary_markdown,
    write_recommendation_summary_files,
)
from dataset_forge.review_persistence import ReviewStatus


def _context(image_count: int = 4) -> DatasetContext:
    return DatasetContext(
        schema_version=CONTEXT_SCHEMA_VERSION,
        analyzer_versions={"texture_analyzer": "v1"},
        image_paths=tuple(Path(f"img_{index}.png") for index in range(image_count)),
        image_count=image_count,
        error_count=0,
        resolution_stats=ResolutionStats.empty(),
        aspect_ratio_stats=AspectRatioStats.empty(),
        texture_distributions=TextureDistributions.empty(),
        frequency_distributions=FrequencyDistributions.empty(),
        duplicate_hashes=frozenset(),
        duplicate_groups=(),
    )


def _finding(
    image_path: str,
    *,
    severity: Severity = Severity.LOW,
    category: str = "texture.high_microtexture",
    analyzer: str = "texture_analyzer/v1",
) -> Finding:
    return Finding(
        image_path=Path(image_path),
        analyzer=analyzer,
        category=category,
        severity=severity,
        confidence=0.4,
        false_positive_rate=0.2,
        benchmark_version="uncalibrated",
        evidence={"calibrated": False},
        explanation="test finding",
        recommendation="review",
    )


def _recommendations_by_name(findings: list[Finding]) -> dict[str, dict]:
    summary = build_recommendation_summary(findings, _context()).to_dict()
    return {
        Path(item["image_path"]).name: item
        for item in summary["recommendations"]
    }


class RecommendationRuleTests(unittest.TestCase):
    def test_no_findings_maps_to_no_findings_emitted(self) -> None:
        item = _recommendations_by_name([])["img_0.png"]

        self.assertEqual(item["recommendation"], READY_FOR_TRAINING)
        self.assertEqual(item["display_label"], "No Findings Emitted")
        self.assertEqual(item["reason_codes"], ["no_findings"])
        self.assertIn("no current review finding", item["guidance"])

    def test_low_finding_maps_to_needs_review(self) -> None:
        item = _recommendations_by_name([
            _finding("img_0.png", severity=Severity.LOW),
        ])["img_0.png"]

        self.assertEqual(item["recommendation"], NEEDS_REVIEW)
        self.assertEqual(item["reason_codes"], ["finding.present"])

    def test_medium_finding_maps_to_needs_review(self) -> None:
        item = _recommendations_by_name([
            _finding("img_0.png", severity=Severity.MEDIUM),
        ])["img_0.png"]

        self.assertEqual(item["recommendation"], NEEDS_REVIEW)
        self.assertEqual(item["reason_codes"], ["finding.present"])

    def test_high_finding_maps_to_priority_review(self) -> None:
        item = _recommendations_by_name([
            _finding("img_0.png", severity=Severity.HIGH),
        ])["img_0.png"]

        self.assertEqual(item["recommendation"], PRIORITY_REVIEW)
        self.assertEqual(item["reason_codes"], ["finding.high_severity"])

    def test_critical_finding_maps_to_priority_review(self) -> None:
        item = _recommendations_by_name([
            _finding("img_0.png", severity=Severity.CRITICAL),
        ])["img_0.png"]

        self.assertEqual(item["recommendation"], PRIORITY_REVIEW)
        self.assertEqual(item["reason_codes"], ["finding.high_severity"])

    def test_multiple_categories_map_to_priority_review(self) -> None:
        item = _recommendations_by_name([
            _finding("img_0.png", category="texture.high_microtexture"),
            _finding(
                "img_0.png",
                category="artifact.oversharpening_halo",
                analyzer="oversharpening_halo_analyzer/v1",
            ),
        ])["img_0.png"]

        self.assertEqual(item["recommendation"], PRIORITY_REVIEW)
        self.assertEqual(item["reason_codes"], ["finding.multiple_categories"])

    def test_analyzer_error_maps_to_priority_review(self) -> None:
        item = _recommendations_by_name([
            _finding("img_0.png", category="texture.error"),
        ])["img_0.png"]

        self.assertEqual(item["recommendation"], PRIORITY_REVIEW)
        self.assertEqual(item["reason_codes"], ["analyzer_error"])

    def test_analyzer_error_reason_wins_over_finding_reason(self) -> None:
        item = _recommendations_by_name([
            _finding("img_0.png", category="texture.error"),
            _finding(
                "img_0.png",
                category="artifact.oversharpening_halo",
                analyzer="oversharpening_halo_analyzer/v1",
                severity=Severity.HIGH,
            ),
        ])["img_0.png"]

        self.assertEqual(item["recommendation"], PRIORITY_REVIEW)
        self.assertEqual(item["reason_codes"], ["analyzer_error"])
        self.assertIn("could not inspect", item["primary_reason"])


class RecommendationContractTests(unittest.TestCase):
    def test_summary_counts_are_correct(self) -> None:
        payload = build_recommendation_summary(
            [
                _finding("img_0.png", severity=Severity.HIGH),
                _finding("img_1.png", severity=Severity.MEDIUM),
            ],
            _context(),
        ).to_dict()

        self.assertEqual(payload["schema"], RECOMMENDATION_SUMMARY_SCHEMA)
        self.assertEqual(payload["summary"]["image_count"], 4)
        self.assertEqual(payload["summary"]["priority_review_count"], 1)
        self.assertEqual(payload["summary"]["needs_review_count"], 1)
        self.assertEqual(payload["summary"]["ready_for_training_count"], 2)

    def test_output_is_json_serializable(self) -> None:
        payload = build_recommendation_summary(
            [_finding("img_0.png", severity=Severity.MEDIUM)],
            _context(),
        ).to_dict()

        self.assertIn(RECOMMENDATION_SUMMARY_SCHEMA, json.dumps(payload))

    def test_json_schema_is_stable(self) -> None:
        payload = build_recommendation_summary(
            [_finding("img_0.png", severity=Severity.MEDIUM)],
            _context(),
        ).to_dict()

        self.assertEqual(
            set(payload),
            {
                "schema",
                "source_report_schema",
                "summary",
                "analyzer_coverage",
                "recommendations",
            },
        )
        self.assertEqual(
            set(payload["summary"]),
            {
                "image_count",
                "no_findings_emitted_count",
                "ready_for_training_count",
                "needs_review_count",
                "priority_review_count",
                "analyzer_error_count",
            },
        )
        self.assertEqual(
            set(payload["recommendations"][0]),
            {
                "image_path",
                "recommendation",
                "display_label",
                "primary_reason",
                "reason_codes",
                "finding_refs",
                "findings",
                "guidance",
                "confidence_note",
            },
        )

    def test_finding_refs_expose_only_analyzer_category_and_severity(self) -> None:
        item = _recommendations_by_name([
            _finding("img_0.png", severity=Severity.MEDIUM),
        ])["img_0.png"]

        self.assertEqual(
            set(item["finding_refs"][0]),
            {"analyzer", "category", "severity"},
        )

    def test_no_numeric_quality_score_is_emitted(self) -> None:
        payload = build_recommendation_summary(
            [_finding("img_0.png", severity=Severity.MEDIUM)],
            _context(),
        ).to_dict()

        def assert_no_score_or_priority_keys(value: object) -> None:
            if isinstance(value, dict):
                self.assertNotIn("score", value)
                self.assertNotIn("priority", value)
                for child in value.values():
                    assert_no_score_or_priority_keys(child)
            elif isinstance(value, list):
                for child in value:
                    assert_no_score_or_priority_keys(child)

        assert_no_score_or_priority_keys(payload)

    def test_recommendations_are_sorted_by_group_then_severity_then_path(self) -> None:
        payload = build_recommendation_summary(
            [
                _finding("img_2.png", severity=Severity.MEDIUM),
                _finding("img_1.png", severity=Severity.HIGH),
                _finding("img_0.png", severity=Severity.CRITICAL),
            ],
            _context(),
        ).to_dict()

        self.assertEqual(
            [
                Path(item["image_path"]).name
                for item in payload["recommendations"]
            ],
            ["img_0.png", "img_1.png", "img_2.png", "img_3.png"],
        )

    def test_repeated_input_produces_identical_output(self) -> None:
        findings = [
            _finding("img_1.png", severity=Severity.HIGH),
            _finding("img_0.png", severity=Severity.MEDIUM),
        ]

        first = build_recommendation_summary(findings, _context()).to_dict()
        second = build_recommendation_summary(list(reversed(findings)), _context()).to_dict()

        self.assertEqual(first, second)

    def test_ready_text_does_not_say_clean(self) -> None:
        item = _recommendations_by_name([])["img_0.png"]

        self.assertNotIn("clean", json.dumps(item).lower())

    def test_priority_text_does_not_say_reject_delete_or_remove(self) -> None:
        item = _recommendations_by_name([
            _finding("img_0.png", severity=Severity.HIGH),
        ])["img_0.png"]
        text = json.dumps(item).lower()

        self.assertNotIn("reject", text)
        self.assertNotIn("delete", text)
        self.assertNotIn("remove", text)

    def test_confidence_note_is_advisory_and_not_calibrated_claim(self) -> None:
        item = _recommendations_by_name([
            _finding("img_0.png", severity=Severity.MEDIUM),
        ])["img_0.png"]

        self.assertIn("advisory", item["confidence_note"])
        self.assertNotIn("validated", item["confidence_note"].lower())

    def test_markdown_uses_human_review_report_structure(self) -> None:
        summary = build_recommendation_summary(
            [
                _finding("img_0.png", severity=Severity.HIGH),
                _finding("img_1.png", severity=Severity.MEDIUM),
            ],
            _context(),
        )

        markdown = render_recommendation_summary_markdown(summary)

        self.assertIn("# Dataset Recommendation Summary", markdown)
        self.assertIn("## Dataset Summary", markdown)
        self.assertIn("- Images inspected: 4", markdown)
        self.assertIn("- No Findings Emitted: 2", markdown)
        self.assertIn("- Needs Review: 1", markdown)
        self.assertIn("- Priority Review: 1", markdown)
        self.assertIn("- Most common finding categories:", markdown)
        self.assertIn("## Analyzer Coverage", markdown)
        self.assertIn("# Recommended Review Order", markdown)
        self.assertLess(
            markdown.index("## Priority Review"),
            markdown.index("## Needs Review"),
        )
        self.assertLess(
            markdown.index("## Needs Review"),
            markdown.index("# No Findings Emitted"),
        )
        self.assertIn("# Important Notes", markdown)
        self.assertIn("# Next Step", markdown)
        self.assertIn(
            "Recommendations are based only on current deterministic findings.",
            markdown,
        )
        self.assertIn("does not guarantee the image is artifact-free", markdown)

    def test_markdown_groups_review_images_by_artifact_family(self) -> None:
        summary = build_recommendation_summary(
            [
                _finding(
                    "img_0.png",
                    category="texture.error",
                    analyzer="texture_analyzer/v1",
                ),
                _finding(
                    "img_1.png",
                    severity=Severity.HIGH,
                    category="artifact.high_frequency_isolated",
                    analyzer="high_frequency_isolated_artifact_analyzer/v1",
                ),
                _finding(
                    "img_2.png",
                    severity=Severity.LOW,
                    category="artifact.oversharpening_halo",
                    analyzer="oversharpening_halo_analyzer/v1",
                ),
            ],
            _context(),
        )

        markdown = render_recommendation_summary_markdown(summary)

        self.assertIn("### Analyzer errors", markdown)
        self.assertIn("### artifact.high_frequency_isolated", markdown)
        self.assertIn("### artifact.oversharpening_halo", markdown)
        self.assertIn("#### img_0.png", markdown)
        self.assertIn("Recommendation:\nPriority Review", markdown)
        self.assertIn("Primary reason:\nDataset Forge could not inspect", markdown)
        self.assertIn("Finding categories:\n- texture.error", markdown)
        self.assertIn("Analyzer:\n- texture_analyzer/v1", markdown)
        self.assertIn("Severity:\nLOW", markdown)
        self.assertIn("Finding count:\n1", markdown)
        self.assertIn("Review Status:\nPending Review", markdown)
        self.assertIn("Decision:\nNone recorded", markdown)

    def test_markdown_displays_existing_review_decision_status(self) -> None:
        summary = build_recommendation_summary(
            [_finding("img_0.png", severity=Severity.HIGH)],
            _context(),
        )

        markdown = render_recommendation_summary_markdown(
            summary,
            review_statuses={
                "img_0.png": ReviewStatus(
                    status="Already Reviewed",
                    decisions=("Acceptable Style",),
                ),
            },
        )

        self.assertIn("Review Status:\nAlready Reviewed", markdown)
        self.assertIn("Decision:\nAcceptable Style", markdown)

    def test_markdown_uses_stable_group_and_image_ordering(self) -> None:
        summary = build_recommendation_summary(
            [
                _finding(
                    "img_2.png",
                    severity=Severity.HIGH,
                    category="artifact.oversharpening_halo",
                    analyzer="oversharpening_halo_analyzer/v1",
                ),
                _finding(
                    "img_0.png",
                    severity=Severity.HIGH,
                    category="artifact.high_frequency_isolated",
                    analyzer="high_frequency_isolated_artifact_analyzer/v1",
                ),
                _finding(
                    "img_1.png",
                    severity=Severity.MEDIUM,
                    category="texture.high_microtexture",
                    analyzer="texture_analyzer/v1",
                ),
            ],
            _context(),
        )

        markdown = render_recommendation_summary_markdown(summary)

        self.assertLess(
            markdown.index("### artifact.high_frequency_isolated"),
            markdown.index("### artifact.oversharpening_halo"),
        )
        self.assertLess(
            markdown.index("## Priority Review"),
            markdown.index("## Needs Review"),
        )
        self.assertLess(
            markdown.index("#### img_0.png"),
            markdown.index("#### img_2.png"),
        )

    def test_markdown_summarizes_ready_images_without_listing_each_one(self) -> None:
        summary = build_recommendation_summary([], _context())

        markdown = render_recommendation_summary_markdown(summary)

        self.assertIn(
            "4 images emitted no current findings requiring review.",
            markdown,
        )
        self.assertNotIn("#### img_0.png", markdown)
        self.assertNotIn("#### img_1.png", markdown)

    def test_markdown_uses_singular_image_word_for_one_ready_image(self) -> None:
        summary = build_recommendation_summary(
            [_finding("img_0.png", severity=Severity.HIGH)],
            _context(image_count=2),
        )

        markdown = render_recommendation_summary_markdown(summary)

        self.assertIn(
            "1 image emitted no current findings requiring review.",
            markdown,
        )
        self.assertNotIn("1 images emitted", markdown)

    def test_markdown_contains_required_next_step_text(self) -> None:
        summary = build_recommendation_summary([], _context())

        markdown = render_recommendation_summary_markdown(summary)

        self.assertIn("Review Priority Review images first.", markdown)
        self.assertIn("Then review Needs Review images if appropriate.", markdown)
        self.assertIn(
            "After review, decide whether each image belongs in your training dataset.",
            markdown,
        )

    def test_markdown_does_not_use_reject_remove_or_delete_language(self) -> None:
        summary = build_recommendation_summary(
            [_finding("img_0.png", severity=Severity.HIGH)],
            _context(),
        )
        text = render_recommendation_summary_markdown(summary).lower()

        self.assertNotIn("reject", text)
        self.assertNotIn("remove", text)
        self.assertNotIn("delete", text)

    def test_markdown_does_not_include_confidence_percentages(self) -> None:
        summary = build_recommendation_summary(
            [_finding("img_0.png", severity=Severity.HIGH)],
            _context(),
        )

        markdown = render_recommendation_summary_markdown(summary)

        self.assertNotIn("%", markdown)
        self.assertNotIn("confidence", markdown.lower())

    def test_rendering_markdown_does_not_change_recommendation_json(self) -> None:
        summary = build_recommendation_summary(
            [_finding("img_0.png", severity=Severity.HIGH)],
            _context(),
        )
        before = summary.to_dict()

        render_recommendation_summary_markdown(summary)

        self.assertEqual(summary.to_dict(), before)

    def test_rendering_markdown_preserves_json_bytes(self) -> None:
        summary = build_recommendation_summary(
            [_finding("img_0.png", severity=Severity.HIGH)],
            _context(),
        )
        before = json.dumps(summary.to_dict(), indent=2, ensure_ascii=False)

        render_recommendation_summary_markdown(
            summary,
            review_statuses={
                "img_0.png": ReviewStatus(
                    status="Already Reviewed",
                    decisions=("False Positive",),
                ),
            },
        )

        after = json.dumps(summary.to_dict(), indent=2, ensure_ascii=False)
        self.assertEqual(after, before)

    def test_recommendation_engine_outputs_same_v011_recommendations(self) -> None:
        summary = build_recommendation_summary(
            [
                _finding("img_0.png", category="texture.error"),
                _finding("img_1.png", severity=Severity.HIGH),
                _finding("img_2.png", severity=Severity.MEDIUM),
            ],
            _context(),
        ).to_dict()

        self.assertEqual(
            [
                (
                    Path(item["image_path"]).name,
                    item["recommendation"],
                    item["primary_reason"],
                    item["reason_codes"],
                )
                for item in summary["recommendations"]
            ],
            [
                (
                    "img_0.png",
                    PRIORITY_REVIEW,
                    "Dataset Forge could not inspect this image reliably.",
                    ["analyzer_error"],
                ),
                (
                    "img_1.png",
                    PRIORITY_REVIEW,
                    "High-severity finding detected.",
                    ["finding.high_severity"],
                ),
                (
                    "img_2.png",
                    NEEDS_REVIEW,
                    "Measurable finding detected.",
                    ["finding.present"],
                ),
                (
                    "img_3.png",
                    READY_FOR_TRAINING,
                    "No findings were emitted for this image.",
                    ["no_findings"],
                ),
            ],
        )

    def test_summary_files_are_written(self) -> None:
        summary = build_recommendation_summary([], _context())
        with tempfile.TemporaryDirectory() as tmp:
            json_path, markdown_path = write_recommendation_summary_files(
                summary,
                Path(tmp),
                review_statuses={
                    "img_0.png": ReviewStatus(
                        status="Already Reviewed",
                        decisions=("Locked",),
                    ),
                },
            )

            self.assertEqual(json_path.name, "recommendation_summary.json")
            self.assertEqual(markdown_path.name, "recommendation_summary.md")
            self.assertTrue(json_path.is_file())
            self.assertTrue(markdown_path.is_file())

    def test_recommendation_summary_can_be_reproduced_from_inspection_report(self) -> None:
        original = build_recommendation_summary(
            [
                _finding("img_0.png", severity=Severity.HIGH),
                _finding("img_1.png", severity=Severity.MEDIUM),
            ],
            _context(),
        ).to_dict()
        report = {
            "schema": "dataset-forge/inspection/v1",
            "findings": [
                _finding("img_0.png", severity=Severity.HIGH).to_dict(),
                _finding("img_1.png", severity=Severity.MEDIUM).to_dict(),
            ],
            "review_queue": {
                "items": [
                    {"image_path": "img_0.png"},
                    {"image_path": "img_1.png"},
                    {"image_path": "img_2.png"},
                    {"image_path": "img_3.png"},
                ],
            },
        }

        replayed = build_recommendation_summary_from_report(report).to_dict()

        self.assertEqual(replayed, original)


if __name__ == "__main__":
    unittest.main()
