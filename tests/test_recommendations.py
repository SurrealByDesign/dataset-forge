from __future__ import annotations

import json
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
)


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
    def test_no_findings_maps_to_ready_for_training(self) -> None:
        item = _recommendations_by_name([])["img_0.png"]

        self.assertEqual(item["recommendation"], READY_FOR_TRAINING)
        self.assertEqual(item["reason_codes"], ["no_findings"])
        self.assertIn("no current evidence", item["guidance"])

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

    def test_priority_text_does_not_say_exclude_delete_or_remove(self) -> None:
        item = _recommendations_by_name([
            _finding("img_0.png", severity=Severity.HIGH),
        ])["img_0.png"]
        text = json.dumps(item).lower()

        self.assertNotIn("exclude", text)
        self.assertNotIn("delete", text)
        self.assertNotIn("remove", text)

    def test_confidence_note_is_advisory_and_not_calibrated_claim(self) -> None:
        item = _recommendations_by_name([
            _finding("img_0.png", severity=Severity.MEDIUM),
        ])["img_0.png"]

        self.assertIn("advisory", item["confidence_note"])
        self.assertNotIn("validated", item["confidence_note"].lower())


if __name__ == "__main__":
    unittest.main()
