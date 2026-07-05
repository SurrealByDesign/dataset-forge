from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from dataset_forge.static_review_gallery import (
    render_static_review_gallery,
    write_static_review_gallery,
)


def _inspection_report(dataset: Path) -> dict:
    return {
        "schema": "dataset-forge/inspection/v1",
        "dataset_path": str(dataset),
        "findings": [],
    }


def _recommendation_summary(dataset: Path) -> dict:
    return {
        "schema": "dataset-forge/recommendation-summary/v1",
        "source_report_schema": "dataset-forge/inspection/v1",
        "summary": {
            "image_count": 3,
            "ready_for_training_count": 1,
            "needs_review_count": 1,
            "priority_review_count": 1,
            "analyzer_error_count": 0,
        },
        "recommendations": [
            {
                "image_path": str(dataset / "priority.png"),
                "recommendation": "PRIORITY_REVIEW",
                "display_label": "Priority Review",
                "primary_reason": "High-severity finding detected.",
                "reason_codes": ["finding.high_severity"],
                "finding_refs": [
                    {
                        "analyzer": "texture_analyzer/v1",
                        "category": "artifact.texture",
                        "severity": "HIGH",
                    }
                ],
                "guidance": "Review this image early before training.",
                "confidence_note": "Recommendations are advisory.",
            },
            {
                "image_path": str(dataset / "needs.png"),
                "recommendation": "NEEDS_REVIEW",
                "display_label": "Needs Review",
                "primary_reason": "Measurable finding detected.",
                "reason_codes": ["finding.present"],
                "finding_refs": [
                    {
                        "analyzer": "oversharpening_halo_analyzer/v1",
                        "category": "artifact.oversharpening_halo",
                        "severity": "MEDIUM",
                    }
                ],
                "guidance": "Inspect this image before training.",
                "confidence_note": "Recommendations are advisory.",
            },
            {
                "image_path": str(dataset / "ready.png"),
                "recommendation": "READY_FOR_TRAINING",
                "display_label": "Ready for Training",
                "primary_reason": "No findings were emitted for this image.",
                "reason_codes": ["no_findings"],
                "finding_refs": [],
                "guidance": "No current evidence requiring review.",
                "confidence_note": "Recommendations are advisory.",
            },
        ],
    }


class StaticReviewGalleryTests(unittest.TestCase):
    def test_writes_review_gallery_html(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inspection_path = root / "inspection_report.json"
            recommendation_path = root / "recommendation_summary.json"
            output_path = root / "review_gallery.html"
            inspection_path.write_text(
                json.dumps(_inspection_report(root)),
                encoding="utf-8",
            )
            recommendation_path.write_text(
                json.dumps(_recommendation_summary(root)),
                encoding="utf-8",
            )

            written = write_static_review_gallery(
                inspection_path,
                recommendation_path,
                output_path,
            )

            self.assertEqual(written, output_path)
            self.assertTrue(output_path.exists())

    def test_contains_review_sections_and_advisory_language(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            html = render_static_review_gallery(
                _inspection_report(Path(tmp)),
                _recommendation_summary(Path(tmp)),
            )

        self.assertIn("<h1>Dataset Forge Review Gallery</h1>", html)
        self.assertIn("<h2>Dataset Summary</h2>", html)
        self.assertIn("<h2>Priority Review</h2>", html)
        self.assertIn("<h2>Needs Review</h2>", html)
        self.assertIn(
            "Recommendations are based only on current deterministic findings.",
            html,
        )
        self.assertIn("Ready for Training means no current findings were emitted.", html)
        self.assertIn("Dataset Forge never modifies source images.", html)
        self.assertIn(
            "It does not guarantee the image is artifact-free.",
            html,
        )

    def test_ready_for_training_is_summarized_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            html = render_static_review_gallery(
                _inspection_report(Path(tmp)),
                _recommendation_summary(Path(tmp)),
            )

        self.assertIn("1 image emitted no current findings requiring review.", html)
        self.assertIn("priority.png", html)
        self.assertIn("needs.png", html)
        self.assertNotIn("ready.png", html)

    def test_cards_include_required_finding_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            html = render_static_review_gallery(
                _inspection_report(Path(tmp)),
                _recommendation_summary(Path(tmp)),
            )

        self.assertIn("High-severity finding detected.", html)
        self.assertIn("artifact.texture", html)
        self.assertIn("HIGH", html)
        self.assertIn("texture_analyzer/v1", html)
        self.assertIn("<strong>Finding categories:</strong>", html)
        self.assertIn("<strong>Finding count:</strong> 1", html)
        self.assertIn("<strong>Analyzer:</strong>", html)

    def test_contains_no_action_or_app_controls(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            html = render_static_review_gallery(
                _inspection_report(Path(tmp)),
                _recommendation_summary(Path(tmp)),
            )
        lowered = html.lower()

        for forbidden in ("delete", "remove", "exclude", "repair", "export"):
            self.assertNotIn(forbidden, lowered)
        self.assertNotIn("reject", lowered)
        self.assertNotIn("confidence", lowered)
        self.assertNotIn("%", lowered)
        for forbidden in ("<button", "checkbox", "<form", "<script"):
            self.assertNotIn(forbidden, lowered)
        for forbidden in ("react", "vue", "svelte", "cdn.", "http://", "https://"):
            self.assertNotIn(forbidden, lowered)

    def test_output_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = _inspection_report(Path(tmp))
            summary = _recommendation_summary(Path(tmp))

            first = render_static_review_gallery(report, summary)
            second = render_static_review_gallery(report, summary)

        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
