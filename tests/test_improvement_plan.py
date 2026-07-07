from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from dataset_forge.improvement_plan import (
    IMPROVEMENT_PLAN_SCHEMA,
    ImprovementPlanError,
    build_improvement_plan,
    render_improvement_plan_markdown,
    write_improvement_plan,
)
from dataset_forge.review_decisions import REVIEW_DECISIONS_SCHEMA


def _finding(
    image_path: str,
    *,
    category: str = "artifact.crystalline_faceting",
    analyzer: str = "crystalline_faceting_analyzer/v1",
    severity: str = "HIGH",
) -> dict[str, object]:
    return {
        "image_path": image_path,
        "analyzer": analyzer,
        "category": category,
        "severity": severity,
        "confidence": 0.4,
        "false_positive_rate": 0.2,
        "benchmark_version": "uncalibrated",
        "evidence": {"calibrated": False},
        "explanation": "test finding",
        "recommendation": "review",
    }


def _recommendation(
    image_path: str,
    recommendation: str = "PRIORITY_REVIEW",
    *,
    category: str = "artifact.crystalline_faceting",
    analyzer: str = "crystalline_faceting_analyzer/v1",
    severity: str = "HIGH",
) -> dict[str, object]:
    labels = {
        "READY_FOR_TRAINING": "Ready for Training",
        "NEEDS_REVIEW": "Needs Review",
        "PRIORITY_REVIEW": "Priority Review",
    }
    return {
        "image_path": image_path,
        "recommendation": recommendation,
        "display_label": labels[recommendation],
        "primary_reason": "High-severity finding detected.",
        "reason_codes": ["finding.high_severity"],
        "finding_refs": [
            {
                "category": category,
                "analyzer": analyzer,
                "severity": severity,
            }
        ],
        "guidance": "review",
        "confidence_note": "advisory",
    }


def _decision(
    image_path: str,
    decision: str,
    *,
    category: str | None = "artifact.crystalline_faceting",
    analyzer: str | None = "crystalline_faceting_analyzer/v1",
) -> dict[str, object]:
    payload: dict[str, object] = {
        "image_path": image_path,
        "decision": decision,
    }
    if category is not None:
        payload["category"] = category
    if analyzer is not None:
        payload["analyzer"] = analyzer
    return payload


def _write_output(
    root: Path,
    *,
    recommendations: list[dict[str, object]],
    findings: list[dict[str, object]] | None = None,
    decisions: list[dict[str, object]] | None = None,
) -> Path:
    root.mkdir()
    findings = findings if findings is not None else [
        _finding(str(item["image_path"])) for item in recommendations
        if item["recommendation"] != "READY_FOR_TRAINING"
    ]
    (root / "inspection_report.json").write_text(
        json.dumps({
            "schema": "dataset-forge/inspection/v1",
            "dataset_path": str(root / "dataset"),
            "tool_version": "0.test",
            "findings": findings,
            "summary": {"total_findings": len(findings)},
        }),
        encoding="utf-8",
    )
    counts = {
        "image_count": len(recommendations),
        "ready_for_training_count": sum(
            1 for item in recommendations
            if item["recommendation"] == "READY_FOR_TRAINING"
        ),
        "needs_review_count": sum(
            1 for item in recommendations
            if item["recommendation"] == "NEEDS_REVIEW"
        ),
        "priority_review_count": sum(
            1 for item in recommendations
            if item["recommendation"] == "PRIORITY_REVIEW"
        ),
        "analyzer_error_count": 0,
    }
    (root / "recommendation_summary.json").write_text(
        json.dumps({
            "schema": "dataset-forge/recommendation-summary/v1",
            "source_report_schema": "dataset-forge/inspection/v1",
            "summary": counts,
            "recommendations": recommendations,
        }),
        encoding="utf-8",
    )
    if decisions is not None:
        (root / "review_decisions.json").write_text(
            json.dumps({
                "schema": REVIEW_DECISIONS_SCHEMA,
                "decisions": decisions,
            }),
            encoding="utf-8",
        )
    return root


class ImprovementPlanTests(unittest.TestCase):
    def test_builds_json_serializable_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = _write_output(
                Path(tmp) / "inspect_output",
                recommendations=[_recommendation("dataset/img.png")],
            )

            plan = build_improvement_plan(output, generated_at="2026-07-05T00:00:00Z")

        self.assertEqual(plan["schema"], IMPROVEMENT_PLAN_SCHEMA)
        self.assertEqual(plan["summary"]["improvement_candidate_count"], 1)
        self.assertEqual(
            plan["improvement_candidates"][0]["suggested_improvement"],
            "Microtexture Normalization",
        )
        self.assertEqual(json.loads(json.dumps(plan)), plan)

    def test_writes_json_and_markdown_only_to_output_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inspect_output = _write_output(
                root / "inspect_output",
                recommendations=[_recommendation("dataset/img.png")],
            )
            image_path = root / "dataset" / "img.png"
            image_path.parent.mkdir()
            image_path.write_text("not an image", encoding="utf-8")
            before = image_path.read_text(encoding="utf-8")
            inspection_before = (inspect_output / "inspection_report.json").read_text(encoding="utf-8")
            recommendation_before = (inspect_output / "recommendation_summary.json").read_text(encoding="utf-8")

            json_path, markdown_path = write_improvement_plan(inspect_output)

            self.assertEqual(json_path.name, "improvement_plan.json")
            self.assertEqual(markdown_path.name, "improvement_plan.md")
            self.assertEqual(image_path.read_text(encoding="utf-8"), before)
            self.assertEqual(
                (inspect_output / "inspection_report.json").read_text(encoding="utf-8"),
                inspection_before,
            )
            self.assertEqual(
                (inspect_output / "recommendation_summary.json").read_text(encoding="utf-8"),
                recommendation_before,
            )
            self.assertEqual(
                json.loads(json_path.read_text(encoding="utf-8"))["schema"],
                IMPROVEMENT_PLAN_SCHEMA,
            )

    def test_missing_sidecars_fail_clearly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "inspect_output"
            output.mkdir()

            with self.assertRaisesRegex(ImprovementPlanError, "Missing inspection report"):
                build_improvement_plan(output)

    def test_ready_for_training_does_not_create_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = _write_output(
                Path(tmp) / "inspect_output",
                recommendations=[
                    _recommendation("dataset/img.png", "READY_FOR_TRAINING"),
                ],
                findings=[],
            )

            plan = build_improvement_plan(output, generated_at="2026-07-05T00:00:00Z")

        self.assertEqual(plan["summary"]["improvement_candidate_count"], 0)

    def test_confirmed_artifact_is_eligible_for_planning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = _write_output(
                Path(tmp) / "inspect_output",
                recommendations=[_recommendation("dataset/img.png")],
                decisions=[_decision("dataset/img.png", "CONFIRMED_ARTIFACT")],
            )

            plan = build_improvement_plan(output, generated_at="2026-07-05T00:00:00Z")

        self.assertEqual(plan["summary"]["improvement_candidate_count"], 1)
        self.assertEqual(
            plan["improvement_candidates"][0]["review_decision"]["decision"],
            "CONFIRMED_ARTIFACT",
        )

    def test_false_positive_suppresses_planning(self) -> None:
        plan = self._plan_for_decision("FALSE_POSITIVE")

        self.assertEqual(plan["summary"]["improvement_candidate_count"], 0)
        self.assertEqual(plan["summary"]["suppressed_improvement_candidate_count"], 1)

    def test_acceptable_style_suppresses_planning(self) -> None:
        plan = self._plan_for_decision("ACCEPTABLE_STYLE")

        self.assertEqual(plan["summary"]["improvement_candidate_count"], 0)
        self.assertEqual(plan["summary"]["suppressed_improvement_candidate_count"], 1)

    def test_ignore_suppresses_planning(self) -> None:
        plan = self._plan_for_decision("IGNORE")

        self.assertEqual(plan["summary"]["improvement_candidate_count"], 0)
        self.assertEqual(plan["summary"]["suppressed_improvement_candidate_count"], 1)

    def test_needs_review_defers_planning(self) -> None:
        plan = self._plan_for_decision("NEEDS_REVIEW")

        self.assertEqual(plan["summary"]["improvement_candidate_count"], 0)
        self.assertEqual(plan["summary"]["deferred_improvement_candidate_count"], 1)

    def test_locked_image_suppresses_planning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = _write_output(
                Path(tmp) / "inspect_output",
                recommendations=[_recommendation("dataset/img.png")],
                decisions=[
                    _decision(
                        "dataset/img.png",
                        "LOCKED",
                        category=None,
                        analyzer=None,
                    ),
                ],
            )

            plan = build_improvement_plan(output, generated_at="2026-07-05T00:00:00Z")

        self.assertEqual(plan["summary"]["improvement_candidate_count"], 0)
        self.assertEqual(plan["summary"]["suppressed_improvement_candidate_count"], 1)
        self.assertIn("locked", plan["suppressed_improvement_candidates"][0]["planning_notes"].lower())

    def test_deterministic_ordering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = _write_output(
                Path(tmp) / "inspect_output",
                recommendations=[
                    _recommendation("dataset/b.png", "NEEDS_REVIEW"),
                    _recommendation("dataset/a.png", "PRIORITY_REVIEW"),
                ],
            )

            plan = build_improvement_plan(output, generated_at="2026-07-05T00:00:00Z")

        self.assertEqual(
            [item["filename"] for item in plan["improvement_candidates"]],
            ["a.png", "b.png"],
        )

    def test_markdown_uses_improvement_language(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = _write_output(
                Path(tmp) / "inspect_output",
                recommendations=[_recommendation("dataset/img.png")],
            )
            plan = build_improvement_plan(output, generated_at="2026-07-05T00:00:00Z")

            markdown = render_improvement_plan_markdown(plan)

        self.assertIn("# Improvement Plan", markdown)
        self.assertIn("## Improvement Candidates", markdown)
        self.assertIn("Suggested Improvement", markdown)
        self.assertIn("Human Approval Required", markdown)
        for forbidden in ("Cleanup Candidate", "Repair Candidate", "Bad Image"):
            self.assertNotIn(forbidden, markdown)

    def _plan_for_decision(self, decision: str) -> dict[str, object]:
        with tempfile.TemporaryDirectory() as tmp:
            output = _write_output(
                Path(tmp) / "inspect_output",
                recommendations=[_recommendation("dataset/img.png")],
                decisions=[_decision("dataset/img.png", decision)],
            )
            return build_improvement_plan(output, generated_at="2026-07-05T00:00:00Z")
