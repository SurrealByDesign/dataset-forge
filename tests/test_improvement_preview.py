from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from dataset_forge.improvement_preview import (
    IMPROVEMENT_PREVIEW_SCHEMA,
    OPERATION_MANUAL_CAPTION,
    OPERATION_NO_ACTION,
    OPERATION_REDUCE_HALO,
    OPERATION_REMOVE_DUPLICATE,
    PROVIDER_LOCAL_CLASSICAL,
    PROVIDER_MANUAL,
    PROVIDER_UNKNOWN,
    STATUS_NOT_AVAILABLE,
    STATUS_READY,
    STATUS_WAITING_FOR_PROVIDER,
    ImprovementPreviewError,
    build_improvement_preview,
    provider_descriptors,
    render_improvement_preview_markdown,
    write_improvement_preview,
)
from dataset_forge.review_decisions import REVIEW_DECISIONS_SCHEMA
from dataset_forge.review_desk import build_review_data


def _recommendation(
    image_path: str,
    *,
    category: str = "artifact.oversharpening_halo",
    analyzer: str = "oversharpening_halo_analyzer/v1",
    severity: str = "MEDIUM",
    confidence: float = 0.61,
    recommendation: str = "NEEDS_REVIEW",
) -> dict[str, object]:
    labels = {
        "READY_FOR_TRAINING": "No Findings Emitted",
        "NEEDS_REVIEW": "Needs Review",
        "PRIORITY_REVIEW": "Priority Review",
    }
    findings = [] if recommendation == "READY_FOR_TRAINING" else [
        {
            "image_path": image_path,
            "analyzer": analyzer,
            "category": category,
            "severity": severity,
            "confidence": confidence,
            "evidence": {"fixture": True},
            "explanation": "fixture finding",
            "recommendation": "review",
        }
    ]
    return {
        "image_path": image_path,
        "recommendation": recommendation,
        "display_label": labels[recommendation],
        "primary_reason": "Fixture evidence.",
        "reason_codes": ["fixture"],
        "finding_refs": [
            {
                "category": category,
                "analyzer": analyzer,
                "severity": severity,
            }
            for _finding in findings
        ],
        "findings": findings,
        "guidance": "review",
        "confidence_note": "advisory",
    }


def _decision(
    image_path: str,
    decision: str,
) -> dict[str, object]:
    return {
        "image_path": image_path,
        "decision": decision,
        "workflow_state": "REVIEWED",
    }


def _write_output(
    root: Path,
    *,
    recommendations: list[dict[str, object]],
    decisions: list[dict[str, object]] | None = None,
) -> Path:
    root.mkdir()
    findings = [
        finding
        for recommendation in recommendations
        for finding in recommendation.get("findings", [])
        if isinstance(finding, dict)
    ]
    (root / "inspection_report.json").write_text(
        json.dumps({
            "schema": "dataset-forge/inspection/v1",
            "dataset_path": str(root / "dataset"),
            "tool_version": "fixture",
            "findings": findings,
            "summary": {"total_findings": len(findings)},
        }),
        encoding="utf-8",
    )
    (root / "recommendation_summary.json").write_text(
        json.dumps({
            "schema": "dataset-forge/recommendation-summary/v1",
            "source_report_schema": "dataset-forge/inspection/v1",
            "summary": {
                "image_count": len(recommendations),
                "priority_review_count": sum(
                    1 for item in recommendations
                    if item["recommendation"] == "PRIORITY_REVIEW"
                ),
                "needs_review_count": sum(
                    1 for item in recommendations
                    if item["recommendation"] == "NEEDS_REVIEW"
                ),
                "no_findings_emitted_count": sum(
                    1 for item in recommendations
                    if item["recommendation"] == "READY_FOR_TRAINING"
                ),
            },
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


class ImprovementPreviewTests(unittest.TestCase):
    def test_builds_schema_v1_sidecar_from_inspect_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = _write_output(
                Path(tmp) / "inspect_output",
                recommendations=[_recommendation("dataset/img.png")],
                decisions=[_decision("dataset/img.png", "IMPROVEMENT_CANDIDATE")],
            )

            preview = build_improvement_preview(output)
            self.assertTrue(preview["summary"]["provider_implementations_available"])

        self.assertEqual(preview["schema"], IMPROVEMENT_PREVIEW_SCHEMA)
        self.assertTrue(preview["deterministic"])
        self.assertEqual(preview["summary"]["record_count"], 1)
        record = preview["preview_records"][0]
        self.assertEqual(record["image"]["path"], "dataset/img.png")
        self.assertEqual(record["recommended_operation"], OPERATION_REDUCE_HALO)
        self.assertEqual(record["required_provider_type"], PROVIDER_LOCAL_CLASSICAL)
        self.assertEqual(record["preview_status"], STATUS_WAITING_FOR_PROVIDER)
        self.assertEqual(record["approval_state"], "APPROVED")
        self.assertEqual(json.loads(json.dumps(preview)), preview)

    def test_writes_preview_without_modifying_inputs_or_images(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = _write_output(
                root / "inspect_output",
                recommendations=[_recommendation("dataset/img.png")],
            )
            image = root / "dataset" / "img.png"
            image.parent.mkdir()
            image.write_text("source image placeholder", encoding="utf-8")
            before_image = image.read_text(encoding="utf-8")
            before_report = (output / "inspection_report.json").read_text(encoding="utf-8")
            before_summary = (output / "recommendation_summary.json").read_text(encoding="utf-8")

            json_path, markdown_path = write_improvement_preview(output)

            self.assertEqual(json_path.name, "improvement_preview.json")
            self.assertEqual(markdown_path.name, "improvement_preview.md")
            self.assertEqual(image.read_text(encoding="utf-8"), before_image)
            self.assertEqual((output / "inspection_report.json").read_text(encoding="utf-8"), before_report)
            self.assertEqual((output / "recommendation_summary.json").read_text(encoding="utf-8"), before_summary)
            self.assertEqual(
                json.loads(json_path.read_text(encoding="utf-8"))["schema"],
                IMPROVEMENT_PREVIEW_SCHEMA,
            )

    def test_output_is_deterministic_for_same_sidecars(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = _write_output(
                Path(tmp) / "inspect_output",
                recommendations=[
                    _recommendation("dataset/b.png", category="caption.missing", analyzer="caption_metadata_analyzer/v1"),
                    _recommendation("dataset/a.png", category="dataset.duplicate.exact", analyzer="duplicate_detection_analyzer/v1"),
                ],
                decisions=[
                    _decision("dataset/a.png", "REMOVAL_CANDIDATE"),
                    _decision("dataset/b.png", "IMPROVEMENT_CANDIDATE"),
                ],
            )

            first = build_improvement_preview(output)
            second = build_improvement_preview(output)

        self.assertEqual(first, second)
        self.assertEqual(
            [record["image"]["path"] for record in first["preview_records"]],
            ["dataset/a.png", "dataset/b.png"],
        )

    def test_operation_selection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = _write_output(
                Path(tmp) / "inspect_output",
                recommendations=[
                    _recommendation("dataset/caption.png", category="caption.short", analyzer="caption_metadata_analyzer/v1"),
                    _recommendation("dataset/duplicate.png", category="duplicate.perceptual", analyzer="perceptual_duplicate_analyzer/v1"),
                    _recommendation("dataset/clean.png", recommendation="READY_FOR_TRAINING"),
                ],
            )

            preview = build_improvement_preview(output)

        by_path = {
            record["image"]["path"]: record
            for record in preview["preview_records"]
        }
        self.assertEqual(by_path["dataset/caption.png"]["recommended_operation"], OPERATION_MANUAL_CAPTION)
        self.assertEqual(by_path["dataset/caption.png"]["required_provider_type"], PROVIDER_MANUAL)
        self.assertEqual(by_path["dataset/caption.png"]["preview_status"], STATUS_READY)
        self.assertEqual(by_path["dataset/duplicate.png"]["recommended_operation"], OPERATION_REMOVE_DUPLICATE)
        self.assertEqual(by_path["dataset/clean.png"]["recommended_operation"], OPERATION_NO_ACTION)
        self.assertEqual(by_path["dataset/clean.png"]["preview_status"], STATUS_NOT_AVAILABLE)

    def test_provider_descriptors_are_capabilities_only(self) -> None:
        descriptors = [descriptor.to_dict() for descriptor in provider_descriptors()]

        self.assertEqual(
            [descriptor["provider_type"] for descriptor in descriptors],
            ["LOCAL_CLASSICAL", "COMFYUI", "KREA", "MANUAL", "UNKNOWN"],
        )
        by_type = {descriptor["provider_type"]: descriptor for descriptor in descriptors}
        self.assertEqual(by_type["LOCAL_CLASSICAL"]["implementation_status"], "local_preview_available")
        self.assertTrue(
            all(
                descriptor["implementation_status"] == "not_implemented"
                for descriptor in descriptors
                if descriptor["provider_type"] != "LOCAL_CLASSICAL"
            )
        )
        self.assertTrue(all(not descriptor["network_access"] for descriptor in descriptors))
        self.assertTrue(all(not descriptor["modifies_source_images"] for descriptor in descriptors))
        self.assertTrue(by_type["LOCAL_CLASSICAL"]["generates_preview_images"])
        self.assertTrue(by_type["LOCAL_CLASSICAL"]["processes_images"])
        self.assertTrue(
            all(
                not descriptor["generates_preview_images"]
                for descriptor in descriptors
                if descriptor["provider_type"] != "LOCAL_CLASSICAL"
            )
        )
        self.assertTrue(all(set(descriptor) == {
            "provider_type",
            "display_name",
            "capabilities",
            "implementation_status",
            "network_access",
            "processes_images",
            "modifies_source_images",
            "generates_preview_images",
        } for descriptor in descriptors))

    def test_v17_provider_contract_does_not_change_improvement_preview_v1_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = _write_output(
                Path(tmp) / "inspect_output",
                recommendations=[_recommendation("dataset/img.png")],
            )

            preview = build_improvement_preview(output)

        record = preview["preview_records"][0]
        self.assertNotIn("required_capabilities", record)
        self.assertNotIn("provider_compatibility", record)
        self.assertNotIn("provider_contract", preview)
        self.assertEqual(preview["schema"], IMPROVEMENT_PREVIEW_SCHEMA)

    def test_wrong_sidecar_schema_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "inspect_output"
            output.mkdir()
            (output / "inspection_report.json").write_text(
                json.dumps({"schema": "wrong"}),
                encoding="utf-8",
            )
            (output / "recommendation_summary.json").write_text(
                json.dumps({"schema": "dataset-forge/recommendation-summary/v1"}),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ImprovementPreviewError, "Unsupported inspection report schema"):
                build_improvement_preview(output)

    def test_review_desk_exposes_preview_sidecar_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = _write_output(
                Path(tmp) / "inspect_output",
                recommendations=[_recommendation("dataset/img.png")],
            )
            write_improvement_preview(output)

            payload = build_review_data(output)

        self.assertTrue(payload["improvement_preview"]["available"])
        self.assertEqual(payload["improvement_preview"]["schema"], IMPROVEMENT_PREVIEW_SCHEMA)
        self.assertEqual(payload["improvement_preview"]["records"][0]["recommended_operation"], OPERATION_REDUCE_HALO)

    def test_markdown_contains_scope_boundaries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = _write_output(
                Path(tmp) / "inspect_output",
                recommendations=[_recommendation("dataset/img.png")],
            )
            preview = build_improvement_preview(output)

            markdown = render_improvement_preview_markdown(preview)

        self.assertIn("# Improvement Preview", markdown)
        self.assertIn("Planning infrastructure for preview candidate review", markdown)
        self.assertIn("Recommended operation", markdown)
        self.assertIn("Required provider type", markdown)
        self.assertIn("No provider implementation was called", markdown)
        self.assertNotIn("Prompt:", markdown)
        self.assertNotIn("Image editing", markdown)


if __name__ == "__main__":
    unittest.main()
