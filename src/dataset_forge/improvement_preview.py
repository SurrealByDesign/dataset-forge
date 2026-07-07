"""Deterministic preview rendering for Improvement Plans."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

from dataset_forge import __version__
from dataset_forge.comparison import COMPARISON_SUMMARY_SCHEMA
from dataset_forge.improvement_plan import IMPROVEMENT_PLAN_SCHEMA
from dataset_forge.review_decisions import load_review_decisions


IMPROVEMENT_PREVIEW_SCHEMA = "dataset-forge/improvement-preview/v1"

IMPROVEMENT_PLAN_JSON_FILENAME = "improvement_plan.json"
IMPROVEMENT_PREVIEW_JSON_FILENAME = "improvement_preview.json"
IMPROVEMENT_PREVIEW_MARKDOWN_FILENAME = "improvement_preview.md"
REVIEW_DECISIONS_FILENAME = "review_decisions.json"
COMPARISON_SUMMARY_FILENAME = "comparison_summary.json"
EXECUTION_AVAILABILITY = "Not Implemented"


class ImprovementPreviewError(ValueError):
    """Raised when improvement preview inputs are missing or unsupported."""


def write_improvement_preview(plan_path: Path) -> tuple[Path, Path]:
    """Build and write improvement_preview.json and improvement_preview.md."""

    plan_file = plan_path.expanduser().resolve()
    preview = build_improvement_preview(plan_file)
    output_dir = plan_file.parent
    json_path = output_dir / IMPROVEMENT_PREVIEW_JSON_FILENAME
    markdown_path = output_dir / IMPROVEMENT_PREVIEW_MARKDOWN_FILENAME
    json_path.write_text(
        json.dumps(preview, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(
        render_improvement_preview_markdown(preview),
        encoding="utf-8",
    )
    return json_path, markdown_path


def build_improvement_preview(
    plan_path: Path,
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a deterministic preview from an existing Improvement Plan."""

    plan_file = plan_path.expanduser().resolve()
    plan = _load_plan(plan_file)
    review_path = plan_file.parent / REVIEW_DECISIONS_FILENAME
    comparison_path = plan_file.parent / COMPARISON_SUMMARY_FILENAME
    review_decision_count = 0
    comparison_available = False

    if review_path.is_file():
        review_decision_count = len(load_review_decisions(review_path).decisions)
    if comparison_path.is_file():
        comparison = _load_json_object(comparison_path, "comparison summary")
        _validate_schema(comparison, COMPARISON_SUMMARY_SCHEMA, "comparison summary")
        comparison_available = True

    entries = _preview_entries(plan)
    timestamp = generated_at or datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return {
        "schema": IMPROVEMENT_PREVIEW_SCHEMA,
        "tool_version": __version__,
        "generated_at": timestamp,
        "inputs": {
            "improvement_plan": str(plan_file),
            "improvement_plan_schema": plan["schema"],
            "review_decisions": str(review_path) if review_path.is_file() else None,
            "review_decision_count": review_decision_count,
            "comparison_summary": str(comparison_path) if comparison_available else None,
            "comparison_summary_available": comparison_available,
        },
        "summary": {
            "preview_entry_count": len(entries),
            "execution_availability": EXECUTION_AVAILABILITY,
        },
        "preview_entries": entries,
    }


def render_improvement_preview_markdown(preview: Mapping[str, Any]) -> str:
    """Render a plain Markdown Improvement Preview."""

    lines = [
        "# Improvement Preview",
        "",
        "## Preview Summary",
        "",
        f"- Tool version: {preview['tool_version']}",
        f"- Generated at: {preview['generated_at']}",
        f"- Preview entries: {preview['summary']['preview_entry_count']}",
        f"- Execution availability: {preview['summary']['execution_availability']}",
        "",
        "## Entries",
        "",
    ]
    entries = preview["preview_entries"]
    if not entries:
        lines.extend(["No Improvement Candidates to preview.", ""])
    for entry in entries:
        lines.extend(_markdown_entry(entry))
    lines.extend([
        "## Important Notes",
        "",
        "This preview is documentation and traceability only.",
        "",
        "Execution availability is Not Implemented.",
        "",
        "Dataset Forge did not inspect images, process pixels, modify source images, or export datasets.",
        "",
        "Suggested Improvements are abstract planning concepts only.",
        "",
    ])
    return "\n".join(lines).rstrip() + "\n"


def _load_plan(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ImprovementPreviewError(f"Missing improvement plan: {path}")
    plan = _load_json_object(path, "improvement plan")
    _validate_schema(plan, IMPROVEMENT_PLAN_SCHEMA, "improvement plan")
    return plan


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


def _preview_entries(plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for source, label in (
        ("improvement_candidates", "Improvement Candidate"),
        ("deferred_improvement_candidates", "Deferred Improvement Candidate"),
        ("suppressed_improvement_candidates", "Suppressed Improvement Candidate"),
    ):
        for item in plan.get(source, []):
            if isinstance(item, dict):
                entries.append(_preview_entry(item, label))
    return sorted(
        entries,
        key=lambda entry: (
            entry["entry_type"],
            entry["image_path"],
            entry["suggested_improvement"],
            entry["planning_status"],
        ),
    )


def _preview_entry(item: Mapping[str, Any], entry_type: str) -> dict[str, Any]:
    finding_refs = [
        {
            "category": str(ref.get("category", "")),
            "analyzer": str(ref.get("analyzer", "")),
            "severity": str(ref.get("severity", "")),
        }
        for ref in item.get("finding_references", [])
        if isinstance(ref, dict)
    ]
    return {
        "entry_type": entry_type,
        "image_path": str(item.get("image_path", "")),
        "filename": str(item.get("filename", "")),
        "recommendation": str(item.get("recommendation", "")),
        "suggested_improvement": str(item.get("suggested_improvement", "")),
        "evidence": {
            "primary_reason": str(item.get("primary_reason", "")),
            "finding_references": finding_refs,
        },
        "triggering_findings": finding_refs,
        "review_decision": item.get("review_decision"),
        "planning_status": str(item.get("status", "")),
        "planning_notes": str(item.get("planning_notes", "")),
        "execution_availability": EXECUTION_AVAILABILITY,
        "expected_outcome": _expected_outcome(item),
    }


def _expected_outcome(item: Mapping[str, Any]) -> str:
    return (
        "No image change. This preview documents the proposed "
        f"{item.get('suggested_improvement', 'Suggested Improvement')} for human review."
    )


def _markdown_entry(entry: Mapping[str, Any]) -> list[str]:
    lines = [
        f"### {entry['filename'] or entry['image_path']}",
        "",
        f"- Entry type: {entry['entry_type']}",
        f"- Recommendation: {entry['recommendation']}",
        f"- Suggested Improvement: {entry['suggested_improvement']}",
        f"- Evidence: {entry['evidence']['primary_reason']}",
        "- Triggering findings:",
    ]
    findings = entry["triggering_findings"]
    if findings:
        for ref in findings:
            lines.append(
                f"  - {ref['category']} / {ref['analyzer']} / {ref['severity']}"
            )
    else:
        lines.append("  - none")
    decision = entry["review_decision"]
    lines.extend([
        f"- Review decision: {decision.get('decision') if isinstance(decision, dict) else 'not provided'}",
        f"- Planning status: {entry['planning_status']}",
        f"- Planning notes: {entry['planning_notes']}",
        f"- Execution availability: {entry['execution_availability']}",
        f"- Expected outcome: {entry['expected_outcome']}",
        "",
    ])
    return lines
