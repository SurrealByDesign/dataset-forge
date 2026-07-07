from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from dataset_forge.improvement_plan import IMPROVEMENT_PLAN_SCHEMA
from dataset_forge.improvement_preview import (
    EXECUTION_AVAILABILITY,
    IMPROVEMENT_PREVIEW_SCHEMA,
    ImprovementPreviewError,
    build_improvement_preview,
    render_improvement_preview_markdown,
    write_improvement_preview,
)
from dataset_forge.review_decisions import REVIEW_DECISIONS_SCHEMA


def _candidate(
    image_path: str,
    *,
    status: str = "PLANNING_ONLY",
    suggested_improvement: str = "Microtexture Normalization",
    decision: str | None = "CONFIRMED_ARTIFACT",
) -> dict[str, object]:
    return {
        "image_path": image_path,
        "filename": Path(image_path).name,
        "recommendation": "Priority Review",
        "recommendation_code": "PRIORITY_REVIEW",
        "primary_reason": "High-severity finding detected.",
        "finding_references": [
            {
                "category": "artifact.crystalline_faceting",
                "analyzer": "crystalline_faceting_analyzer/v1",
                "severity": "HIGH",
            }
        ],
        "review_decision": (
            {
                "image_path": image_path,
                "category": "artifact.crystalline_faceting",
                "analyzer": "crystalline_faceting_analyzer/v1",
                "decision": decision,
            }
            if decision is not None
            else None
        ),
        "suggested_improvement": suggested_improvement,
        "status": status,
        "planning_notes": "Improvement Candidate only.",
    }


def _write_plan(root: Path, *, candidates: list[dict[str, object]]) -> Path:
    root.mkdir(exist_ok=True)
    plan_path = root / "improvement_plan.json"
    plan_path.write_text(
        json.dumps({
            "schema": IMPROVEMENT_PLAN_SCHEMA,
            "tool_version": "0.test",
            "generated_at": "2026-07-05T00:00:00Z",
            "inputs": {"inspection_report": "inspection_report.json"},
            "summary": {
                "improvement_candidate_count": len(candidates),
                "deferred_improvement_candidate_count": 0,
                "suppressed_improvement_candidate_count": 0,
                "suggested_improvement_count": 1 if candidates else 0,
            },
            "improvement_candidates": candidates,
            "deferred_improvement_candidates": [],
            "suppressed_improvement_candidates": [],
            "suggested_improvements": [
                {"suggested_improvement": "Microtexture Normalization", "count": len(candidates)}
            ] if candidates else [],
        }),
        encoding="utf-8",
    )
    return plan_path


class ImprovementPreviewTests(unittest.TestCase):
    def test_builds_json_serializable_preview(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plan_path = _write_plan(
                Path(tmp),
                candidates=[_candidate("dataset/img.png")],
            )

            preview = build_improvement_preview(
                plan_path,
                generated_at="2026-07-05T00:00:00Z",
            )

        self.assertEqual(preview["schema"], IMPROVEMENT_PREVIEW_SCHEMA)
        self.assertEqual(preview["summary"]["execution_availability"], EXECUTION_AVAILABILITY)
        self.assertEqual(preview["preview_entries"][0]["execution_availability"], "Not Implemented")
        self.assertEqual(json.loads(json.dumps(preview)), preview)

    def test_writes_json_and_markdown_without_modifying_inputs_or_images(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_path = _write_plan(root, candidates=[_candidate("dataset/img.png")])
            image = root / "dataset" / "img.png"
            image.parent.mkdir()
            image.write_text("not an image", encoding="utf-8")
            image_before = image.read_text(encoding="utf-8")
            plan_before = plan_path.read_text(encoding="utf-8")

            json_path, markdown_path = write_improvement_preview(plan_path)

            self.assertEqual(json_path.name, "improvement_preview.json")
            self.assertEqual(markdown_path.name, "improvement_preview.md")
            self.assertEqual(image.read_text(encoding="utf-8"), image_before)
            self.assertEqual(plan_path.read_text(encoding="utf-8"), plan_before)
            self.assertEqual(
                json.loads(json_path.read_text(encoding="utf-8"))["schema"],
                IMPROVEMENT_PREVIEW_SCHEMA,
            )

    def test_optional_sidecars_are_validated_and_summarized(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_path = _write_plan(root, candidates=[_candidate("dataset/img.png")])
            (root / "review_decisions.json").write_text(
                json.dumps({
                    "schema": REVIEW_DECISIONS_SCHEMA,
                    "decisions": [
                        {
                            "image_path": "dataset/img.png",
                            "category": "artifact.crystalline_faceting",
                            "analyzer": "crystalline_faceting_analyzer/v1",
                            "decision": "CONFIRMED_ARTIFACT",
                        }
                    ],
                }),
                encoding="utf-8",
            )
            (root / "comparison_summary.json").write_text(
                json.dumps({
                    "schema": "dataset-forge/comparison-summary/v1",
                }),
                encoding="utf-8",
            )

            preview = build_improvement_preview(
                plan_path,
                generated_at="2026-07-05T00:00:00Z",
            )

        self.assertEqual(preview["inputs"]["review_decision_count"], 1)
        self.assertTrue(preview["inputs"]["comparison_summary_available"])

    def test_wrong_plan_schema_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "improvement_plan.json"
            path.write_text(json.dumps({"schema": "wrong"}), encoding="utf-8")

            with self.assertRaisesRegex(ImprovementPreviewError, "Unsupported improvement plan schema"):
                build_improvement_preview(path)

    def test_deterministic_ordering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plan_path = _write_plan(
                Path(tmp),
                candidates=[
                    _candidate("dataset/b.png", suggested_improvement="Speck Reduction"),
                    _candidate("dataset/a.png", suggested_improvement="Microtexture Normalization"),
                ],
            )

            preview = build_improvement_preview(
                plan_path,
                generated_at="2026-07-05T00:00:00Z",
            )

        self.assertEqual(
            [entry["filename"] for entry in preview["preview_entries"]],
            ["a.png", "b.png"],
        )

    def test_markdown_contains_traceability_and_no_execution_language(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plan_path = _write_plan(Path(tmp), candidates=[_candidate("dataset/img.png")])
            preview = build_improvement_preview(
                plan_path,
                generated_at="2026-07-05T00:00:00Z",
            )

            markdown = render_improvement_preview_markdown(preview)

        self.assertIn("# Improvement Preview", markdown)
        self.assertIn("Suggested Improvement", markdown)
        self.assertIn("Triggering findings", markdown)
        self.assertIn("Execution availability: Not Implemented", markdown)
        self.assertIn("Expected outcome", markdown)
        self.assertNotIn("Cleanup Candidate", markdown)
        self.assertNotIn("Repair Candidate", markdown)
