from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from dataset_forge.recommendation_contact_sheets import (
    MAX_TILES_PER_SHEET,
    render_recommendation_contact_sheet,
    write_recommendation_contact_sheets,
)


def _write_image(path: Path, value: int) -> None:
    Image.fromarray(np.full((48, 48, 3), value, dtype=np.uint8)).save(path)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


class RecommendationContactSheetTests(unittest.TestCase):
    def test_writes_priority_and_needs_review_sheets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, value in (
                ("priority.png", 220),
                ("needs.png", 160),
                ("ready.png", 120),
            ):
                _write_image(root / name, value)
            inspection_path = root / "inspection_report.json"
            recommendation_path = root / "recommendation_summary.json"
            inspection_path.write_text(json.dumps(_inspection_report(root)), encoding="utf-8")
            recommendation_path.write_text(json.dumps(_recommendation_summary(root)), encoding="utf-8")

            priority_path, needs_path = write_recommendation_contact_sheets(
                inspection_path,
                recommendation_path,
                root,
            )

            self.assertEqual(priority_path.name, "priority_review_contact_sheet.png")
            self.assertEqual(needs_path.name, "needs_review_contact_sheet.png")
            self.assertTrue(priority_path.exists())
            self.assertTrue(needs_path.exists())

    def test_ready_for_training_sheet_is_not_created(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inspection_path = root / "inspection_report.json"
            recommendation_path = root / "recommendation_summary.json"
            inspection_path.write_text(json.dumps(_inspection_report(root)), encoding="utf-8")
            recommendation_path.write_text(json.dumps(_recommendation_summary(root)), encoding="utf-8")

            write_recommendation_contact_sheets(inspection_path, recommendation_path, root)

            self.assertFalse((root / "ready_for_training_contact_sheet.png").exists())
            self.assertFalse((root / "all_review_contact_sheet.png").exists())

    def test_empty_groups_write_deterministic_empty_state_sheets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = _inspection_report(root)
            summary = _recommendation_summary(root)
            summary["recommendations"] = [
                item for item in summary["recommendations"]
                if item["recommendation"] == "READY_FOR_TRAINING"
            ]
            inspection_path = root / "inspection_report.json"
            recommendation_path = root / "recommendation_summary.json"
            inspection_path.write_text(json.dumps(report), encoding="utf-8")
            recommendation_path.write_text(json.dumps(summary), encoding="utf-8")

            first = write_recommendation_contact_sheets(
                inspection_path,
                recommendation_path,
                root,
            )
            first_hashes = [_sha256(path) for path in first]
            second = write_recommendation_contact_sheets(
                inspection_path,
                recommendation_path,
                root,
            )
            second_hashes = [_sha256(path) for path in second]

            self.assertEqual(first_hashes, second_hashes)

    def test_deterministic_output_ordering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_image(root / "priority.png", 220)
            image = render_recommendation_contact_sheet(
                _inspection_report(root),
                [
                    _recommendation_summary(root)["recommendations"][0],
                ],
                title="Priority Review",
            )
            output_a = root / "a.png"
            output_b = root / "b.png"
            image.save(output_a, "PNG")
            render_recommendation_contact_sheet(
                _inspection_report(root),
                [
                    _recommendation_summary(root)["recommendations"][0],
                ],
                title="Priority Review",
            ).save(output_b, "PNG")

            self.assertEqual(_sha256(output_a), _sha256(output_b))

    def test_source_images_are_not_modified(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "priority.png"
            _write_image(source, 220)
            inspection_path = root / "inspection_report.json"
            recommendation_path = root / "recommendation_summary.json"
            inspection_path.write_text(json.dumps(_inspection_report(root)), encoding="utf-8")
            recommendation_path.write_text(json.dumps(_recommendation_summary(root)), encoding="utf-8")
            before = _sha256(source)

            write_recommendation_contact_sheets(inspection_path, recommendation_path, root)

            self.assertEqual(_sha256(source), before)

    def test_max_tiles_per_sheet_is_documented_constant(self) -> None:
        self.assertEqual(MAX_TILES_PER_SHEET, 100)


if __name__ == "__main__":
    unittest.main()
