"""Image-level triage dossiers for Dataset Forge inspect outputs."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

from dataset_forge import __version__
from dataset_forge.finding import Finding
from dataset_forge.recommendation_summary import RecommendationSummary


TRIAGE_DOSSIER_SCHEMA = "dataset-forge/triage-dossiers/v1"
TRIAGE_DOSSIER_JSON = "triage_dossiers.json"
TRIAGE_DOSSIER_MARKDOWN = "triage_dossiers.md"
TRIAGE_POLICY_SEMANTICS = {
    "dossier_basis": "triage_included_findings",
    "visible_findings_basis": "display_visible_findings",
    "executed_findings_source": "inspection_report.json",
    "policy_source": "inspection_manifest.json",
    "all_current_findings_visible": True,
    "all_current_findings_triage_included": True,
}


def write_triage_dossier_files(
    findings: list[Finding],
    summary: RecommendationSummary,
    output_dir: Path,
    *,
    review_statuses: Mapping[str, Any] | None = None,
    generated_at: str | None = None,
) -> tuple[Path, Path]:
    """Write image-centered triage dossier JSON and Markdown sidecars."""

    output_dir.mkdir(parents=True, exist_ok=True)
    payload = build_triage_dossiers(
        findings,
        summary,
        review_statuses=review_statuses,
        generated_at=generated_at,
    )
    json_path = output_dir / TRIAGE_DOSSIER_JSON
    markdown_path = output_dir / TRIAGE_DOSSIER_MARKDOWN
    json_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(
        render_triage_dossiers_markdown(payload),
        encoding="utf-8",
    )
    return json_path, markdown_path


def build_triage_dossiers(
    findings: list[Finding],
    summary: RecommendationSummary,
    *,
    review_statuses: Mapping[str, Any] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build deterministic image-level dossiers from recommendations."""

    findings_by_image: dict[str, list[Finding]] = {}
    for finding in sorted(findings, key=lambda item: (str(item.image_path), item.analyzer, item.category)):
        findings_by_image.setdefault(str(finding.image_path), []).append(finding)

    return {
        "schema": TRIAGE_DOSSIER_SCHEMA,
        "tool_version": __version__,
        "generated_at": generated_at or _now_utc(),
        "summary": {
            "image_count": summary.image_count,
            "no_findings_emitted_count": summary.ready_for_training_count,
            "needs_review_count": summary.needs_review_count,
            "priority_review_count": summary.priority_review_count,
            "dossier_count": len(summary.recommendations),
        },
        "analyzer_coverage": summary.analyzer_coverage,
        "policy_semantics": dict(TRIAGE_POLICY_SEMANTICS),
        "scope": {
            "read_only": True,
            "advisory": True,
            "deterministic": True,
            "sidecar_based": True,
            "execution": "out_of_scope",
            "cleanup": "out_of_scope",
            "export": "out_of_scope",
            "source_image_modification": "out_of_scope",
            "pixel_modification": "out_of_scope",
        },
        "dossiers": [
            _dossier(item.to_dict(), findings_by_image.get(item.image_path, []), review_statuses)
            for item in summary.recommendations
        ],
    }


def render_triage_dossiers_markdown(payload: Mapping[str, Any]) -> str:
    """Render triage dossiers as a human-facing Markdown review artifact."""

    summary = payload["summary"]
    lines = [
        "# Image-Level Triage Dossiers",
        "",
        "## Summary",
        "",
        f"- Images inspected: {summary['image_count']}",
        f"- No Findings Emitted: {summary['no_findings_emitted_count']}",
        f"- Needs Review: {summary['needs_review_count']}",
        f"- Priority Review: {summary['priority_review_count']}",
        "",
        "## Scope",
        "",
        "- Read-only, advisory, deterministic, and sidecar-based.",
        "- Execution, cleanup, export, source-image modification, and pixel modification are out of scope.",
        "",
        "## Analyzer Coverage",
        "",
    ]
    lines.extend(_coverage_lines(payload.get("analyzer_coverage", {})))
    lines.extend(["", "## Dossiers", ""])
    for dossier in payload.get("dossiers", []):
        lines.extend(_dossier_lines(dossier))
    return "\n".join(lines).rstrip() + "\n"


def _dossier(
    recommendation: Mapping[str, Any],
    findings: list[Finding],
    review_statuses: Mapping[str, Any] | None,
) -> dict[str, Any]:
    image_path = str(recommendation.get("image_path", ""))
    review_status, review_decision = _review_status_text(image_path, review_statuses)
    finding_payloads = [_finding_payload(finding) for finding in findings]
    return {
        "image_path": image_path,
        "filename": Path(image_path).name or image_path,
        "recommendation": recommendation.get("recommendation", ""),
        "display_label": recommendation.get("display_label", ""),
        "primary_reason": recommendation.get("primary_reason", ""),
        "reason_codes": list(recommendation.get("reason_codes", [])),
        "review_status": review_status,
        "review_decision": review_decision,
        "suggested_human_action": recommendation.get("guidance", ""),
        "confidence_note": recommendation.get("confidence_note", ""),
        "no_finding_semantics": (
            "No Findings Emitted means no current deterministic analyzer emitted "
            "a review finding for this image. It is not proof that the image is "
            "artifact-free, caption-ready, or guaranteed suitable for LoRA training."
        ),
        "findings": finding_payloads,
    }


def _finding_payload(finding: Finding) -> dict[str, Any]:
    return {
        "analyzer": finding.analyzer,
        "category": finding.category,
        "severity": finding.severity.name,
        "confidence": finding.confidence,
        "false_positive_rate": finding.false_positive_rate,
        "benchmark_version": finding.benchmark_version,
        "evidence": dict(finding.evidence),
        "explanation": finding.explanation,
        "human_review_note": finding.recommendation,
    }


def _coverage_lines(coverage: Mapping[str, Any]) -> list[str]:
    analyzers = coverage.get("analyzers", [])
    if not analyzers:
        return ["- No analyzer coverage was recorded."]
    lines: list[str] = []
    for item in analyzers:
        categories = ", ".join(str(v) for v in item.get("categories", [])) or "none"
        lines.append(
            f"- {item.get('analyzer', '')}/{item.get('version', '')}: "
            f"{item.get('finding_count', 0)} findings on "
            f"{item.get('image_count', 0)} images; categories: {categories}; "
            f"calibration: {item.get('calibration_status', 'unknown')}"
        )
    uncovered = coverage.get("currently_uncovered", [])
    if uncovered:
        lines.append(
            "- Currently uncovered artifact families: "
            + ", ".join(str(item) for item in uncovered)
        )
    return lines


def _dossier_lines(dossier: Mapping[str, Any]) -> list[str]:
    lines = [
        f"### {dossier.get('filename') or dossier.get('image_path')}",
        "",
        f"- Recommendation: {dossier.get('display_label', '')}",
        f"- Primary reason: {dossier.get('primary_reason', '')}",
        f"- Review status: {dossier.get('review_status', '')}",
        f"- Decision: {dossier.get('review_decision', '')}",
        f"- Suggested human action: {dossier.get('suggested_human_action', '')}",
        "",
        "Findings:",
    ]
    findings = dossier.get("findings", [])
    if findings:
        for finding in findings:
            lines.extend([
                (
                    f"- {finding.get('category', '')} / "
                    f"{finding.get('analyzer', '')} / "
                    f"{finding.get('severity', '')}"
                ),
                f"  - Evidence: {_evidence_summary(finding.get('evidence', {}))}",
                f"  - Why: {finding.get('explanation', '')}",
                f"  - Human review note: {finding.get('human_review_note', '')}",
            ])
    else:
        lines.append("- none")
        lines.append(f"- {dossier.get('no_finding_semantics', '')}")
    lines.append("")
    return lines


def _evidence_summary(evidence: object) -> str:
    if not isinstance(evidence, Mapping):
        return "none"
    parts = [
        f"{key}={value}"
        for key, value in evidence.items()
        if key != "calibrated" and not isinstance(value, dict | list)
    ]
    return ", ".join(parts) if parts else "none"


def _review_status_text(
    image_path: str,
    review_statuses: Mapping[str, Any] | None,
) -> tuple[str, str]:
    if review_statuses is None:
        return ("Pending Review", "None recorded")
    status = review_statuses.get(image_path)
    if status is None:
        return ("Pending Review", "None recorded")
    status_text = str(getattr(status, "status", "Pending Review"))
    decisions = tuple(getattr(status, "decisions", ()))
    if not decisions:
        return (status_text, "None recorded")
    return (status_text, "; ".join(str(decision) for decision in decisions))


def _now_utc() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


__all__ = [
    "TRIAGE_DOSSIER_JSON",
    "TRIAGE_DOSSIER_MARKDOWN",
    "TRIAGE_DOSSIER_SCHEMA",
    "TRIAGE_POLICY_SEMANTICS",
    "build_triage_dossiers",
    "render_triage_dossiers_markdown",
    "write_triage_dossier_files",
]
