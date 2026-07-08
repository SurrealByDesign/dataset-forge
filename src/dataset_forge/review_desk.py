"""Review Desk sidecar loading and deterministic data contract builders.

This module owns the internal payload consumed by the localhost Review Desk.
It reads generated sidecars and builds image-centered review data. It does not
run analyzers, write files, or modify source images.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote

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
    inspection_report: dict[str, Any]
    recommendation_summary: dict[str, Any]
    triage_dossiers: dict[str, Any]
    review_decisions: ReviewDecisionSet


def load_review_workspace(output_dir: Path) -> ReviewWorkspace:
    """Load sidecars required by the Review Desk."""

    root = output_dir.expanduser().resolve()
    inspection_path = root / INSPECTION_REPORT_FILENAME
    recommendation_path = root / RECOMMENDATION_SUMMARY_FILENAME
    decisions_path = root / REVIEW_DECISIONS_FILENAME
    triage_path = root / TRIAGE_DOSSIERS_FILENAME

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
        inspection_report=inspection_report,
        recommendation_summary=recommendation_summary,
        triage_dossiers=triage_dossiers,
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
        "analyzer_coverage": analyzer_coverage,
        "decision_values": sorted(_DECISION_VALUES),
        "workflow_states": sorted(_WORKFLOW_STATES),
        "scope": {
            "local_only": True,
            "read_only_inputs": True,
            "writes_only": REVIEW_DECISIONS_FILENAME,
            "execution": "out_of_scope",
            "cleanup": "out_of_scope",
            "export": "out_of_scope",
            "source_image_modification": "out_of_scope",
            "file_movement": "out_of_scope",
        },
        "images": images,
        "rows": images,
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
            "writes_only": REVIEW_DECISIONS_FILENAME,
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
            first = sorted(matches, key=lambda image: image["filename"])[0]
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
    "LOCAL_REVIEW_HOST",
    "RECOMMENDATION_SUMMARY_FILENAME",
    "REVIEW_DECISIONS_FILENAME",
    "REVIEW_DESK_DATA_SCHEMA",
    "TRIAGE_DOSSIERS_FILENAME",
    "ReviewDeskError",
    "ReviewWorkspace",
    "build_analyzer_coverage",
    "build_next_action",
    "build_overview",
    "build_review_data",
    "build_review_images",
    "build_review_payload",
    "build_review_progress",
    "build_top_categories",
    "load_review_workspace",
]
