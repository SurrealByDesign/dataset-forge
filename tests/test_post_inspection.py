"""Tests for additive post-inspection aggregation and review queue models."""

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
from dataset_forge.post_inspection import (
    DATASET_SUMMARY_SCHEMA,
    REVIEW_QUEUE_SCHEMA,
    build_aggregation,
    build_dataset_summary,
    build_post_inspection_sections,
    build_review_queue,
)


def _ctx(n: int = 4) -> DatasetContext:
    return DatasetContext(
        schema_version=CONTEXT_SCHEMA_VERSION,
        analyzer_versions={"texture_analyzer": "v1"},
        image_paths=tuple(Path(f"img_{i}.png") for i in range(n)),
        image_count=n,
        error_count=0,
        resolution_stats=ResolutionStats.empty(),
        aspect_ratio_stats=AspectRatioStats.empty(),
        texture_distributions=TextureDistributions.empty(),
        frequency_distributions=FrequencyDistributions.empty(),
        duplicate_hashes=frozenset(),
        duplicate_groups=(),
    )


def _finding(
    image: str,
    *,
    category: str = "texture.high_microtexture",
    analyzer: str = "texture_analyzer/v1",
    severity: Severity = Severity.LOW,
    calibrated: bool = False,
) -> Finding:
    return Finding(
        image_path=Path(image),
        analyzer=analyzer,
        category=category,
        severity=severity,
        confidence=0.4,
        false_positive_rate=0.2,
        benchmark_version="uncalibrated",
        evidence={"calibrated": calibrated},
        explanation="test",
        recommendation="review",
    )


class TestPostInspectionAggregation(unittest.TestCase):
    def test_aggregation_is_deterministic_and_groups_by_image(self):
        findings = [
            _finding("img_1.png", severity=Severity.MEDIUM),
            _finding("img_0.png", category="artifact.oversharpening_halo"),
        ]

        aggregation = build_aggregation(_ctx(), findings)

        self.assertEqual(tuple(aggregation.findings_by_image), (
            "img_0.png",
            "img_1.png",
            "img_2.png",
            "img_3.png",
        ))
        self.assertEqual(len(aggregation.findings_by_image["img_0.png"]), 1)

    def test_summary_counts_are_correct(self):
        findings = [
            _finding("img_0.png", severity=Severity.LOW),
            _finding(
                "img_1.png",
                category="artifact.oversharpening_halo",
                analyzer="oversharpening_halo_analyzer/v1",
                severity=Severity.MEDIUM,
                calibrated=True,
            ),
            _finding(
                "img_2.png",
                category="texture.error",
                severity=Severity.LOW,
            ),
        ]

        aggregation = build_aggregation(_ctx(), findings)
        summary = build_dataset_summary(_ctx(), aggregation)

        self.assertEqual(summary.schema, DATASET_SUMMARY_SCHEMA)
        self.assertEqual(summary.image_count, 4)
        self.assertEqual(summary.images_with_findings, 3)
        self.assertEqual(summary.images_without_findings, 1)
        self.assertEqual(summary.findings_by_category["texture.high_microtexture"], 1)
        self.assertEqual(summary.findings_by_severity["LOW"], 2)
        self.assertEqual(summary.findings_by_severity["MEDIUM"], 1)
        self.assertEqual(summary.analyzer_error_count, 1)
        self.assertEqual(summary.calibrated_finding_count, 1)
        self.assertEqual(summary.uncalibrated_finding_count, 2)
        self.assertEqual(summary.dominant_artifact_families[0], "artifact.oversharpening_halo")

    def test_counts_images_with_multiple_finding_families(self):
        findings = [
            _finding("img_0.png", category="texture.high_microtexture"),
            _finding(
                "img_0.png",
                category="artifact.high_frequency_isolated",
                analyzer="high_frequency_isolated_artifact_analyzer/v1",
            ),
        ]

        aggregation = build_aggregation(_ctx(), findings)

        self.assertEqual(aggregation.images_with_multiple_finding_families, 1)


class TestReviewQueue(unittest.TestCase):
    def _items_by_name(self, findings: list[Finding]):
        aggregation = build_aggregation(_ctx(), findings)
        queue = build_review_queue(_ctx(), aggregation)
        return {
            Path(item.image_path).name: item
            for item in queue.items
        }

    def test_no_findings_maps_to_no_attention_needed(self):
        item = self._items_by_name([])["img_0.png"]

        self.assertEqual(item.outcome, "no_attention_needed")
        self.assertEqual(item.priority, "none")

    def test_one_low_finding_maps_to_review_recommended_low(self):
        item = self._items_by_name([
            _finding("img_0.png", severity=Severity.LOW)
        ])["img_0.png"]

        self.assertEqual(item.outcome, "review_recommended")
        self.assertEqual(item.priority, "low")

    def test_one_medium_finding_maps_to_review_recommended_medium(self):
        item = self._items_by_name([
            _finding("img_0.png", severity=Severity.MEDIUM)
        ])["img_0.png"]

        self.assertEqual(item.outcome, "review_recommended")
        self.assertEqual(item.priority, "medium")

    def test_multiple_families_map_to_priority_review(self):
        item = self._items_by_name([
            _finding("img_0.png", category="texture.high_microtexture"),
            _finding(
                "img_0.png",
                category="artifact.crystalline_faceting",
                analyzer="crystalline_faceting_analyzer/v1",
            ),
        ])["img_0.png"]

        self.assertEqual(item.outcome, "priority_review")
        self.assertEqual(item.priority, "high")

    def test_analyzer_error_maps_to_priority_review(self):
        item = self._items_by_name([
            _finding("img_0.png", category="texture.error")
        ])["img_0.png"]

        self.assertEqual(item.outcome, "priority_review")
        self.assertTrue(item.has_analyzer_error)

    def test_review_queue_json_serializable(self):
        summary, queue = build_post_inspection_sections([
            _finding("img_0.png", severity=Severity.MEDIUM)
        ], _ctx())

        payload = {
            "dataset_summary": summary.to_dict(),
            "review_queue": queue.to_dict(),
        }

        self.assertEqual(queue.schema, REVIEW_QUEUE_SCHEMA)
        self.assertIn("dataset_summary", json.loads(json.dumps(payload)))

    def test_review_queue_does_not_use_reject_regenerate_or_repair_outcomes(self):
        _, queue = build_post_inspection_sections([
            _finding("img_0.png", severity=Severity.CRITICAL),
            _finding("img_1.png", category="texture.error"),
        ], _ctx())

        outcomes = {item.outcome for item in queue.items}
        self.assertLessEqual(
            outcomes,
            {"no_attention_needed", "review_recommended", "priority_review"},
        )


if __name__ == "__main__":
    unittest.main()
