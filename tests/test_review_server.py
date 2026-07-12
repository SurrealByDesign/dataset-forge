from __future__ import annotations

import json
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import numpy as np
from PIL import Image

from dataset_forge.improvement_preview import IMPROVEMENT_PREVIEW_SCHEMA
from dataset_forge.preview_artifacts import import_manual_preview_candidate
from dataset_forge.review_decisions import REVIEW_DECISIONS_SCHEMA
from dataset_forge.review_desk import (
    REVIEW_DESK_DATA_SCHEMA,
    build_analyzer_coverage,
    build_dataset_intelligence,
    build_intelligence_analyzer_contribution,
    build_intelligence_evidence_summary,
    build_next_action,
    build_overview,
    build_review_payload,
    build_review_progress,
    build_top_categories,
)
from dataset_forge.review_server import (
    LOCAL_REVIEW_HOST,
    ReviewServerError,
    atomic_write_json,
    build_review_data,
    create_review_server,
    load_review_workspace,
    update_review_decision,
    update_preview_approval,
)


def _write_workspace(
    root: Path,
    *,
    include_needs_review: bool = False,
    include_manifest: bool = False,
    include_comparison: bool = False,
) -> tuple[Path, Path]:
    output = root / "inspect_output"
    output.mkdir()
    image = root / "priority.png"
    ready = root / "ready.png"
    needs = root / "needs.png"
    Image.fromarray(np.full((24, 24, 3), 128, dtype=np.uint8)).save(image)
    Image.fromarray(np.full((24, 24, 3), 64, dtype=np.uint8)).save(ready)
    if include_needs_review:
        Image.fromarray(np.full((24, 24, 3), 96, dtype=np.uint8)).save(needs)
    recommendations = [
        {
            "image_path": str(image),
            "recommendation": "PRIORITY_REVIEW",
            "display_label": "Priority Review",
            "primary_reason": "High-severity finding detected.",
            "reason_codes": ["finding.high_severity"],
            "finding_refs": [
                {
                    "analyzer": "texture_analyzer/v1",
                    "category": "artifact.texture",
                    "severity": "HIGH",
                },
                {
                    "analyzer": "oversharpening_halo_analyzer/v1",
                    "category": "artifact.oversharpening_halo",
                    "severity": "MEDIUM",
                },
            ],
            "guidance": "Review this image early before training.",
            "confidence_note": "Recommendations are advisory.",
        },
        {
            "image_path": str(ready),
            "recommendation": "READY_FOR_TRAINING",
            "display_label": "No Findings Emitted",
            "primary_reason": "No findings were emitted for this image.",
            "reason_codes": ["no_findings"],
            "finding_refs": [],
            "guidance": "No current evidence requiring review.",
            "confidence_note": "Recommendations are advisory.",
        },
    ]
    if include_needs_review:
        recommendations.append({
            "image_path": str(needs),
            "recommendation": "NEEDS_REVIEW",
            "display_label": "Needs Review",
            "primary_reason": "Medium-severity finding detected.",
            "reason_codes": ["finding.medium_severity"],
            "finding_refs": [
                {
                    "analyzer": "high_frequency_isolated_artifact_analyzer/v1",
                    "category": "artifact.high_frequency_isolated",
                    "severity": "MEDIUM",
                },
                {
                    "analyzer": "texture_analyzer/v1",
                    "category": "artifact.texture",
                    "severity": "LOW",
                },
            ],
            "guidance": "Review this image before training.",
            "confidence_note": "Recommendations are advisory.",
        })
    (output / "inspection_report.json").write_text(
        json.dumps({
            "schema": "dataset-forge/inspection/v1",
            "dataset_path": str(root),
            "findings": [],
        }),
        encoding="utf-8",
    )
    (output / "recommendation_summary.json").write_text(
        json.dumps({
            "schema": "dataset-forge/recommendation-summary/v1",
            "source_report_schema": "dataset-forge/inspection/v1",
            "summary": {
                "image_count": 3 if include_needs_review else 2,
                "ready_for_training_count": 1,
                "needs_review_count": 1 if include_needs_review else 0,
                "priority_review_count": 1,
                "analyzer_error_count": 0,
            },
            "analyzer_coverage": {
                "schema": "dataset-forge/analyzer-coverage/v1",
                "analyzers": [
                    {
                        "analyzer": "high_frequency_isolated_artifact_analyzer",
                        "version": "v1",
                        "finding_count": 1 if include_needs_review else 0,
                        "image_count": 1 if include_needs_review else 0,
                        "calibration_status": "uncalibrated",
                    },
                    {
                        "analyzer": "texture_analyzer",
                        "version": "v1",
                        "finding_count": 2 if include_needs_review else 1,
                        "image_count": 2 if include_needs_review else 1,
                        "calibration_status": "uncalibrated",
                    },
                ],
            },
            "recommendations": recommendations,
        }),
        encoding="utf-8",
    )
    if include_manifest:
        (output / "inspection_manifest.json").write_text(
            json.dumps({
                "schema": "dataset-forge/inspection-manifest/v1",
                "tool": {
                    "name": "dataset-forge",
                    "version": "1.0.0",
                },
                "inspection": {
                    "profile": {
                        "id": "default",
                        "display_name": "Default Inspection",
                        "version": "v1",
                        "description": "Default Dataset Forge inspection profile.",
                        "analyzer_policy_overrides": [],
                    },
                    "started_at": "2026-07-07T00:00:00Z",
                    "completed_at": "2026-07-07T00:00:01Z",
                    "deterministic": True,
                    "read_only": True,
                },
                "dataset": {
                    "path": str(root),
                    "recursive": True,
                    "limit": None,
                    "image_count": 3 if include_needs_review else 2,
                    "analyzed_count": 3 if include_needs_review else 2,
                    "error_count": 0,
                },
                "sidecars": {},
                "analyzers": [
                    {
                        "id": "high_frequency_isolated_artifact_analyzer",
                        "display_name": "High Frequency Isolated Artifact Analyzer",
                        "version": "v1",
                        "family": "Technical Quality",
                        "categories_emitted": ["artifact.high_frequency_isolated"],
                        "calibration_status": "advisory",
                        "execution": {"policy": "enabled", "executed": True},
                        "display": {"policy": "visible"},
                        "triage": {"policy": "included"},
                        "finding_count": 1 if include_needs_review else 0,
                        "image_count": 1 if include_needs_review else 0,
                    },
                    {
                        "id": "texture_analyzer",
                        "display_name": "Texture Analyzer",
                        "version": "v1",
                        "family": "Technical Quality",
                        "categories_emitted": ["artifact.texture"],
                        "calibration_status": "advisory",
                        "execution": {"policy": "enabled", "executed": True},
                        "display": {"policy": "visible"},
                        "triage": {"policy": "included"},
                        "finding_count": 2 if include_needs_review else 1,
                        "image_count": 2 if include_needs_review else 1,
                    },
                ],
                "disabled_analyzers": [],
                "compatibility": {
                    "inspection_report_schema": "dataset-forge/inspection/v1",
                    "recommendation_summary_schema": "dataset-forge/recommendation-summary/v1",
                    "manifest_contract_version": 1,
                },
            }),
            encoding="utf-8",
        )
    if include_comparison:
        (output / "comparison_summary.json").write_text(
            json.dumps({
                "schema": "dataset-forge/comparison-summary/v1",
                "inspection_compatibility": {"status": "compatible"},
            }),
            encoding="utf-8",
        )
    return output, image


def _write_review_decisions(output: Path, decisions: list[dict[str, object]]) -> None:
    (output / "review_decisions.json").write_text(
        json.dumps({
            "schema": REVIEW_DECISIONS_SCHEMA,
            "decisions": decisions,
        }),
        encoding="utf-8",
    )


def _write_improvement_preview(
    output: Path,
    image: Path,
    *,
    approval_state: str = "NOT_REQUESTED",
) -> None:
    record = {
        "image": {
            "path": str(image),
            "filename": image.name,
        },
        "review_decision": "UNDECIDED",
        "current_findings": [
            {
                "analyzer": "texture_analyzer/v1",
                "category": "artifact.texture",
                "severity": "HIGH",
                "confidence": 0.82,
            }
        ],
        "recommended_operation": "REPLACE_SOURCE",
        "operation_rationale": "Planning only; source replacement may be reviewed later.",
        "confidence": 0.82,
        "required_provider_type": "MANUAL",
        "preview_status": "READY",
        "approval_state": approval_state,
        "notes": "Planning only. No image data, generated outputs, provider calls, or execution.",
    }
    payload = {
        "schema": IMPROVEMENT_PREVIEW_SCHEMA,
        "tool_version": "1.5.0",
        "deterministic": True,
        "approval_states": ["NOT_REQUESTED", "APPROVED", "REJECTED"],
        "preview_statuses": ["NOT_AVAILABLE", "WAITING_FOR_PROVIDER", "READY", "REJECTED", "APPROVED"],
        "summary": {
            "record_count": 1,
            "approval_state_counts": {approval_state: 1},
            "generated_preview_image_count": 0,
            "execution_available": False,
            "provider_implementations_available": False,
        },
        "scope": {
            "read_only": True,
            "sidecar_only": True,
            "does_not_generate_images": True,
            "does_not_execute_improvements": True,
            "does_not_modify_images": True,
        },
        "preview_records": [record],
        "preview_entries": [record],
    }
    (output / "improvement_preview.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )


class ReviewServerDataTests(unittest.TestCase):
    def test_requires_inspection_and_recommendation_sidecars(self) -> None:
        with TemporaryDirectory() as tmp:
            with self.assertRaises(ReviewServerError):
                load_review_workspace(Path(tmp))

    def test_builds_image_centered_rows_for_all_triage_groups(self) -> None:
        with TemporaryDirectory() as tmp:
            output, _image = _write_workspace(Path(tmp))

            data = build_review_data(output)

        self.assertEqual(data["schema"], REVIEW_DESK_DATA_SCHEMA)
        self.assertEqual(data["summary"]["review_image_count"], 2)
        self.assertEqual(data["summary"]["pending_review_count"], 2)
        self.assertEqual(
            {row["triage_status"] for row in data["rows"]},
            {"Priority Review", "No Findings Emitted"},
        )
        priority = [row for row in data["rows"] if row["triage_status"] == "Priority Review"][0]
        self.assertEqual(priority["finding_count"], 2)
        self.assertIn("artifact.texture", priority["finding_categories"])
        self.assertIn("ready.png", json.dumps(data))

    def test_review_payload_contract_has_stable_top_level_shape(self) -> None:
        with TemporaryDirectory() as tmp:
            output, _image = _write_workspace(Path(tmp), include_needs_review=True)
            workspace = load_review_workspace(output)

            data = build_review_payload(workspace)

        self.assertEqual(
            set(data),
            {
                "schema",
                "review_decisions_schema",
                "dataset_path",
                "summary",
                "overview",
                "dataset_intelligence",
                "improvement_preview",
                "analyzer_coverage",
                "decision_values",
                "workflow_states",
                "scope",
                "images",
                "rows",
            },
        )
        self.assertIs(data["images"], data["rows"])
        self.assertEqual(data["schema"], REVIEW_DESK_DATA_SCHEMA)
        self.assertEqual(data["review_decisions_schema"], REVIEW_DECISIONS_SCHEMA)
        self.assertEqual(
            set(data["images"][0]),
            {
                "id",
                "image_path",
                "thumbnail_url",
                "filename",
                "triage_status",
                "recommendation",
                "primary_reason",
                "reason_codes",
                "finding_categories",
                "analyzers",
                "severities",
                "max_confidence",
                "finding_count",
                "finding_refs",
                "findings",
                "evidence_summary",
                "suggested_review_action",
                "confidence_note",
                "no_finding_semantics",
                "dossier_anchor",
                "decision",
                "workflow_state",
                "notes",
                "decision_history",
            },
        )

    def test_pure_review_builders_are_deterministic(self) -> None:
        with TemporaryDirectory() as tmp:
            output, _image = _write_workspace(Path(tmp), include_needs_review=True)
            data = build_review_data(output)
            workspace = load_review_workspace(output)

            images = data["images"]
            source_summary = {
                "image_count": 3,
                "priority_review_count": 1,
                "needs_review_count": 1,
                "ready_for_training_count": 1,
            }
            coverage = data["analyzer_coverage"]

            self.assertEqual(
                build_review_progress(images),
                {
                    "review_image_count": 3,
                    "reviewed_count": 0,
                    "pending_review_count": 3,
                    "completion_percent": 0.0,
                },
            )
            self.assertEqual(
                build_next_action(images)["target_filter"],
                {"triage_status": "Priority Review", "decision": "UNDECIDED"},
            )
            self.assertEqual(build_top_categories(images), data["overview"]["top_finding_categories"])
            self.assertEqual(
                build_analyzer_coverage(coverage),
                data["overview"]["analyzer_coverage_summary"],
            )
            self.assertEqual(
                build_overview(images, source_summary, coverage),
                data["overview"],
            )
            self.assertEqual(
                build_dataset_intelligence(
                    workspace,
                    images,
                    source_summary,
                    coverage,
                ),
                data["dataset_intelligence"],
            )

    def test_overview_counts_and_scope_are_computed_from_sidecars(self) -> None:
        with TemporaryDirectory() as tmp:
            output, image = _write_workspace(Path(tmp), include_needs_review=True)
            _write_review_decisions(output, [
                {
                    "image_path": str(image),
                    "decision": "KEEP",
                    "workflow_state": "REVIEWED",
                },
            ])

            data = build_review_data(output)

        overview = data["overview"]
        self.assertEqual(overview["image_count"], 3)
        self.assertEqual(
            overview["triage_counts"],
            {
                "Priority Review": 1,
                "Needs Review": 1,
                "No Findings Emitted": 1,
            },
        )
        self.assertEqual(overview["review_progress"]["reviewed_count"], 1)
        self.assertEqual(overview["review_progress"]["pending_review_count"], 2)
        self.assertEqual(overview["decision_counts"]["KEEP"], 1)
        self.assertTrue(overview["scope"]["read_only"])
        self.assertTrue(overview["scope"]["sidecar_driven"])
        self.assertTrue(overview["scope"]["does_not_run_analyzers"])
        self.assertTrue(overview["scope"]["does_not_modify_images"])
        self.assertEqual(
            overview["scope"]["writes_only"],
            ["review_decisions.json", "improvement_preview.json"],
        )

    def test_dataset_intelligence_review_status_and_scope_are_descriptive(self) -> None:
        with TemporaryDirectory() as tmp:
            output, image = _write_workspace(
                Path(tmp),
                include_needs_review=True,
                include_manifest=True,
                include_comparison=True,
            )
            _write_review_decisions(output, [
                {
                    "image_path": str(image),
                    "decision": "KEEP",
                    "workflow_state": "REVIEWED",
                },
            ])

            intelligence = build_review_data(output)["dataset_intelligence"]

        status = intelligence["review_status"]
        self.assertEqual(status["image_count"], 3)
        self.assertEqual(status["reviewed_count"], 1)
        self.assertEqual(status["undecided_count"], 2)
        self.assertEqual(status["decision_completion_percent"], 33.3)
        self.assertEqual(
            status["remaining_undecided_by_triage"],
            {
                "Priority Review": 0,
                "Needs Review": 1,
                "No Findings Emitted": 1,
            },
        )
        self.assertTrue(intelligence["scope"]["descriptive_only"])
        self.assertTrue(intelligence["scope"]["no_quality_score"])
        self.assertTrue(intelligence["scope"]["does_not_run_analyzers"])
        self.assertTrue(intelligence["scope"]["does_not_modify_images"])
        self.assertEqual(intelligence["scope"]["writes_only"], "review_decisions.json")

    def test_review_payload_exposes_optional_improvement_preview_sidecar(self) -> None:
        with TemporaryDirectory() as tmp:
            output, image = _write_workspace(Path(tmp))
            _write_improvement_preview(output, image)

            preview = build_review_data(output)["improvement_preview"]

        self.assertTrue(preview["available"])
        self.assertEqual(preview["schema"], IMPROVEMENT_PREVIEW_SCHEMA)
        self.assertEqual(preview["approval_states"], ["NOT_REQUESTED", "APPROVED", "REJECTED"])
        self.assertEqual(preview["preview_statuses"][2], "READY")
        self.assertEqual(preview["records"][0]["image"]["path"], str(image))
        compatibility = preview["records"][0]["provider_compatibility"]
        self.assertEqual(compatibility["status"], "compatible")
        self.assertEqual(compatibility["provider_type"], "MANUAL")
        self.assertFalse(compatibility["execution_available"])
        self.assertEqual(
            compatibility["provider_descriptor"]["implementation_status"],
            "not_implemented",
        )
        self.assertFalse(preview["provider_contract"]["execution_available"])

    def test_review_payload_normalizes_legacy_preview_entries_for_display(self) -> None:
        with TemporaryDirectory() as tmp:
            output, image = _write_workspace(Path(tmp))
            legacy_record = {
                "entry_type": "Improvement Candidate",
                "image_path": str(image),
                "filename": image.name,
                "suggested_improvement": "Manual Source Review",
                "triggering_findings": [
                    {
                        "analyzer": "texture_analyzer/v1",
                        "category": "artifact.texture",
                        "severity": "MEDIUM",
                    }
                ],
                "planning_status": "PLANNING_ONLY",
                "planning_notes": "Planning metadata only; no provider execution.",
                "execution_availability": "Not Implemented",
            }
            (output / "improvement_preview.json").write_text(
                json.dumps({
                    "schema": IMPROVEMENT_PREVIEW_SCHEMA,
                    "summary": {"preview_entry_count": 1},
                    "preview_entries": [legacy_record],
                }),
                encoding="utf-8",
            )

            data = build_review_data(output)

        preview = data["improvement_preview"]
        self.assertEqual(len(preview["records"]), 1)
        record = preview["records"][0]
        self.assertEqual(record["image"]["path"], str(image))
        self.assertEqual(record["image"]["filename"], image.name)
        self.assertEqual(record["recommended_operation"], "Manual Source Review")
        self.assertEqual(record["current_findings"][0]["category"], "artifact.texture")
        self.assertEqual(record["preview_status"], "PLANNING_ONLY")
        self.assertEqual(
            record["provider_compatibility"]["status"],
            "invalid_plan",
        )

    def test_review_payload_handles_missing_improvement_preview_sidecar(self) -> None:
        with TemporaryDirectory() as tmp:
            output, _image = _write_workspace(Path(tmp))

            preview = build_review_data(output)["improvement_preview"]

        self.assertFalse(preview["available"])
        self.assertEqual(preview["records"], [])
        self.assertEqual(preview["approval_states"], [])
        self.assertFalse(preview["provider_contract"]["execution_available"])
        self.assertEqual(len(preview["provider_contract"]["descriptors"]), 5)

    def test_review_payload_handles_unknown_and_malformed_preview_contract_data(self) -> None:
        with TemporaryDirectory() as tmp:
            output, image = _write_workspace(Path(tmp))
            _write_improvement_preview(output, image)
            path = output / "improvement_preview.json"
            preview = json.loads(path.read_text(encoding="utf-8"))
            preview["preview_records"][0]["required_provider_type"] = "MISSING"
            path.write_text(json.dumps(preview), encoding="utf-8")

            unknown = build_review_data(output)["improvement_preview"]["records"][0]
            preview["preview_records"][0]["recommended_operation"] = "RUN_SHELL"
            path.write_text(json.dumps(preview), encoding="utf-8")
            malformed = build_review_data(output)["improvement_preview"]["records"][0]

        self.assertEqual(
            unknown["provider_compatibility"]["status"],
            "unknown_provider",
        )
        self.assertIsNone(
            unknown["provider_compatibility"]["provider_descriptor"]
        )
        self.assertEqual(
            malformed["provider_compatibility"]["status"],
            "invalid_plan",
        )

    def test_dataset_intelligence_evidence_summary_counts_images_and_percentages(self) -> None:
        with TemporaryDirectory() as tmp:
            output, image = _write_workspace(Path(tmp), include_needs_review=True)
            _write_review_decisions(output, [
                {
                    "image_path": str(image),
                    "decision": "KEEP",
                    "workflow_state": "REVIEWED",
                },
            ])

            data = build_review_data(output)
            evidence = data["dataset_intelligence"]["evidence_summary"]

        self.assertEqual(
            build_intelligence_evidence_summary(data["images"]),
            evidence,
        )
        texture = evidence["category_rows"][0]
        self.assertEqual(texture["finding_category"], "artifact.texture")
        self.assertEqual(texture["finding_count"], 2)
        self.assertEqual(texture["affected_image_count"], 2)
        self.assertEqual(texture["affected_image_percentage"], 66.7)
        self.assertEqual(texture["highest_observed_severity"], "HIGH")
        self.assertEqual(texture["undecided_image_count"], 1)
        self.assertEqual(evidence["concentration"]["top_category"], "artifact.texture")

    def test_dataset_intelligence_analyzer_contribution_uses_manifest_when_available(self) -> None:
        with TemporaryDirectory() as tmp:
            output, _image = _write_workspace(
                Path(tmp),
                include_needs_review=True,
                include_manifest=True,
            )

            data = build_review_data(output)
            rows = data["dataset_intelligence"]["analyzer_contribution"]
            manifest = load_review_workspace(output).inspection_manifest

        self.assertEqual(
            build_intelligence_analyzer_contribution(
                data["analyzer_coverage"],
                manifest,
            ),
            rows,
        )
        texture = [row for row in rows if row["analyzer"] == "texture_analyzer"][0]
        self.assertEqual(texture["family"], "Technical Quality")
        self.assertEqual(texture["calibration_status"], "advisory")
        self.assertEqual(texture["execution_policy"], "enabled")
        self.assertEqual(texture["display_policy"], "visible")
        self.assertEqual(texture["triage_policy"], "included")
        self.assertEqual(texture["metadata_source"], "inspection_manifest")

    def test_dataset_intelligence_analyzer_contribution_falls_back_without_manifest(self) -> None:
        with TemporaryDirectory() as tmp:
            output, _image = _write_workspace(Path(tmp), include_needs_review=True)

            rows = build_review_data(output)["dataset_intelligence"]["analyzer_contribution"]

        texture = [row for row in rows if row["analyzer"] == "texture_analyzer"][0]
        self.assertEqual(texture["family"], "not recorded")
        self.assertEqual(texture["execution_policy"], "not recorded")
        self.assertEqual(texture["display_policy"], "not recorded")
        self.assertEqual(texture["triage_policy"], "not recorded")
        self.assertEqual(texture["metadata_source"], "recommendation_summary")

    def test_dataset_intelligence_coverage_characteristics_and_provenance(self) -> None:
        with TemporaryDirectory() as tmp:
            output, _image = _write_workspace(
                Path(tmp),
                include_needs_review=True,
                include_manifest=True,
                include_comparison=True,
            )

            intelligence = build_review_data(output)["dataset_intelligence"]

        coverage = intelligence["dataset_coverage"]
        self.assertTrue(coverage["required_sidecars"]["inspection_report.json"])
        self.assertTrue(coverage["required_sidecars"]["recommendation_summary.json"])
        self.assertTrue(coverage["optional_sidecars"]["inspection_manifest.json"])
        self.assertFalse(coverage["optional_sidecars"]["review_decisions.json"])
        self.assertTrue(coverage["comparison_available"])
        self.assertEqual(coverage["image_count"], 3)
        self.assertEqual(coverage["analyzed_count"], 3)
        self.assertEqual(coverage["error_count"], 0)
        characteristics = intelligence["dataset_characteristics"]
        self.assertEqual(characteristics["inspection_profile"]["id"], "default")
        self.assertEqual(characteristics["dataset_forge_version"], "1.0.0")
        self.assertEqual(characteristics["inspection_completed_at"], "2026-07-07T00:00:01Z")
        provenance = intelligence["provenance"]
        self.assertTrue(provenance["manifest_available"])
        self.assertTrue(provenance["comparison_available"])
        self.assertEqual(provenance["inspection_profile"]["version"], "v1")

    def test_dataset_intelligence_guidance_ordering_is_deterministic(self) -> None:
        with TemporaryDirectory() as tmp:
            output, image = _write_workspace(Path(tmp), include_needs_review=True)

            first = build_review_data(output)["dataset_intelligence"]["review_guidance"]
            _write_review_decisions(output, [
                {
                    "image_path": str(image),
                    "decision": "KEEP",
                    "workflow_state": "REVIEWED",
                },
            ])
            second = build_review_data(output)["dataset_intelligence"]["review_guidance"]

        self.assertEqual(first["next_review_focus"]["target_filter"]["triage_status"], "Priority Review")
        self.assertEqual(second["next_review_focus"]["target_filter"]["triage_status"], "Needs Review")
        self.assertEqual(second["remaining_priority_review_work"], 0)
        self.assertEqual(second["remaining_needs_review_work"], 1)
        self.assertEqual(
            second["optional_no_findings_emitted_sampling"]["remaining_undecided"],
            1,
        )

    def test_overview_next_action_order_is_deterministic(self) -> None:
        with TemporaryDirectory() as tmp:
            output, image = _write_workspace(Path(tmp), include_needs_review=True)

            first = build_review_data(output)["overview"]["next_action"]
            _write_review_decisions(output, [
                {
                    "image_path": str(image),
                    "decision": "KEEP",
                    "workflow_state": "REVIEWED",
                },
            ])
            second = build_review_data(output)["overview"]["next_action"]

        self.assertEqual(first["label"], "Review Priority Review images")
        self.assertEqual(first["target_filter"]["triage_status"], "Priority Review")
        self.assertEqual(second["label"], "Review Needs Review images")
        self.assertEqual(second["target_filter"]["triage_status"], "Needs Review")

    def test_next_action_prioritizes_unresolved_severity_and_evidence(self) -> None:
        images = [
            {
                "id": "low-many",
                "filename": "a.png",
                "image_path": "a.png",
                "triage_status": "Priority Review",
                "decision": "UNDECIDED",
                "severities": ["LOW"],
                "finding_count": 5,
                "max_confidence": 0.9,
            },
            {
                "id": "high-one",
                "filename": "z.png",
                "image_path": "z.png",
                "triage_status": "Priority Review",
                "decision": None,
                "severities": ["HIGH"],
                "finding_count": 1,
                "max_confidence": 0.2,
            },
            {
                "id": "decided-critical",
                "filename": "critical.png",
                "image_path": "critical.png",
                "triage_status": "Priority Review",
                "decision": "KEEP",
                "severities": ["CRITICAL"],
                "finding_count": 8,
                "max_confidence": 1.0,
            },
        ]

        first = build_next_action(images)
        second = build_next_action(list(reversed(images)))

        self.assertEqual(first["target_image_id"], "high-one")
        self.assertEqual(second, first)

    def test_next_action_orders_malformed_legacy_values_deterministically(self) -> None:
        images = [
            {
                "id": "z-malformed",
                "filename": "z.png",
                "image_path": "z.png",
                "triage_status": "Priority Review",
                "decision": "UNDECIDED",
                "severities": None,
                "finding_count": "unknown",
                "max_confidence": "unknown",
            },
            {
                "id": "a-missing",
                "filename": "a.png",
                "image_path": "a.png",
                "triage_status": "Priority Review",
                "decision": "UNDECIDED",
            },
        ]

        first = build_next_action(images)
        second = build_next_action(list(reversed(images)))

        self.assertEqual(first["target_image_id"], "a-missing")
        self.assertEqual(second, first)

    def test_overview_top_categories_are_sorted_by_count_then_name(self) -> None:
        with TemporaryDirectory() as tmp:
            output, _image = _write_workspace(Path(tmp), include_needs_review=True)

            data = build_review_data(output)

        categories = data["overview"]["top_finding_categories"]
        self.assertEqual(
            categories[:3],
            [
                {
                    "category": "artifact.texture",
                    "count": 2,
                    "highest_severity": "HIGH",
                },
                {
                    "category": "artifact.high_frequency_isolated",
                    "count": 1,
                    "highest_severity": "MEDIUM",
                },
                {
                    "category": "artifact.oversharpening_halo",
                    "count": 1,
                    "highest_severity": "MEDIUM",
                },
            ],
        )

    def test_build_review_data_does_not_write_files(self) -> None:
        with TemporaryDirectory() as tmp:
            output, _image = _write_workspace(Path(tmp), include_needs_review=True)
            before = sorted(path.name for path in output.iterdir())

            build_review_data(output)
            after = sorted(path.name for path in output.iterdir())

        self.assertEqual(after, before)

    def test_existing_decisions_load_into_rows(self) -> None:
        with TemporaryDirectory() as tmp:
            output, image = _write_workspace(Path(tmp))
            (output / "review_decisions.json").write_text(
                json.dumps({
                    "schema": REVIEW_DECISIONS_SCHEMA,
                    "decisions": [
                        {
                            "image_path": str(image),
                            "decision": "ACCEPTED_STYLE_FALSE_POSITIVE",
                            "workflow_state": "REVIEWED",
                            "notes": "intentional style",
                        },
                    ],
                }),
                encoding="utf-8",
            )

            data = build_review_data(output)

        row = [
            row for row in data["rows"]
            if row["filename"] == "priority.png"
        ][0]
        self.assertEqual(row["decision"], "ACCEPTED_STYLE_FALSE_POSITIVE")
        self.assertEqual(row["workflow_state"], "REVIEWED")
        self.assertEqual(row["notes"], "intentional style")

    def test_post_update_writes_review_decisions_json(self) -> None:
        with TemporaryDirectory() as tmp:
            output, image = _write_workspace(Path(tmp))

            update_review_decision(output, {
                "image_path": str(image),
                "recommendation": "Priority Review",
                "decision": "IMPROVEMENT_CANDIDATE",
                "workflow_state": "REVIEWED",
                "notes": "visible artifact",
            })
            payload = json.loads((output / "review_decisions.json").read_text(encoding="utf-8"))

        self.assertEqual(payload["schema"], REVIEW_DECISIONS_SCHEMA)
        self.assertEqual(payload["decisions"][0]["decision"], "IMPROVEMENT_CANDIDATE")
        self.assertEqual(payload["decisions"][0]["workflow_state"], "REVIEWED")
        self.assertEqual(payload["decisions"][0]["notes"], "visible artifact")

    def test_preview_approval_update_writes_only_improvement_preview(self) -> None:
        with TemporaryDirectory() as tmp:
            output, image = _write_workspace(Path(tmp))
            _write_improvement_preview(output, image)
            image_before = image.read_bytes()
            inspection_before = (output / "inspection_report.json").read_text(encoding="utf-8")
            recommendation_before = (output / "recommendation_summary.json").read_text(encoding="utf-8")

            data = update_preview_approval(output, {
                "image_path": str(image),
                "approval_state": "APPROVED",
            })
            payload = json.loads((output / "improvement_preview.json").read_text(encoding="utf-8"))
            image_after = image.read_bytes()
            inspection_after = (output / "inspection_report.json").read_text(encoding="utf-8")
            recommendation_after = (output / "recommendation_summary.json").read_text(encoding="utf-8")
            review_decisions_exists = (output / "review_decisions.json").exists()

        self.assertEqual(data["improvement_preview"]["records"][0]["approval_state"], "APPROVED")
        self.assertEqual(payload["preview_records"][0]["approval_state"], "APPROVED")
        self.assertEqual(payload["preview_entries"][0]["approval_state"], "APPROVED")
        self.assertEqual(payload["preview_records"][0]["preview_status"], "APPROVED")
        self.assertEqual(payload["summary"]["approval_state_counts"], {"APPROVED": 1})
        self.assertEqual(image_after, image_before)
        self.assertEqual(inspection_after, inspection_before)
        self.assertEqual(recommendation_after, recommendation_before)
        self.assertFalse(review_decisions_exists)

    def test_preview_approval_reset_returns_record_to_ready(self) -> None:
        with TemporaryDirectory() as tmp:
            output, image = _write_workspace(Path(tmp))
            _write_improvement_preview(output, image)
            update_preview_approval(output, {
                "image_path": str(image),
                "approval_state": "APPROVED",
            })

            update_preview_approval(output, {
                "image_path": str(image),
                "approval_state": "NOT_REQUESTED",
            })
            payload = json.loads((output / "improvement_preview.json").read_text(encoding="utf-8"))

        self.assertEqual(payload["preview_records"][0]["approval_state"], "NOT_REQUESTED")
        self.assertEqual(payload["preview_records"][0]["preview_status"], "READY")

    def test_preview_approval_requires_existing_record_and_known_state(self) -> None:
        with TemporaryDirectory() as tmp:
            output, image = _write_workspace(Path(tmp))
            _write_improvement_preview(output, image)

            with self.assertRaises(ReviewServerError):
                update_preview_approval(output, {
                    "image_path": str(image),
                    "approval_state": "EXECUTE",
                })
            with self.assertRaises(ReviewServerError):
                update_preview_approval(output, {
                    "image_path": str(output / "missing.png"),
                    "approval_state": "APPROVED",
                })

    def test_preview_approval_rejects_ambiguous_duplicate_records(self) -> None:
        with TemporaryDirectory() as tmp:
            output, image = _write_workspace(Path(tmp))
            _write_improvement_preview(output, image)
            path = output / "improvement_preview.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["preview_records"].append(dict(payload["preview_records"][0]))
            path.write_text(json.dumps(payload), encoding="utf-8")
            before = path.read_bytes()

            with self.assertRaisesRegex(ReviewServerError, "approval is ambiguous"):
                update_preview_approval(output, {
                    "image_path": str(image),
                    "approval_state": "APPROVED",
                })

            self.assertEqual(path.read_bytes(), before)

    def test_same_scope_decision_updates_and_unrelated_decisions_are_preserved(self) -> None:
        with TemporaryDirectory() as tmp:
            output, image = _write_workspace(Path(tmp))
            (output / "review_decisions.json").write_text(
                json.dumps({
                    "schema": REVIEW_DECISIONS_SCHEMA,
                    "decisions": [
                        {
                            "image_path": str(image),
                            "decision": "UNDECIDED",
                        },
                        {
                            "image_path": "unmatched.png",
                            "decision": "KEEP",
                        },
                    ],
                }),
                encoding="utf-8",
            )

            update_review_decision(output, {
                "image_path": str(image),
                "decision": "ACCEPTED_STYLE_FALSE_POSITIVE",
                "notes": "not an artifact",
            })
            payload = json.loads((output / "review_decisions.json").read_text(encoding="utf-8"))

        self.assertEqual(len(payload["decisions"]), 2)
        self.assertIn("KEEP", json.dumps(payload))
        self.assertIn("ACCEPTED_STYLE_FALSE_POSITIVE", json.dumps(payload))
        self.assertNotIn("UNDECIDED", json.dumps(payload))

    def test_duplicate_existing_decisions_are_rejected(self) -> None:
        with TemporaryDirectory() as tmp:
            output, image = _write_workspace(Path(tmp))
            duplicate = {
                "image_path": str(image),
                "decision": "UNDECIDED",
            }
            (output / "review_decisions.json").write_text(
                json.dumps({
                    "schema": REVIEW_DECISIONS_SCHEMA,
                    "decisions": [duplicate, dict(duplicate)],
                }),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                load_review_workspace(output)

    def test_invalid_decision_and_notes_are_rejected(self) -> None:
        with TemporaryDirectory() as tmp:
            output, image = _write_workspace(Path(tmp))
            with self.assertRaises(ReviewServerError):
                update_review_decision(output, {
                    "image_path": str(image),
                    "category": "artifact.texture",
                    "analyzer": "texture_analyzer/v1",
                    "decision": "AUTO_FIX",
                })
            with self.assertRaises(ReviewServerError):
                update_review_decision(output, {
                    "image_path": str(image),
                    "category": "artifact.texture",
                    "analyzer": "texture_analyzer/v1",
                    "decision": "UNDECIDED",
                    "notes": ["not", "plain", "text"],
                })

    def test_atomic_write_helper_replaces_json(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "review_decisions.json"
            atomic_write_json(path, {"schema": REVIEW_DECISIONS_SCHEMA, "decisions": []})

            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8"))["schema"],
                REVIEW_DECISIONS_SCHEMA,
            )
            self.assertFalse(list(Path(tmp).glob("*.tmp")))

    def test_updates_do_not_modify_source_or_existing_sidecars(self) -> None:
        with TemporaryDirectory() as tmp:
            output, image = _write_workspace(Path(tmp))
            image_before = image.read_bytes()
            report = output / "inspection_report.json"
            summary = output / "recommendation_summary.json"
            report_before = report.read_text(encoding="utf-8")
            summary_before = summary.read_text(encoding="utf-8")

            update_review_decision(output, {
                "image_path": str(image),
                "decision": "UNDECIDED",
                "notes": "",
            })

            self.assertEqual(image.read_bytes(), image_before)
            self.assertEqual(report.read_text(encoding="utf-8"), report_before)
            self.assertEqual(summary.read_text(encoding="utf-8"), summary_before)


class ReviewServerHttpTests(unittest.TestCase):
    def test_server_binds_only_to_localhost(self) -> None:
        with TemporaryDirectory() as tmp:
            output, _image = _write_workspace(Path(tmp))
            with self.assertRaises(ReviewServerError):
                create_review_server(output, host="0.0.0.0", port=0)

    def test_get_serves_html_and_data(self) -> None:
        with TemporaryDirectory() as tmp:
            output, _image = _write_workspace(Path(tmp))
            server = create_review_server(output, port=0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://{LOCAL_REVIEW_HOST}:{server.server_port}"
                html = urllib.request.urlopen(base + "/", timeout=5).read().decode("utf-8")
                data = json.loads(
                    urllib.request.urlopen(base + "/api/review-data", timeout=5)
                    .read()
                    .decode("utf-8")
                )
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

        self.assertIn("Dataset Forge Review Desk", html)
        self.assertIn("Review Overview", html)
        self.assertIn("Dataset Intelligence", html)
        self.assertIn('<summary>Dataset Intelligence</summary>', html)
        self.assertIn("Overview from existing sidecars. No scoring, no automation.", html)
        self.assertIn("<summary>Review Status</summary>", html)
        self.assertIn("<summary>Evidence Summary</summary>", html)
        self.assertIn("<summary>Analyzer Contribution</summary>", html)
        self.assertIn("<summary>Dataset Coverage</summary>", html)
        self.assertIn("<summary>Dataset Characteristics</summary>", html)
        self.assertIn("<summary>Unresolved Evidence Categories</summary>", html)
        self.assertIn("<summary>Improvement Preview</summary>", html)
        self.assertIn("Planning records and candidate review", html)
        self.assertIn("Candidate creation happens only through explicit CLI commands", html)
        self.assertIn("Provider implementations", html)
        self.assertIn("This candidate is an isolated preview artifact", html)
        self.assertIn("Required capabilities", html)
        self.assertIn("Descriptor check", html)
        self.assertIn("Provider availability", html)
        self.assertIn("The descriptor check compares static metadata only", html)
        self.assertIn("Raw category", html)
        self.assertIn("preview-workspace", html)
        self.assertIn("No candidate preview exists.", html)
        self.assertIn("Plan state", html)
        self.assertIn("Plan decision", html)
        self.assertIn("Candidate decision", html)
        self.assertIn("This decision updates <code>improvement_preview.json</code> only", html)
        self.assertIn("/api/preview-approval", html)
        self.assertIn("This plan describes manual caption review; no image candidate is expected.", html)
        self.assertIn("Your change was not saved.", html)
        self.assertIn("Show Next Review Set", html)
        self.assertIn("Show Next Review Set changes filters and selection only.", html)
        self.assertIn("Clear Filters", html)
        self.assertIn("Review Queue", html)
        self.assertIn("Accepted Style", html)
        self.assertIn("Improvement Candidate", html)
        self.assertIn("Exclude Candidate", html)
        self.assertNotIn("Removal Candidate", html)
        self.assertNotIn("'Removal Candidate'", html)
        self.assertIn("Decision progress and workflow stage are tracked separately", html)
        self.assertIn("Decisions recorded", html)
        self.assertIn("Decisions remaining", html)
        self.assertIn("Review Complete", html)
        self.assertIn("review-controls", html)
        self.assertIn("document.getElementById('detail').scrollTop = 0", html)
        self.assertIn("compareReviewOrder", html)
        self.assertIn("Unresolved first, then severity and evidence", html)
        self.assertIn('id="saveStatus"', html)
        self.assertIn("Saving...", html)
        self.assertIn("No images match this group with the current filters.", html)
        self.assertIn("Advisory review signal", html)
        self.assertIn("Crystal-like Surface Pattern", html)
        self.assertIn("High Microtexture", html)
        self.assertIn("Oversharpening / Edge Halo", html)
        self.assertIn("Isolated High-Frequency Specks", html)
        self.assertIn("Duplicate Image", html)
        self.assertIn("JPEG Compression Context", html)
        self.assertIn("8x8 JPEG Blocking", html)
        self.assertIn("JPEG Ringing / Mosquito Noise", html)
        self.assertIn("Chroma Encoding Artifact", html)
        self.assertIn("Banding / Posterization", html)
        self.assertIn("Low Source-Quality Context", html)
        self.assertIn("Missing Caption Sidecar", html)
        self.assertIn("Empty Caption Sidecar", html)
        self.assertIn("Duplicate Caption Text", html)
        self.assertIn("Very Short Caption", html)
        self.assertIn("Very Long Caption", html)
        self.assertIn("Repeated Caption Boilerplate", html)
        self.assertIn("Perceptual Near-Duplicate", html)
        self.assertIn("Texture Analyzer", html)
        self.assertIn("Crystal-like Surface Pattern Analyzer", html)
        self.assertIn("Duplicate Detection Analyzer", html)
        self.assertIn("Image Encoding Analyzer", html)
        self.assertIn("Caption / Metadata Analyzer", html)
        self.assertIn("Perceptual Near-Duplicate Analyzer", html)
        self.assertIn("Raw category", html)
        self.assertIn("Raw category IDs", html)
        self.assertIn("artifact.crystalline_faceting", html)
        self.assertIn("texture.high_microtexture", html)
        self.assertIn("dataset.duplicate.exact", html)
        self.assertIn("source_encoding.jpeg_compression", html)
        self.assertIn("caption.missing", html)
        self.assertIn("duplicate.perceptual", html)
        self.assertIn("Suggested representative is advisory", html)
        self.assertIn("Duplicate group", html)
        self.assertIn("Near-duplicate group", html)
        self.assertIn("Review signal only; not an automatic defect.", html)
        self.assertIn("String(value ?? '')", html)
        self.assertIn(":focus-visible", html)
        self.assertIn("sessionStorage", html)
        self.assertIn("UI_STATE_KEY_PREFIX", html)
        self.assertIn("visibleImages.length && !visibleImages.some", html)
        self.assertIn("renderGroups(); renderDetail(); writeUiState();", html)
        self.assertIn('id="filterSummary"', html)
        self.assertIn('role="status" aria-live="polite"', html)
        self.assertIn("Review Desk does not run analyzers", html)
        self.assertIn("Evidence Summary", html)
        self.assertIn("Analyzer Contribution", html)
        self.assertIn("Dataset Coverage", html)
        self.assertIn("Dataset Intelligence is descriptive only", html)
        self.assertIn("no quality score", html)
        self.assertIn("Set Aside Intent (no files moved)", html)
        self.assertIn("Set Aside Intent is workflow intent only", html)
        self.assertIn("No Findings Emitted means no current review finding. It is not a guarantee.", html)
        self.assertIn("review_decisions.json", html)
        self.assertIn("improvement_preview.json", html)
        self.assertIn('id="zoomViewer"', html)
        self.assertIn('tabindex="0" role="button" aria-label="Open zoom viewer for', html)
        self.assertIn("Actual size: 100% pixels", html)
        self.assertIn("mouse wheel zooms", html)
        self.assertIn("Space: larger preview", html)
        self.assertIn("export datasets", html)
        self.assertIn("does not create quarantine folders or move files", html)
        self.assertNotIn("Quarantine Planned (workflow note only)", html)
        self.assertNotIn(">Removal Candidate<", html)
        for forbidden in ("repair", "<form", "localStorage"):
            self.assertNotIn(forbidden, html)
        self.assertEqual(data["summary"]["review_image_count"], 2)
        self.assertIn("overview", data)
        self.assertIn("dataset_intelligence", data)

    def test_post_writes_decision(self) -> None:
        with TemporaryDirectory() as tmp:
            output, image = _write_workspace(Path(tmp))
            server = create_review_server(output, port=0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://{LOCAL_REVIEW_HOST}:{server.server_port}"
                request = urllib.request.Request(
                    base + "/api/decision",
                    data=json.dumps({
                        "image_path": str(image),
                        "decision": "KEEP",
                        "workflow_state": "REVIEWED",
                        "notes": "approved by human",
                    }).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                response = urllib.request.urlopen(request, timeout=5)
                data = json.loads(response.read().decode("utf-8"))
                payload = json.loads(
                    (output / "review_decisions.json").read_text(encoding="utf-8")
                )
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

        self.assertEqual(data["summary"]["already_reviewed_count"], 1)
        self.assertEqual(payload["decisions"][0]["decision"], "KEEP")

    def test_post_reports_sidecar_write_failure_as_json(self) -> None:
        with TemporaryDirectory() as tmp:
            output, image = _write_workspace(Path(tmp))
            server = create_review_server(output, port=0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://{LOCAL_REVIEW_HOST}:{server.server_port}"
                request = urllib.request.Request(
                    base + "/api/decision",
                    data=json.dumps({
                        "image_path": str(image),
                        "decision": "KEEP",
                    }).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with patch(
                    "dataset_forge.review_server.atomic_write_json",
                    side_effect=OSError("disk full"),
                ):
                    with self.assertRaises(urllib.error.HTTPError) as failed:
                        urllib.request.urlopen(request, timeout=5)
                    body = json.loads(failed.exception.read().decode("utf-8"))
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

        self.assertEqual(failed.exception.code, 500)
        self.assertIn("Could not save the sidecar update", body["error"])

    def test_post_writes_preview_approval(self) -> None:
        with TemporaryDirectory() as tmp:
            output, image = _write_workspace(Path(tmp))
            _write_improvement_preview(output, image)
            server = create_review_server(output, port=0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://{LOCAL_REVIEW_HOST}:{server.server_port}"
                request = urllib.request.Request(
                    base + "/api/preview-approval",
                    data=json.dumps({
                        "image_path": str(image),
                        "approval_state": "REJECTED",
                    }).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                response = urllib.request.urlopen(request, timeout=5)
                data = json.loads(response.read().decode("utf-8"))
                payload = json.loads(
                    (output / "improvement_preview.json").read_text(encoding="utf-8")
                )
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

        self.assertEqual(data["improvement_preview"]["records"][0]["approval_state"], "REJECTED")
        self.assertEqual(payload["preview_records"][0]["approval_state"], "REJECTED")

    def test_review_desk_serves_isolated_candidate_and_refreshes_approval(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            output, image = _write_workspace(root)
            candidate = root / "candidate.png"
            Image.fromarray(np.full((32, 48, 3), 180, dtype=np.uint8)).save(candidate)
            _write_improvement_preview(output, image)
            imported = import_manual_preview_candidate(output, image, candidate)
            server = create_review_server(output, port=0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://{LOCAL_REVIEW_HOST}:{server.server_port}"
                data = json.loads(
                    urllib.request.urlopen(base + "/api/review-data", timeout=5)
                    .read()
                    .decode("utf-8")
                )
                record = data["improvement_preview"]["records"][0]
                artifact = record["candidate_artifact"]
                image_bytes = urllib.request.urlopen(
                    base + artifact["image_url"], timeout=5
                ).read()
                artifact_bytes = Path(imported["artifact_path"]).read_bytes()
                with self.assertRaises(urllib.error.HTTPError) as unsafe:
                    urllib.request.urlopen(
                        base + "/preview-artifact?id=../candidate.png", timeout=5
                    )
                request = urllib.request.Request(
                    base + "/api/preview-approval",
                    data=json.dumps({
                        "image_path": str(image),
                        "approval_state": "APPROVED",
                    }).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                refreshed = json.loads(urllib.request.urlopen(request, timeout=5).read().decode("utf-8"))
                html = urllib.request.urlopen(base + "/", timeout=5).read().decode("utf-8")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

        self.assertTrue(artifact["available"])
        self.assertEqual(artifact["provider_display_name"], "Manual Import")
        self.assertTrue(artifact["image_url"].startswith("/preview-artifact?id=artifact-"))
        self.assertEqual(image_bytes, artifact_bytes)
        self.assertEqual(unsafe.exception.code, 404)
        refreshed_record = refreshed["improvement_preview"]["records"][0]
        self.assertEqual(refreshed_record["approval_state"], "APPROVED")
        self.assertEqual(refreshed_record["preview_status"], "APPROVED")
        self.assertIn("Candidate preview", html)
        self.assertIn("Side by side", html)
        self.assertIn("Candidate previews", html)
        self.assertNotIn("Generated previews", html)

    def test_post_rejects_invalid_decision(self) -> None:
        with TemporaryDirectory() as tmp:
            output, image = _write_workspace(Path(tmp))
            server = create_review_server(output, port=0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://{LOCAL_REVIEW_HOST}:{server.server_port}"
                request = urllib.request.Request(
                    base + "/api/decision",
                    data=json.dumps({
                        "image_path": str(image),
                        "category": "artifact.texture",
                        "analyzer": "texture_analyzer/v1",
                        "decision": "AUTO_FIX",
                    }).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with self.assertRaises(urllib.error.HTTPError) as ctx:
                    urllib.request.urlopen(request, timeout=5)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

        self.assertEqual(ctx.exception.code, 400)


if __name__ == "__main__":
    unittest.main()
