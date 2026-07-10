"""Deterministic Improvement Preview planning from existing sidecars.

Improvement Preview is a planning contract only. It describes what operation
would be appropriate if a human chose to improve an image. It does not process
pixels, generate preview images, call providers, execute improvements, or
modify source images.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from dataset_forge import __version__
from dataset_forge.preview_provider_contract import preview_provider_descriptors
from dataset_forge.recommendation_summary import RECOMMENDATION_SUMMARY_SCHEMA
from dataset_forge.report import REPORT_SCHEMA
from dataset_forge.review_decisions import (
    ReviewDecision,
    ReviewDecisionSet,
    ReviewDecisionValue,
    load_review_decisions,
)


IMPROVEMENT_PREVIEW_SCHEMA = "dataset-forge/improvement-preview/v1"

INSPECTION_REPORT_FILENAME = "inspection_report.json"
RECOMMENDATION_SUMMARY_FILENAME = "recommendation_summary.json"
REVIEW_DECISIONS_FILENAME = "review_decisions.json"
IMPROVEMENT_PREVIEW_JSON_FILENAME = "improvement_preview.json"
IMPROVEMENT_PREVIEW_MARKDOWN_FILENAME = "improvement_preview.md"

OPERATION_KEEP = "KEEP"
OPERATION_MANUAL_CAPTION = "MANUAL_CAPTION"
OPERATION_REMOVE_DUPLICATE = "REMOVE_DUPLICATE"
OPERATION_REPLACE_SOURCE = "REPLACE_SOURCE"
OPERATION_REDUCE_HALO = "REDUCE_HALO"
OPERATION_REDUCE_ENCODING_ARTIFACTS = "REDUCE_ENCODING_ARTIFACTS"
OPERATION_NO_ACTION = "NO_ACTION"

PROVIDER_LOCAL_CLASSICAL = "LOCAL_CLASSICAL"
PROVIDER_COMFYUI = "COMFYUI"
PROVIDER_KREA = "KREA"
PROVIDER_MANUAL = "MANUAL"
PROVIDER_UNKNOWN = "UNKNOWN"

STATUS_NOT_AVAILABLE = "NOT_AVAILABLE"
STATUS_WAITING_FOR_PROVIDER = "WAITING_FOR_PROVIDER"
STATUS_READY = "READY"
STATUS_REJECTED = "REJECTED"
STATUS_APPROVED = "APPROVED"

APPROVAL_NOT_REQUESTED = "NOT_REQUESTED"
APPROVAL_APPROVED = "APPROVED"
APPROVAL_REJECTED = "REJECTED"

OPERATION_TYPES = (
    OPERATION_KEEP,
    OPERATION_MANUAL_CAPTION,
    OPERATION_REMOVE_DUPLICATE,
    OPERATION_REPLACE_SOURCE,
    OPERATION_REDUCE_HALO,
    OPERATION_REDUCE_ENCODING_ARTIFACTS,
    OPERATION_NO_ACTION,
)
PROVIDER_TYPES = (
    PROVIDER_LOCAL_CLASSICAL,
    PROVIDER_COMFYUI,
    PROVIDER_KREA,
    PROVIDER_MANUAL,
    PROVIDER_UNKNOWN,
)
PREVIEW_STATUSES = (
    STATUS_NOT_AVAILABLE,
    STATUS_WAITING_FOR_PROVIDER,
    STATUS_READY,
    STATUS_REJECTED,
    STATUS_APPROVED,
)
APPROVAL_STATES = (
    APPROVAL_NOT_REQUESTED,
    APPROVAL_APPROVED,
    APPROVAL_REJECTED,
)


class ImprovementPreviewError(ValueError):
    """Raised when improvement preview inputs are missing or unsupported."""


@dataclass(frozen=True)
class ProviderDescriptor:
    """Capability metadata for future preview providers.

    This is not an implementation hook. Dataset Forge v1.5 records provider
    capability names only so future preview generation can extend the contract
    without changing the sidecar shape.
    """

    provider_type: str
    display_name: str
    capabilities: tuple[str, ...]
    implementation_status: str = "not_implemented"
    network_access: bool = False
    processes_images: bool = False
    modifies_source_images: bool = False
    generates_preview_images: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_type": self.provider_type,
            "display_name": self.display_name,
            "capabilities": list(self.capabilities),
            "implementation_status": self.implementation_status,
            "network_access": self.network_access,
            "processes_images": self.processes_images,
            "modifies_source_images": self.modifies_source_images,
            "generates_preview_images": self.generates_preview_images,
        }


_LEGACY_PROVIDER_DISPLAY_NAMES = {
    PROVIDER_LOCAL_CLASSICAL: "Local Classical Provider",
    PROVIDER_COMFYUI: "ComfyUI Provider",
    PROVIDER_KREA: "Krea Provider",
    PROVIDER_MANUAL: "Manual Provider",
    PROVIDER_UNKNOWN: "Unknown Provider",
}
_LEGACY_PROVIDER_CAPABILITIES = {
    PROVIDER_LOCAL_CLASSICAL: ("future_local_classical_preview",),
    PROVIDER_COMFYUI: ("future_external_preview",),
    PROVIDER_KREA: ("future_external_preview",),
    PROVIDER_MANUAL: ("human_supplied_review_or_replacement",),
    PROVIDER_UNKNOWN: ("provider_not_selected",),
}

# Preserve the Improvement Preview v1 embedded descriptor snapshot exactly.
# The v1.7 provider contract is richer runtime metadata; this adapter avoids a
# sidecar schema change while keeping provider types and implementation status
# sourced from the authoritative contract registry.
BUILT_IN_PROVIDER_DESCRIPTORS = tuple(
    ProviderDescriptor(
        provider_type=descriptor.provider_type,
        display_name=_LEGACY_PROVIDER_DISPLAY_NAMES[descriptor.provider_type],
        capabilities=_LEGACY_PROVIDER_CAPABILITIES[descriptor.provider_type],
        implementation_status=descriptor.implementation_status,
    )
    for descriptor in preview_provider_descriptors()
)


def provider_descriptors() -> tuple[ProviderDescriptor, ...]:
    """Return the deterministic provider capability descriptors."""

    return BUILT_IN_PROVIDER_DESCRIPTORS


def write_improvement_preview(inspect_output: Path) -> tuple[Path, Path]:
    """Build and write improvement_preview.json and improvement_preview.md."""

    root = inspect_output.expanduser().resolve()
    preview = build_improvement_preview(root)
    json_path = root / IMPROVEMENT_PREVIEW_JSON_FILENAME
    markdown_path = root / IMPROVEMENT_PREVIEW_MARKDOWN_FILENAME
    json_path.write_text(
        json.dumps(preview, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(
        render_improvement_preview_markdown(preview),
        encoding="utf-8",
    )
    return json_path, markdown_path


def build_improvement_preview(inspect_output: Path) -> dict[str, Any]:
    """Build a deterministic Improvement Preview from existing sidecars."""

    workspace = _load_workspace(inspect_output)
    records = _preview_records(workspace)
    operation_counts = _operation_counts(records)
    status_counts = _status_counts(records)
    return {
        "schema": IMPROVEMENT_PREVIEW_SCHEMA,
        "tool_version": __version__,
        "deterministic": True,
        "inputs": _input_references(workspace),
        "scope": {
            "planning_only": True,
            "read_only": True,
            "sidecar_based": True,
            "no_image_data": True,
            "no_generated_outputs": True,
            "no_prompts": True,
            "does_not_process_images": True,
            "does_not_modify_source_images": True,
            "does_not_execute_improvements": True,
            "does_not_integrate_providers": True,
            "does_not_export": True,
        },
        "operation_types": list(OPERATION_TYPES),
        "provider_types": list(PROVIDER_TYPES),
        "preview_statuses": list(PREVIEW_STATUSES),
        "approval_states": list(APPROVAL_STATES),
        "provider_descriptors": [
            descriptor.to_dict() for descriptor in provider_descriptors()
        ],
        "summary": {
            "record_count": len(records),
            "operation_counts": operation_counts,
            "preview_status_counts": status_counts,
            "approval_state_counts": _approval_counts(records),
            "execution_available": False,
            "provider_implementations_available": False,
            "generated_preview_image_count": 0,
        },
        "preview_records": records,
        "preview_entries": records,
    }


def render_improvement_preview_markdown(preview: Mapping[str, Any]) -> str:
    """Render a plain Markdown Improvement Preview plan."""

    summary = preview["summary"]
    lines = [
        "# Improvement Preview",
        "",
        "Planning infrastructure for future preview generation.",
        "",
        "No image processing, provider integration, preview image generation, "
        "dataset modification, or improvement execution was performed.",
        "",
        "## Summary",
        "",
        f"- Tool version: {preview['tool_version']}",
        f"- Records: {summary['record_count']}",
        f"- Execution available: {summary['execution_available']}",
        f"- Provider implementations available: {summary['provider_implementations_available']}",
        f"- Generated preview images: {summary['generated_preview_image_count']}",
        "",
        "## Records",
        "",
    ]
    records = preview["preview_records"]
    if not records:
        lines.extend(["No preview records.", ""])
    for record in records:
        lines.extend(_markdown_record(record))
    lines.extend([
        "## Important Notes",
        "",
        "Improvement Preview is advisory planning metadata only.",
        "",
        "Provider types describe future capabilities only. No provider implementation was called.",
        "",
        "Dataset Forge did not inspect pixels, process images, generate prompts, generate preview images, modify source images, move files, export datasets, or execute improvements.",
        "",
    ])
    return "\n".join(lines).rstrip() + "\n"


def _load_workspace(inspect_output: Path) -> dict[str, Any]:
    root = inspect_output.expanduser().resolve()
    inspection_path = root / INSPECTION_REPORT_FILENAME
    recommendation_path = root / RECOMMENDATION_SUMMARY_FILENAME
    review_path = root / REVIEW_DECISIONS_FILENAME

    if not inspection_path.is_file():
        raise ImprovementPreviewError(
            f"Missing inspection report: {inspection_path}. "
            "Run 'dataset-forge inspect <dataset>' first and pass the inspect_output folder."
        )
    if not recommendation_path.is_file():
        raise ImprovementPreviewError(
            f"Missing recommendation summary: {recommendation_path}. "
            "Run 'dataset-forge inspect <dataset>' first and pass the inspect_output folder."
        )

    inspection_report = _load_json_object(inspection_path, "inspection report")
    recommendation_summary = _load_json_object(
        recommendation_path,
        "recommendation summary",
    )
    _validate_schema(inspection_report, REPORT_SCHEMA, "inspection report")
    _validate_schema(
        recommendation_summary,
        RECOMMENDATION_SUMMARY_SCHEMA,
        "recommendation summary",
    )
    review_decisions = load_review_decisions(review_path) if review_path.is_file() else None
    return {
        "path": root,
        "inspection_report_path": inspection_path,
        "recommendation_summary_path": recommendation_path,
        "review_decisions_path": review_path,
        "inspection_report": inspection_report,
        "recommendation_summary": recommendation_summary,
        "review_decisions": review_decisions,
    }


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ImprovementPreviewError(f"Malformed JSON in {label}: {path}") from exc
    if not isinstance(payload, dict):
        raise ImprovementPreviewError(f"{label} must be a JSON object: {path}")
    return payload


def _validate_schema(payload: Mapping[str, Any], expected: str, label: str) -> None:
    schema = payload.get("schema")
    if schema != expected:
        raise ImprovementPreviewError(
            f"Unsupported {label} schema {schema!r}; expected {expected!r}"
        )


def _input_references(workspace: Mapping[str, Any]) -> dict[str, Any]:
    review_path = workspace["review_decisions_path"]
    return {
        "inspect_output": str(workspace["path"]),
        "inspection_report": str(workspace["inspection_report_path"]),
        "recommendation_summary": str(workspace["recommendation_summary_path"]),
        "review_decisions": str(review_path) if review_path.is_file() else None,
        "review_decisions_available": review_path.is_file(),
    }


def _preview_records(workspace: Mapping[str, Any]) -> list[dict[str, Any]]:
    decisions: ReviewDecisionSet | None = workspace["review_decisions"]
    records = []
    for recommendation in _sorted_recommendations(workspace["recommendation_summary"]):
        image_path = str(recommendation.get("image_path", ""))
        if not image_path:
            continue
        findings = _current_findings(recommendation)
        decision = _decision_for_image(decisions, image_path, findings)
        plan = _operation_plan(decision, findings, recommendation)
        records.append({
            "image": {
                "path": image_path,
                "filename": Path(image_path).name or image_path,
            },
            "review_decision": _decision_payload(decision),
            "current_findings": findings,
            "recommended_operation": plan["operation"],
            "operation_rationale": plan["rationale"],
            "confidence": plan["confidence"],
            "required_provider_type": plan["provider_type"],
            "preview_status": plan["preview_status"],
            "approval_state": plan["approval_state"],
            "notes": (
                "Planning only. No image data, generated outputs, prompts, "
                "provider calls, or execution are included."
            ),
        })
    return sorted(
        records,
        key=lambda item: (
            str(item["image"]["path"]),
            str(item["recommended_operation"]),
            str(item["preview_status"]),
        ),
    )


def _sorted_recommendations(summary: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return sorted(
        [
            item for item in summary.get("recommendations", [])
            if isinstance(item, Mapping)
        ],
        key=lambda item: (
            str(item.get("image_path", "")),
            str(item.get("recommendation", "")),
            str(item.get("primary_reason", "")),
        ),
    )


def _current_findings(recommendation: Mapping[str, Any]) -> list[dict[str, str]]:
    source = recommendation.get("findings") or recommendation.get("finding_refs") or []
    if not isinstance(source, list):
        return []
    findings = []
    for item in source:
        if not isinstance(item, Mapping):
            continue
        findings.append({
            "category": str(item.get("category", "")),
            "analyzer": str(item.get("analyzer", "")),
            "severity": str(item.get("severity", "")),
        })
    return sorted(
        findings,
        key=lambda item: (
            item["category"],
            item["analyzer"],
            item["severity"],
        ),
    )


def _decision_for_image(
    decisions: ReviewDecisionSet | None,
    image_path: str,
    findings: list[Mapping[str, str]],
) -> ReviewDecision | None:
    if decisions is None:
        return None
    for finding in findings:
        decision = decisions.decision_for(
            image_path,
            finding.get("category"),
            finding.get("analyzer"),
        )
        if decision is not None:
            return decision
    return decisions.decision_for(image_path)


def _decision_payload(decision: ReviewDecision | None) -> dict[str, Any] | None:
    return decision.to_dict() if decision is not None else None


def _operation_plan(
    decision: ReviewDecision | None,
    findings: list[Mapping[str, str]],
    recommendation: Mapping[str, Any],
) -> dict[str, Any]:
    decision_value = decision.decision if decision is not None else None
    categories = [str(finding.get("category", "")) for finding in findings]
    if decision_value in {
        ReviewDecisionValue.KEEP.value,
        ReviewDecisionValue.ACCEPTED_STYLE_FALSE_POSITIVE.value,
    }:
        return _plan(
            OPERATION_KEEP,
            "Human review chose to keep or accept the image as-is.",
            PROVIDER_MANUAL,
            STATUS_REJECTED,
            APPROVAL_REJECTED,
            findings,
        )
    if decision_value == ReviewDecisionValue.UNDECIDED.value:
        return _plan(
            OPERATION_NO_ACTION,
            "Human review is undecided, so no improvement operation is proposed.",
            PROVIDER_UNKNOWN,
            STATUS_NOT_AVAILABLE,
            APPROVAL_NOT_REQUESTED,
            findings,
        )
    if not findings:
        return _plan(
            OPERATION_NO_ACTION,
            "No current findings were emitted for this image.",
            PROVIDER_UNKNOWN,
            STATUS_NOT_AVAILABLE,
            APPROVAL_NOT_REQUESTED,
            findings,
        )

    operation, provider, status, rationale = _operation_from_categories(categories)
    approval = (
        APPROVAL_APPROVED
        if decision_value in {
            ReviewDecisionValue.IMPROVEMENT_CANDIDATE.value,
            ReviewDecisionValue.REMOVAL_CANDIDATE.value,
        }
        else APPROVAL_NOT_REQUESTED
    )
    if decision_value is None:
        rationale = (
            f"{rationale} No human review decision has approved this planning record."
        )
    else:
        rationale = f"{rationale} Human review decision: {decision_value}."
    confidence = _confidence(findings, recommendation)
    return _plan(operation, rationale, provider, status, approval, findings, confidence)


def _operation_from_categories(categories: list[str]) -> tuple[str, str, str, str]:
    category_set = set(categories)
    if any(category.startswith("caption.") for category in category_set):
        return (
            OPERATION_MANUAL_CAPTION,
            PROVIDER_MANUAL,
            STATUS_READY,
            "Caption findings indicate a manual caption review operation.",
        )
    if category_set & {"dataset.duplicate.exact", "duplicate.perceptual"}:
        return (
            OPERATION_REMOVE_DUPLICATE,
            PROVIDER_MANUAL,
            STATUS_READY,
            "Duplicate findings indicate a manual duplicate-resolution planning operation.",
        )
    if "artifact.oversharpening_halo" in category_set:
        return (
            OPERATION_REDUCE_HALO,
            PROVIDER_UNKNOWN,
            STATUS_WAITING_FOR_PROVIDER,
            "Halo findings indicate a future halo-reduction preview could be appropriate.",
        )
    if any(category.startswith("source_encoding.") for category in category_set):
        return (
            OPERATION_REDUCE_ENCODING_ARTIFACTS,
            PROVIDER_UNKNOWN,
            STATUS_WAITING_FOR_PROVIDER,
            "Source-encoding findings indicate a future encoding-artifact preview could be appropriate.",
        )
    return (
        OPERATION_REPLACE_SOURCE,
        PROVIDER_MANUAL,
        STATUS_READY,
        "Current findings indicate a manual source replacement or re-sourcing review may be appropriate.",
    )


def _plan(
    operation: str,
    rationale: str,
    provider_type: str,
    preview_status: str,
    approval_state: str,
    findings: list[Mapping[str, str]],
    confidence: float | None = None,
) -> dict[str, Any]:
    return {
        "operation": operation,
        "rationale": rationale,
        "provider_type": provider_type,
        "preview_status": preview_status,
        "approval_state": approval_state,
        "confidence": _confidence(findings, {}) if confidence is None else confidence,
    }


def _confidence(
    findings: list[Mapping[str, Any]],
    recommendation: Mapping[str, Any],
) -> float:
    values = [
        float(item["confidence"])
        for item in recommendation.get("findings", [])
        if isinstance(item, Mapping) and isinstance(item.get("confidence"), int | float)
    ]
    if values:
        return round(max(values), 4)
    severity_rank = {"CRITICAL": 0.8, "HIGH": 0.7, "MEDIUM": 0.55, "LOW": 0.4}
    severities = [
        severity_rank[str(item.get("severity", ""))]
        for item in findings
        if str(item.get("severity", "")) in severity_rank
    ]
    return round(max(severities), 4) if severities else 0.0


def _operation_counts(records: list[Mapping[str, Any]]) -> dict[str, int]:
    counts = {operation: 0 for operation in OPERATION_TYPES}
    for record in records:
        operation = str(record["recommended_operation"])
        counts[operation] = counts.get(operation, 0) + 1
    return {key: value for key, value in counts.items() if value}


def _status_counts(records: list[Mapping[str, Any]]) -> dict[str, int]:
    counts = {status: 0 for status in PREVIEW_STATUSES}
    for record in records:
        status = str(record["preview_status"])
        counts[status] = counts.get(status, 0) + 1
    return {key: value for key, value in counts.items() if value}


def _approval_counts(records: list[Mapping[str, Any]]) -> dict[str, int]:
    counts = {state: 0 for state in APPROVAL_STATES}
    for record in records:
        state = str(record["approval_state"])
        counts[state] = counts.get(state, 0) + 1
    return {key: value for key, value in counts.items() if value}


def _markdown_record(record: Mapping[str, Any]) -> list[str]:
    image = record["image"]
    findings = record["current_findings"]
    lines = [
        f"### {image['filename'] or image['path']}",
        "",
        f"- Image: {image['path']}",
        f"- Review decision: {_markdown_decision(record['review_decision'])}",
        f"- Recommended operation: {record['recommended_operation']}",
        f"- Operation rationale: {record['operation_rationale']}",
        f"- Confidence: {record['confidence']}",
        f"- Required provider type: {record['required_provider_type']}",
        f"- Preview status: {record['preview_status']}",
        f"- Approval state: {record['approval_state']}",
        "- Current findings:",
    ]
    if findings:
        for finding in findings:
            lines.append(
                f"  - {finding['category']} / {finding['analyzer']} / {finding['severity']}"
            )
    else:
        lines.append("  - none")
    lines.append("")
    return lines


def _markdown_decision(decision: Any) -> str:
    if isinstance(decision, Mapping):
        return str(decision.get("decision", "not provided"))
    return "not provided"


__all__ = [
    "APPROVAL_STATES",
    "BUILT_IN_PROVIDER_DESCRIPTORS",
    "IMPROVEMENT_PREVIEW_JSON_FILENAME",
    "IMPROVEMENT_PREVIEW_MARKDOWN_FILENAME",
    "IMPROVEMENT_PREVIEW_SCHEMA",
    "OPERATION_TYPES",
    "PREVIEW_STATUSES",
    "PROVIDER_TYPES",
    "ImprovementPreviewError",
    "ProviderDescriptor",
    "build_improvement_preview",
    "provider_descriptors",
    "render_improvement_preview_markdown",
    "write_improvement_preview",
]
