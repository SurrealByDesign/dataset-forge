"""Review Desk sidecar loading and deterministic data contract builders.

This module owns the internal payload consumed by the localhost Review Desk.
It reads generated sidecars and builds image-centered review data. It does not
run analyzers, write files, or modify source images.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote

from dataset_forge.preview_provider_contract import (
    DEFAULT_PROVIDER_EXECUTION_POLICY,
    PreviewProviderContractError,
    match_preview_provider,
    preview_provider_descriptor,
    preview_provider_descriptors,
)
from dataset_forge.preview_artifacts import (
    load_preview_artifacts,
    preview_artifact_path,
    preview_plan_record_id,
)
from dataset_forge.review_decisions import (
    REVIEW_DECISIONS_SCHEMA,
    ReviewDecisionSet,
    ReviewDecisionValue,
    ReviewWorkflowState,
    load_review_decisions,
)

LOCAL_REVIEW_HOST = "127.0.0.1"
DEFAULT_REVIEW_PORT = 8765

INSPECTION_REPORT_FILENAME = "inspection_report.json"
RECOMMENDATION_SUMMARY_FILENAME = "recommendation_summary.json"
REVIEW_DECISIONS_FILENAME = "review_decisions.json"
TRIAGE_DOSSIERS_FILENAME = "triage_dossiers.json"
INSPECTION_MANIFEST_FILENAME = "inspection_manifest.json"
COMPARISON_SUMMARY_FILENAME = "comparison_summary.json"
IMPROVEMENT_PREVIEW_FILENAME = "improvement_preview.json"
REVIEW_DESK_DATA_SCHEMA = "dataset-forge/review-desk-data/v1"

_DECISION_VALUES = {value.value for value in ReviewDecisionValue}
_WORKFLOW_STATES = {value.value for value in ReviewWorkflowState}


class ReviewDeskError(ValueError):
    """Raised when a Review Desk workspace or request is invalid."""


@dataclass(frozen=True)
class ReviewWorkspace:
    output_dir: Path
    inspection_report_path: Path
    recommendation_summary_path: Path
    review_decisions_path: Path
    triage_dossiers_path: Path
    inspection_manifest_path: Path
    comparison_summary_path: Path
    improvement_preview_path: Path
    inspection_report: dict[str, Any]
    recommendation_summary: dict[str, Any]
    triage_dossiers: dict[str, Any]
    inspection_manifest: dict[str, Any] | None
    inspection_manifest_error: str
    comparison_summary: dict[str, Any] | None
    comparison_summary_error: str
    improvement_preview: dict[str, Any] | None
    improvement_preview_error: str
    review_decisions: ReviewDecisionSet


def load_review_workspace(output_dir: Path) -> ReviewWorkspace:
    """Load sidecars required by the Review Desk."""

    root = output_dir.expanduser().resolve()
    inspection_path = root / INSPECTION_REPORT_FILENAME
    recommendation_path = root / RECOMMENDATION_SUMMARY_FILENAME
    decisions_path = root / REVIEW_DECISIONS_FILENAME
    triage_path = root / TRIAGE_DOSSIERS_FILENAME
    manifest_path = root / INSPECTION_MANIFEST_FILENAME
    comparison_path = root / COMPARISON_SUMMARY_FILENAME
    preview_path = root / IMPROVEMENT_PREVIEW_FILENAME

    if not inspection_path.exists():
        raise ReviewDeskError(
            f"Missing required sidecar: {inspection_path}. "
            "Run 'dataset-forge inspect <dataset>' first and pass the inspect_output folder."
        )
    if not recommendation_path.exists():
        raise ReviewDeskError(
            f"Missing required sidecar: {recommendation_path}. "
            "Run 'dataset-forge inspect <dataset>' first and pass the inspect_output folder."
        )

    inspection_report = _load_json_object(inspection_path, "inspection report")
    recommendation_summary = _load_json_object(
        recommendation_path,
        "recommendation summary",
    )
    triage_dossiers = (
        _load_json_object(triage_path, "triage dossiers")
        if triage_path.exists()
        else {"schema": "dataset-forge/triage-dossiers/missing", "dossiers": []}
    )
    inspection_manifest, inspection_manifest_error = _load_optional_json_object(
        manifest_path,
        "inspection manifest",
    )
    comparison_summary, comparison_summary_error = _load_optional_json_object(
        comparison_path,
        "comparison summary",
    )
    improvement_preview, improvement_preview_error = _load_optional_json_object(
        preview_path,
        "improvement preview",
    )
    decisions = (
        load_review_decisions(decisions_path)
        if decisions_path.exists()
        else ReviewDecisionSet(schema=REVIEW_DECISIONS_SCHEMA, decisions=())
    )

    return ReviewWorkspace(
        output_dir=root,
        inspection_report_path=inspection_path,
        recommendation_summary_path=recommendation_path,
        review_decisions_path=decisions_path,
        triage_dossiers_path=triage_path,
        inspection_manifest_path=manifest_path,
        comparison_summary_path=comparison_path,
        improvement_preview_path=preview_path,
        inspection_report=inspection_report,
        recommendation_summary=recommendation_summary,
        triage_dossiers=triage_dossiers,
        inspection_manifest=inspection_manifest,
        inspection_manifest_error=inspection_manifest_error,
        comparison_summary=comparison_summary,
        comparison_summary_error=comparison_summary_error,
        improvement_preview=improvement_preview,
        improvement_preview_error=improvement_preview_error,
        review_decisions=decisions,
    )


def build_review_data(output_dir: Path) -> dict[str, Any]:
    """Build deterministic Review Desk data from existing sidecars."""

    return build_review_payload(load_review_workspace(output_dir))


def build_review_payload(workspace: ReviewWorkspace) -> dict[str, Any]:
    """Build the stable image-centered Review Desk payload."""

    images = build_review_images(workspace)
    source_summary = workspace.recommendation_summary.get("summary", {})
    analyzer_coverage = workspace.recommendation_summary.get("analyzer_coverage", {})
    progress = build_review_progress(images)
    decision_counts = _decision_counts(images)
    workflow_counts = _workflow_counts(images)
    overview = build_overview(images, source_summary, analyzer_coverage)
    dataset_intelligence = build_dataset_intelligence(
        workspace,
        images,
        source_summary,
        analyzer_coverage,
    )

    return {
        "schema": REVIEW_DESK_DATA_SCHEMA,
        "review_decisions_schema": REVIEW_DECISIONS_SCHEMA,
        "dataset_path": str(workspace.inspection_report.get("dataset_path", "")),
        "summary": {
            "image_count": int(source_summary.get("image_count", len(images))),
            "priority_review_count": int(source_summary.get("priority_review_count", 0)),
            "needs_review_count": int(source_summary.get("needs_review_count", 0)),
            "no_findings_emitted_count": _no_findings_count(source_summary),
            "review_image_count": len(images),
            "already_reviewed_count": progress["reviewed_count"],
            "pending_review_count": progress["pending_review_count"],
            "decision_counts": decision_counts,
            "workflow_counts": workflow_counts,
        },
        "overview": overview,
        "dataset_intelligence": dataset_intelligence,
        "improvement_preview": build_review_improvement_preview(workspace),
        "analyzer_coverage": analyzer_coverage,
        "decision_values": sorted(_DECISION_VALUES),
        "workflow_states": sorted(_WORKFLOW_STATES),
        "scope": {
            "local_only": True,
            "read_only_inputs": True,
            "writes_only": [REVIEW_DECISIONS_FILENAME, IMPROVEMENT_PREVIEW_FILENAME],
            "execution": "out_of_scope",
            "cleanup": "out_of_scope",
            "export": "out_of_scope",
            "source_image_modification": "out_of_scope",
            "file_movement": "out_of_scope",
        },
        "images": images,
        "rows": images,
    }


def build_review_improvement_preview(workspace: ReviewWorkspace) -> dict[str, Any]:
    """Expose optional Improvement Preview sidecar data for the Review Desk."""

    preview = workspace.improvement_preview
    provider_contract = _review_provider_contract()
    artifact_sidecar = load_preview_artifacts(workspace.output_dir)
    artifacts_by_plan = {
        str(artifact.get("preview_plan_record_id", "")): artifact
        for artifact in artifact_sidecar.get("artifacts", [])
        if isinstance(artifact, Mapping)
    }
    if preview is None:
        return {
            "available": False,
            "error": workspace.improvement_preview_error,
            "path": str(workspace.improvement_preview_path),
            "schema": "",
            "summary": {},
            "records": [],
            "preview_statuses": [],
            "approval_states": [],
            "provider_contract": provider_contract,
            "artifacts": artifact_sidecar,
            "scope": {
                "read_only": True,
                "sidecar_only": True,
                "candidate_generation_available_via_cli": True,
                "review_desk_does_not_generate_images": True,
                "does_not_execute_improvements": True,
                "does_not_modify_source_images": True,
            },
        }
    records = preview.get("preview_records", preview.get("preview_entries", []))
    if not isinstance(records, list):
        records = []
    review_records = [
        _review_preview_record(record, workspace.output_dir, artifacts_by_plan)
        for record in records
        if isinstance(record, Mapping)
    ]
    return {
        "available": True,
        "error": "",
        "path": str(workspace.improvement_preview_path),
        "schema": str(preview.get("schema", "")),
        "summary": preview.get("summary", {}) if isinstance(preview.get("summary"), Mapping) else {},
        "records": review_records,
        "preview_statuses": list(preview.get("preview_statuses", []))
        if isinstance(preview.get("preview_statuses"), list)
        else [],
        "approval_states": list(preview.get("approval_states", []))
        if isinstance(preview.get("approval_states"), list)
        else [],
        "provider_contract": provider_contract,
        "artifacts": artifact_sidecar,
        "scope": preview.get("scope", {}) if isinstance(preview.get("scope"), Mapping) else {},
    }


def _review_provider_contract() -> dict[str, Any]:
    """Build deterministic descriptor metadata for read-only Review Desk display."""

    return {
        "execution_available": False,
        "execution_policy": DEFAULT_PROVIDER_EXECUTION_POLICY.to_dict(),
        "descriptors": [
            descriptor.to_dict()
            for descriptor in preview_provider_descriptors()
        ],
    }


def _review_preview_record(
    record: Mapping[str, Any],
    output_dir: Path,
    artifacts_by_plan: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Add derived capability context without changing the source sidecar record."""

    result = dict(record)
    if not isinstance(result.get("image"), Mapping):
        image_path = str(record.get("image_path", ""))
        filename = str(record.get("filename", ""))
        if image_path or filename:
            result["image"] = {
                "path": image_path,
                "filename": filename,
            }
    if not result.get("recommended_operation") and record.get("suggested_improvement"):
        result["recommended_operation"] = str(record.get("suggested_improvement", ""))
    if not result.get("operation_rationale"):
        result["operation_rationale"] = str(
            record.get("operation_rationale")
            or record.get("planning_notes")
            or record.get("expected_outcome")
            or ""
        )
    if not result.get("current_findings") and isinstance(record.get("triggering_findings"), list):
        result["current_findings"] = list(record.get("triggering_findings", []))
    if not result.get("preview_status") and record.get("planning_status"):
        result["preview_status"] = str(record.get("planning_status", ""))
    operation = str(result.get("recommended_operation", ""))
    provider_type = str(result.get("required_provider_type", ""))
    descriptor = preview_provider_descriptor(provider_type)
    try:
        match = match_preview_provider(provider_type, operation)
        compatibility = match.to_dict()
    except PreviewProviderContractError as exc:
        compatibility = {
            "status": "invalid_plan",
            "provider_type": provider_type,
            "provider_id": descriptor.provider_id if descriptor else None,
            "required_capabilities": [],
            "missing_capabilities": [],
            "operation_supported": False,
            "execution_available": False,
            "error": str(exc),
        }
    compatibility["provider_descriptor"] = (
        descriptor.to_dict() if descriptor is not None else None
    )
    result["provider_compatibility"] = compatibility
    try:
        record_id = preview_plan_record_id(record)
    except ValueError:
        record_id = ""
    result["preview_record_id"] = record_id
    result["candidate_artifact"] = _review_candidate_artifact(
        output_dir,
        artifacts_by_plan.get(record_id),
    )
    return result


def _review_candidate_artifact(
    output_dir: Path,
    artifact: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Expose safe browser-facing candidate metadata without a filesystem path."""

    if artifact is None:
        return {"available": False, "reason": "No candidate artifact is associated with this preview plan."}
    candidate = artifact.get("candidate")
    if not isinstance(candidate, Mapping):
        return {"available": False, "reason": "Candidate artifact metadata is incomplete."}
    artifact_id = str(artifact.get("artifact_id", ""))
    path = preview_artifact_path(output_dir, artifact)
    if path is None:
        return {
            "available": False,
            "artifact_id": artifact_id,
            "reason": "Candidate artifact is unavailable or no longer matches its recorded hash.",
        }
    source = artifact.get("source") if isinstance(artifact.get("source"), Mapping) else {}
    provider = artifact.get("provider") if isinstance(artifact.get("provider"), Mapping) else {}
    generation = artifact.get("generation") if isinstance(artifact.get("generation"), Mapping) else {}
    return {
        "available": True,
        "artifact_id": artifact_id,
        "image_url": f"/preview-artifact?id={quote(artifact_id)}",
        "provider_type": str(provider.get("type", "MANUAL")),
        "provider_display_name": str(provider.get("display_name", "Manual Import")),
        "provider_version": str(provider.get("provider_version", "")),
        "status": str(artifact.get("status", "READY")),
        "original_filename": str(candidate.get("original_filename", "")),
        "sha256": str(candidate.get("sha256", "")),
        "byte_size": candidate.get("byte_size", 0),
        "width": candidate.get("width", 0),
        "height": candidate.get("height", 0),
        "format": str(candidate.get("format", "")),
        "source_sha256": str(source.get("sha256", "")),
        "source_width": source.get("width", 0),
        "source_height": source.get("height", 0),
        "source_format": str(source.get("format", "")),
        "warnings": list(artifact.get("warnings", [])) if isinstance(artifact.get("warnings"), list) else [],
        "imported_at": str(artifact.get("imported_at", "")),
        "generation": dict(generation),
        "execution_available": False,
    }


def build_dataset_intelligence(
    workspace: ReviewWorkspace,
    images: list[dict[str, Any]],
    summary: Mapping[str, Any],
    analyzer_coverage: Mapping[str, Any],
) -> dict[str, Any]:
    """Build deterministic dataset-level evidence organization."""

    return {
        "review_status": build_intelligence_review_status(images, summary),
        "evidence_summary": build_intelligence_evidence_summary(images),
        "analyzer_contribution": build_intelligence_analyzer_contribution(
            analyzer_coverage,
            workspace.inspection_manifest,
        ),
        "dataset_coverage": build_intelligence_dataset_coverage(
            workspace,
            summary,
        ),
        "dataset_characteristics": build_intelligence_dataset_characteristics(
            workspace.inspection_manifest,
            workspace.inspection_report,
        ),
        "review_guidance": build_intelligence_review_guidance(images),
        "provenance": build_intelligence_provenance(
            workspace.inspection_manifest,
            workspace.comparison_summary is not None,
        ),
        "scope": {
            "descriptive_only": True,
            "no_quality_score": True,
            "does_not_run_analyzers": True,
            "does_not_modify_images": True,
            "sidecar_only": True,
            "writes_only": REVIEW_DECISIONS_FILENAME,
        },
    }


def build_intelligence_review_status(
    images: list[dict[str, Any]],
    summary: Mapping[str, Any],
) -> dict[str, Any]:
    """Build dataset-level review status counts."""

    progress = build_review_progress(images)
    triage_counts = {
        "Priority Review": int(summary.get("priority_review_count", 0)),
        "Needs Review": int(summary.get("needs_review_count", 0)),
        "No Findings Emitted": _no_findings_count(summary),
    }
    return {
        "image_count": int(summary.get("image_count", len(images))),
        "triage_counts": triage_counts,
        "reviewed_count": progress["reviewed_count"],
        "undecided_count": progress["pending_review_count"],
        "decision_completion_percent": progress["completion_percent"],
        "decision_counts": _decision_counts(images),
        "workflow_counts": _workflow_counts(images),
        "remaining_undecided_by_triage": _remaining_undecided_by_triage(images),
    }


def build_intelligence_evidence_summary(
    images: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build deterministic finding category evidence rows."""

    image_count = len(images)
    severity_rank = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    rows: dict[str, dict[str, Any]] = {}
    affected: dict[str, set[str]] = {}
    undecided: dict[str, set[str]] = {}
    for image in images:
        image_id = str(image.get("image_path", image.get("id", "")))
        is_undecided = image.get("decision") in (None, ReviewDecisionValue.UNDECIDED.value)
        for finding in _image_findings(image):
            category = str(finding.get("category", ""))
            if not category:
                continue
            row = rows.setdefault(
                category,
                {
                    "finding_category": category,
                    "finding_count": 0,
                    "highest_observed_severity": "",
                },
            )
            row["finding_count"] += 1
            severity = str(finding.get("severity", ""))
            current = str(row.get("highest_observed_severity", ""))
            if current == "" or severity_rank.get(severity, 99) < severity_rank.get(current, 99):
                row["highest_observed_severity"] = severity
            affected.setdefault(category, set()).add(image_id)
            if is_undecided:
                undecided.setdefault(category, set()).add(image_id)

    category_rows = []
    for category, row in rows.items():
        affected_count = len(affected.get(category, set()))
        category_rows.append({
            **row,
            "affected_image_count": affected_count,
            "affected_image_percentage": _percentage(affected_count, image_count),
            "undecided_image_count": len(undecided.get(category, set())),
        })
    category_rows.sort(
        key=lambda item: (
            -int(item["affected_image_count"]),
            -int(item["finding_count"]),
            str(item["finding_category"]),
        )
    )
    top = category_rows[0] if category_rows else None
    return {
        "category_rows": category_rows,
        "concentration": {
            "top_category": top["finding_category"] if top else None,
            "top_category_image_count": int(top["affected_image_count"]) if top else 0,
            "top_category_percentage": (
                float(top["affected_image_percentage"]) if top else 0.0
            ),
        },
    }


def build_intelligence_analyzer_contribution(
    analyzer_coverage: Mapping[str, Any],
    inspection_manifest: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    """Build analyzer contribution rows from sidecar metadata."""

    coverage = _coverage_by_analyzer(analyzer_coverage)
    manifest_rows = _manifest_analyzers_by_id(inspection_manifest)
    analyzer_ids = sorted(set(coverage) | set(manifest_rows))
    rows = []
    for analyzer_id in analyzer_ids:
        coverage_row = coverage.get(analyzer_id, {})
        manifest_row = manifest_rows.get(analyzer_id, {})
        source = "inspection_manifest" if manifest_row else "recommendation_summary"
        rows.append({
            "analyzer": analyzer_id,
            "version": str(
                manifest_row.get("version")
                or coverage_row.get("version")
                or ""
            ),
            "family": str(manifest_row.get("family", "not recorded")),
            "finding_count": int(
                manifest_row.get("finding_count", coverage_row.get("finding_count", 0)) or 0
            ),
            "affected_image_count": int(
                manifest_row.get("image_count", coverage_row.get("image_count", 0)) or 0
            ),
            "calibration_status": str(
                manifest_row.get(
                    "calibration_status",
                    coverage_row.get("calibration_status", "advisory fallback"),
                )
            ),
            "execution_policy": _nested_policy(manifest_row, "execution", "not recorded"),
            "display_policy": _nested_policy(manifest_row, "display", "not recorded"),
            "triage_policy": _nested_policy(manifest_row, "triage", "not recorded"),
            "metadata_source": source,
        })
    return rows


def build_intelligence_dataset_coverage(
    workspace: ReviewWorkspace,
    summary: Mapping[str, Any],
) -> dict[str, Any]:
    """Build sidecar completeness and inspection coverage metadata."""

    manifest = workspace.inspection_manifest or {}
    dataset = manifest.get("dataset", {}) if isinstance(manifest, Mapping) else {}
    required = {
        INSPECTION_REPORT_FILENAME: workspace.inspection_report_path.is_file(),
        RECOMMENDATION_SUMMARY_FILENAME: workspace.recommendation_summary_path.is_file(),
    }
    optional = {
        TRIAGE_DOSSIERS_FILENAME: workspace.triage_dossiers_path.is_file(),
        INSPECTION_MANIFEST_FILENAME: workspace.inspection_manifest_path.is_file(),
        REVIEW_DECISIONS_FILENAME: workspace.review_decisions_path.is_file(),
        COMPARISON_SUMMARY_FILENAME: workspace.comparison_summary_path.is_file(),
        IMPROVEMENT_PREVIEW_FILENAME: workspace.improvement_preview_path.is_file(),
    }
    return {
        "required_sidecars": required,
        "optional_sidecars": optional,
        "manifest_available": workspace.inspection_manifest is not None,
        "manifest_error": workspace.inspection_manifest_error,
        "review_decisions_available": workspace.review_decisions_path.is_file(),
        "comparison_available": workspace.comparison_summary is not None,
        "comparison_error": workspace.comparison_summary_error,
        "improvement_preview_available": workspace.improvement_preview is not None,
        "improvement_preview_error": workspace.improvement_preview_error,
        "image_count": int(dataset.get("image_count", summary.get("image_count", 0)) or 0),
        "analyzed_count": int(
            dataset.get("analyzed_count", summary.get("image_count", 0)) or 0
        ),
        "error_count": int(
            dataset.get("error_count", summary.get("analyzer_error_count", 0)) or 0
        ),
    }


def build_intelligence_dataset_characteristics(
    inspection_manifest: Mapping[str, Any] | None,
    inspection_report: Mapping[str, Any],
) -> dict[str, Any]:
    """Expose dataset facts already present in sidecars."""

    manifest = inspection_manifest or {}
    inspection = manifest.get("inspection", {}) if isinstance(manifest, Mapping) else {}
    profile = inspection.get("profile", {}) if isinstance(inspection, Mapping) else {}
    tool = manifest.get("tool", {}) if isinstance(manifest, Mapping) else {}
    dataset = manifest.get("dataset", {}) if isinstance(manifest, Mapping) else {}
    return {
        "inspection_profile": _profile_payload(profile),
        "dataset_forge_version": str(tool.get("version", "")) if isinstance(tool, Mapping) else "",
        "inspection_started_at": str(inspection.get("started_at", "")) if isinstance(inspection, Mapping) else "",
        "inspection_completed_at": str(inspection.get("completed_at", "")) if isinstance(inspection, Mapping) else "",
        "dataset_path": str(
            dataset.get("path")
            if isinstance(dataset, Mapping) and dataset.get("path") is not None
            else inspection_report.get("dataset_path", "")
        ),
        "recursive": dataset.get("recursive") if isinstance(dataset, Mapping) else None,
        "limit": dataset.get("limit") if isinstance(dataset, Mapping) else None,
        "aspect_ratio_summary": inspection_report.get("aspect_ratio_summary"),
        "resolution_summary": inspection_report.get("resolution_summary"),
    }


def build_intelligence_review_guidance(images: list[dict[str, Any]]) -> dict[str, Any]:
    """Build deterministic review guidance without scoring readiness."""

    remaining = _remaining_undecided_by_triage(images)
    unresolved = build_intelligence_evidence_summary([
        image for image in images
        if image.get("decision") in (None, ReviewDecisionValue.UNDECIDED.value)
    ])["category_rows"]
    return {
        "next_review_focus": build_next_action(images),
        "remaining_priority_review_work": remaining["Priority Review"],
        "remaining_needs_review_work": remaining["Needs Review"],
        "unresolved_evidence_categories": unresolved,
        "optional_no_findings_emitted_sampling": {
            "remaining_undecided": remaining["No Findings Emitted"],
            "guidance": (
                "Optional sample only. No Findings Emitted means no current "
                "deterministic analyzer emitted a review finding."
            ),
        },
    }


def build_intelligence_provenance(
    inspection_manifest: Mapping[str, Any] | None,
    comparison_available: bool,
) -> dict[str, Any]:
    """Build pure provenance metadata for Dataset Intelligence."""

    manifest = inspection_manifest or {}
    inspection = manifest.get("inspection", {}) if isinstance(manifest, Mapping) else {}
    tool = manifest.get("tool", {}) if isinstance(manifest, Mapping) else {}
    profile = inspection.get("profile", {}) if isinstance(inspection, Mapping) else {}
    return {
        "inspection_profile": _profile_payload(profile),
        "dataset_forge_version": str(tool.get("version", "")) if isinstance(tool, Mapping) else "",
        "manifest_available": inspection_manifest is not None,
        "comparison_available": comparison_available,
    }


def build_overview(
    images: list[dict[str, Any]],
    summary: Mapping[str, Any],
    analyzer_coverage: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the deterministic Dataset Overview payload."""

    return {
        "image_count": int(summary.get("image_count", len(images))),
        "triage_counts": {
            "Priority Review": int(summary.get("priority_review_count", 0)),
            "Needs Review": int(summary.get("needs_review_count", 0)),
            "No Findings Emitted": _no_findings_count(summary),
        },
        "review_progress": build_review_progress(images),
        "decision_counts": _decision_counts(images),
        "workflow_counts": _workflow_counts(images),
        "top_finding_categories": build_top_categories(images),
        "analyzer_coverage_summary": build_analyzer_coverage(analyzer_coverage),
        "next_action": build_next_action(images),
        "scope": {
            "read_only": True,
            "sidecar_driven": True,
            "writes_only": [REVIEW_DECISIONS_FILENAME, IMPROVEMENT_PREVIEW_FILENAME],
            "does_not_run_analyzers": True,
            "does_not_modify_images": True,
            "does_not_move_copy_export_or_quarantine_files": True,
        },
        "no_finding_semantics": (
            "No Findings Emitted means no current deterministic analyzer emitted "
            "a review finding. It is not proof that an image is artifact-free, "
            "caption-ready, or suitable for training."
        ),
    }


def build_review_progress(images: list[dict[str, Any]]) -> dict[str, Any]:
    """Build deterministic review progress counts from image rows."""

    reviewed_count = sum(
        1 for image in images
        if image["decision"] not in (None, ReviewDecisionValue.UNDECIDED.value)
    )
    pending_count = len(images) - reviewed_count
    return {
        "review_image_count": len(images),
        "reviewed_count": reviewed_count,
        "pending_review_count": pending_count,
        "completion_percent": (
            round((reviewed_count / len(images)) * 100, 1)
            if images
            else 100.0
        ),
    }


def build_top_categories(images: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build top finding categories sorted by count, then category name."""

    counts: dict[str, int] = {}
    severity_rank = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    category_severity: dict[str, str] = {}
    for image in images:
        references = image.get("findings", []) or image.get("finding_refs", [])
        for finding in references:
            if not isinstance(finding, dict):
                continue
            category = str(finding.get("category", ""))
            if not category:
                continue
            counts[category] = counts.get(category, 0) + 1
            severity = str(finding.get("severity", ""))
            current = category_severity.get(category)
            if current is None or severity_rank.get(severity, 99) < severity_rank.get(current, 99):
                category_severity[category] = severity
    return [
        {
            "category": category,
            "count": count,
            "highest_severity": category_severity.get(category, ""),
        }
        for category, count in sorted(
            counts.items(),
            key=lambda item: (-item[1], item[0]),
        )[:8]
    ]


def build_analyzer_coverage(analyzer_coverage: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Build deterministic analyzer coverage rows for the Review Desk."""

    analyzers = analyzer_coverage.get("analyzers", [])
    if not isinstance(analyzers, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in analyzers:
        if not isinstance(item, dict):
            continue
        rows.append({
            "analyzer": str(item.get("analyzer", "")),
            "version": str(item.get("version", "")),
            "finding_count": int(item.get("finding_count", 0) or 0),
            "image_count": int(item.get("image_count", 0) or 0),
            "calibration_status": str(item.get("calibration_status", "advisory")),
        })
    return sorted(rows, key=lambda item: (item["analyzer"], item["version"]))


def build_next_action(images: list[dict[str, Any]]) -> dict[str, Any]:
    """Build deterministic next-action guidance from current review state."""

    ordered_targets = (
        (
            "Priority Review",
            "Review Priority Review images",
            "Highest-priority images still need human decisions.",
        ),
        (
            "Needs Review",
            "Review Needs Review images",
            "Priority Review images are decided; continue with remaining flagged images.",
        ),
        (
            "No Findings Emitted",
            "Optionally sample No Findings Emitted images",
            "Flagged images have decisions recorded; sample no-finding images if you want extra confidence.",
        ),
    )
    for triage, label, reason in ordered_targets:
        matches = [
            image for image in images
            if image["triage_status"] == triage
            and image["decision"] in (None, ReviewDecisionValue.UNDECIDED.value)
        ]
        if matches:
            first = sorted(matches, key=_review_urgency_key)[0]
            return {
                "label": label,
                "reason": reason,
                "target_filter": {
                    "triage_status": triage,
                    "decision": ReviewDecisionValue.UNDECIDED.value,
                },
                "target_image_id": first["id"],
                "target_filename": first["filename"],
            }
    return {
        "label": "Review decisions are complete",
        "reason": "Every image in the current Review Desk has a recorded decision.",
        "target_filter": {},
        "target_image_id": None,
        "target_filename": None,
    }


def _review_urgency_key(image: Mapping[str, Any]) -> tuple[Any, ...]:
    """Order unresolved review work using existing evidence only."""

    severity_rank = {
        "CRITICAL": 4,
        "HIGH": 3,
        "MEDIUM": 2,
        "LOW": 1,
    }
    severities = image.get("severities", [])
    highest_severity = max(
        (severity_rank.get(str(value), 0) for value in severities),
        default=0,
    ) if isinstance(severities, list) else 0
    decision = image.get("decision")
    decision_recorded = decision not in (None, ReviewDecisionValue.UNDECIDED.value)
    return (
        1 if decision_recorded else 0,
        -highest_severity,
        -_safe_order_number(image.get("finding_count")),
        -_safe_order_number(image.get("max_confidence")),
        str(image.get("filename", "")).casefold(),
        str(image.get("image_path", "")),
    )


def _safe_order_number(value: Any) -> float:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) else 0.0


def build_review_images(workspace: ReviewWorkspace) -> list[dict[str, Any]]:
    """Build deterministic image-centered Review Desk rows."""

    dossiers = {
        str(item.get("image_path", "")): item
        for item in workspace.triage_dossiers.get("dossiers", [])
        if isinstance(item, dict)
    }
    images: list[dict[str, Any]] = []
    for item in workspace.recommendation_summary.get("recommendations", []):
        image_path = str(item.get("image_path", ""))
        if not image_path:
            continue
        decision = workspace.review_decisions.decision_for(image_path)
        findings = list(item.get("findings", []))
        finding_refs = list(item.get("finding_refs", []))
        severities = _unique_values(findings, finding_refs, "severity")
        confidences = [
            float(finding.get("confidence", 0))
            for finding in findings
            if isinstance(finding, dict) and isinstance(finding.get("confidence"), int | float)
        ]
        categories = _unique_values(findings, finding_refs, "category")
        analyzers = _unique_values(findings, finding_refs, "analyzer")
        dossier = dossiers.get(image_path, {})
        images.append({
            "id": _row_id(image_path),
            "image_path": image_path,
            "thumbnail_url": f"/image?path={quote(image_path)}",
            "filename": Path(image_path).name or image_path,
            "triage_status": str(item.get("display_label", "")),
            "recommendation": str(item.get("recommendation", "")),
            "primary_reason": str(item.get("primary_reason", "")),
            "reason_codes": list(item.get("reason_codes", [])),
            "finding_categories": categories,
            "analyzers": analyzers,
            "severities": severities,
            "max_confidence": max(confidences) if confidences else None,
            "finding_count": len(finding_refs),
            "finding_refs": finding_refs,
            "findings": findings,
            "evidence_summary": _evidence_summary(findings),
            "suggested_review_action": str(
                dossier.get("suggested_human_action")
                or item.get("guidance", "")
            ),
            "confidence_note": str(item.get("confidence_note", "")),
            "no_finding_semantics": str(dossier.get("no_finding_semantics", "")),
            "dossier_anchor": _anchor_for_image(image_path),
            "decision": decision.decision if decision else None,
            "workflow_state": (
                decision.workflow_state
                if decision
                else ReviewWorkflowState.IN_DATASET.value
            ),
            "notes": decision.notes if decision else "",
            "decision_history": list(decision.decision_history) if decision else [],
        })
    return sorted(images, key=lambda row: (_triage_sort(row["recommendation"]), row["filename"]))


def _decision_counts(images: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {value: 0 for value in sorted(_DECISION_VALUES)}
    for image in images:
        if image["decision"] is not None:
            counts[image["decision"]] = counts.get(image["decision"], 0) + 1
    return counts


def _workflow_counts(images: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {value: 0 for value in sorted(_WORKFLOW_STATES)}
    for image in images:
        counts[image["workflow_state"]] = counts.get(image["workflow_state"], 0) + 1
    return counts


def _remaining_undecided_by_triage(images: list[dict[str, Any]]) -> dict[str, int]:
    counts = {
        "Priority Review": 0,
        "Needs Review": 0,
        "No Findings Emitted": 0,
    }
    for image in images:
        if image.get("decision") not in (None, ReviewDecisionValue.UNDECIDED.value):
            continue
        triage = str(image.get("triage_status", ""))
        if triage in counts:
            counts[triage] += 1
    return counts


def _image_findings(image: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    findings = image.get("findings", [])
    refs = image.get("finding_refs", [])
    if isinstance(findings, list) and findings:
        return [item for item in findings if isinstance(item, Mapping)]
    if isinstance(refs, list):
        return [item for item in refs if isinstance(item, Mapping)]
    return []


def _percentage(part: int, total: int) -> float:
    return round((part / total) * 100, 1) if total else 0.0


def _coverage_by_analyzer(analyzer_coverage: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    rows: dict[str, Mapping[str, Any]] = {}
    analyzers = analyzer_coverage.get("analyzers", [])
    if not isinstance(analyzers, list):
        return rows
    for item in analyzers:
        if isinstance(item, Mapping) and item.get("analyzer"):
            rows[str(item["analyzer"])] = item
    return rows


def _manifest_analyzers_by_id(
    inspection_manifest: Mapping[str, Any] | None,
) -> dict[str, Mapping[str, Any]]:
    if not inspection_manifest:
        return {}
    analyzers = inspection_manifest.get("analyzers", [])
    if not isinstance(analyzers, list):
        return {}
    rows: dict[str, Mapping[str, Any]] = {}
    for item in analyzers:
        if isinstance(item, Mapping) and item.get("id"):
            rows[str(item["id"])] = item
    return rows


def _nested_policy(
    row: Mapping[str, Any],
    policy_name: str,
    fallback: str,
) -> str:
    policy = row.get(policy_name, {})
    if not isinstance(policy, Mapping):
        return fallback
    return str(policy.get("policy", fallback))


def _profile_payload(profile: Any) -> dict[str, str] | None:
    if not isinstance(profile, Mapping):
        return None
    if not profile:
        return None
    return {
        "id": str(profile.get("id", "")),
        "display_name": str(profile.get("display_name", "")),
        "version": str(profile.get("version", "")),
    }


def _no_findings_count(summary: Mapping[str, Any]) -> int:
    return int(
        summary.get(
            "no_findings_emitted_count",
            summary.get("ready_for_training_count", 0),
        )
    )


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ReviewDeskError(f"Invalid {label} JSON: {path}") from exc
    if not isinstance(data, dict):
        raise ReviewDeskError(f"{label} must be a JSON object: {path}")
    return data


def _load_optional_json_object(path: Path, label: str) -> tuple[dict[str, Any] | None, str]:
    if not path.exists():
        return None, ""
    try:
        return _load_json_object(path, label), ""
    except ReviewDeskError as exc:
        return None, str(exc)


def _row_id(image_path: str) -> str:
    return sha256(image_path.encode("utf-8")).hexdigest()[:16]


def _unique_values(
    findings: list[Any],
    refs: list[Any],
    field: str,
) -> list[str]:
    values: list[str] = []
    for collection in (findings, refs):
        for item in collection:
            if not isinstance(item, dict):
                continue
            value = str(item.get(field, ""))
            if value and value not in values:
                values.append(value)
    return values


def _evidence_summary(findings: list[Any]) -> str:
    parts: list[str] = []
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        category = str(finding.get("category", "finding"))
        severity = str(finding.get("severity", ""))
        confidence = finding.get("confidence")
        label = f"{category}"
        if severity:
            label += f" ({severity})"
        if isinstance(confidence, int | float):
            label += f", confidence {confidence:.2f}"
        parts.append(label)
    return "; ".join(parts) if parts else "No current findings emitted."


def _anchor_for_image(image_path: str) -> str:
    return "#dossier-" + sha256(image_path.encode("utf-8")).hexdigest()[:12]


def _triage_sort(recommendation: str) -> int:
    return {
        "PRIORITY_REVIEW": 0,
        "NEEDS_REVIEW": 1,
        "READY_FOR_TRAINING": 2,
    }.get(recommendation, 3)


__all__ = [
    "DEFAULT_REVIEW_PORT",
    "INSPECTION_REPORT_FILENAME",
    "IMPROVEMENT_PREVIEW_FILENAME",
    "LOCAL_REVIEW_HOST",
    "RECOMMENDATION_SUMMARY_FILENAME",
    "REVIEW_DECISIONS_FILENAME",
    "REVIEW_DESK_DATA_SCHEMA",
    "TRIAGE_DOSSIERS_FILENAME",
    "ReviewDeskError",
    "ReviewWorkspace",
    "build_analyzer_coverage",
    "build_dataset_intelligence",
    "build_intelligence_analyzer_contribution",
    "build_intelligence_dataset_characteristics",
    "build_intelligence_dataset_coverage",
    "build_intelligence_evidence_summary",
    "build_intelligence_provenance",
    "build_intelligence_review_guidance",
    "build_intelligence_review_status",
    "build_next_action",
    "build_overview",
    "build_review_improvement_preview",
    "build_review_data",
    "build_review_images",
    "build_review_payload",
    "build_review_progress",
    "build_top_categories",
    "load_review_workspace",
]
