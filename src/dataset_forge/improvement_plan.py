"""Deterministic improvement planning from existing Dataset Forge sidecars."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

from dataset_forge import __version__
from dataset_forge.comparison import COMPARISON_SUMMARY_SCHEMA
from dataset_forge.recommendation_summary import (
    NEEDS_REVIEW,
    PRIORITY_REVIEW,
    READY_FOR_TRAINING,
    RECOMMENDATION_SUMMARY_SCHEMA,
)
from dataset_forge.report import REPORT_SCHEMA
from dataset_forge.review_decisions import (
    ReviewDecision,
    ReviewDecisionSet,
    ReviewDecisionValue,
    load_review_decisions,
)


IMPROVEMENT_PLAN_SCHEMA = "dataset-forge/improvement-plan/v1"

INSPECTION_REPORT_FILENAME = "inspection_report.json"
RECOMMENDATION_SUMMARY_FILENAME = "recommendation_summary.json"
REVIEW_DECISIONS_FILENAME = "review_decisions.json"
COMPARISON_SUMMARY_FILENAME = "comparison_summary.json"
IMPROVEMENT_PLAN_JSON_FILENAME = "improvement_plan.json"
IMPROVEMENT_PLAN_MARKDOWN_FILENAME = "improvement_plan.md"

_ELIGIBLE_RECOMMENDATIONS = {NEEDS_REVIEW, PRIORITY_REVIEW}
_SUPPRESSING_DECISIONS = {
    ReviewDecisionValue.FALSE_POSITIVE.value: "Human review marked this finding as a false positive.",
    ReviewDecisionValue.ACCEPTABLE_STYLE.value: "Human review marked this finding as acceptable style.",
    ReviewDecisionValue.IGNORE.value: "Human review chose to ignore this scope.",
}
_OPERATION_BY_CATEGORY = {
    "texture.high_microtexture": "High Microtexture Review",
    "artifact.texture": "Texture Consistency Review",
    "artifact.crystalline_faceting": "Crystalline Faceting Review",
    "artifact.oversharpening_halo": "Oversharpening Review",
    "artifact.high_frequency_isolated": "Isolated High-Frequency Artifact Review",
    "texture.error": "Texture Consistency Review",
    "artifact.crystalline_faceting.error": "Texture Consistency Review",
    "artifact.oversharpening_halo.error": "Edge Consistency Review",
    "artifact.high_frequency_isolated.error": "Noise Consistency Review",
}
_RECOMMENDATION_SORT = {
    PRIORITY_REVIEW: 0,
    NEEDS_REVIEW: 1,
    READY_FOR_TRAINING: 2,
}


class ImprovementPlanError(ValueError):
    """Raised when improvement planning inputs are missing or unsupported."""


def write_improvement_plan(
    inspect_output: Path,
    *,
    output_dir: Path | None = None,
) -> tuple[Path, Path]:
    """Build and write improvement_plan.json and improvement_plan.md."""

    root = inspect_output.expanduser().resolve()
    destination = output_dir.expanduser().resolve() if output_dir else root
    plan = build_improvement_plan(root)
    destination.mkdir(parents=True, exist_ok=True)
    json_path = destination / IMPROVEMENT_PLAN_JSON_FILENAME
    markdown_path = destination / IMPROVEMENT_PLAN_MARKDOWN_FILENAME
    json_path.write_text(
        json.dumps(plan, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(
        render_improvement_plan_markdown(plan),
        encoding="utf-8",
    )
    return json_path, markdown_path


def build_improvement_plan(
    inspect_output: Path,
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a deterministic improvement plan from existing sidecars only."""

    workspace = _load_workspace(inspect_output)
    timestamp = generated_at or datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    candidates: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []
    suppressed: list[dict[str, Any]] = []

    for recommendation in _sorted_recommendations(workspace["recommendation_summary"]):
        if recommendation.get("recommendation") not in _ELIGIBLE_RECOMMENDATIONS:
            continue
        finding_refs = _finding_refs(recommendation)
        if not finding_refs:
            continue
        for ref in finding_refs:
            item = _planning_item(recommendation, ref, workspace["review_decisions"])
            decision = item["review_decision"]
            if _is_locked(item, workspace["review_decisions"]):
                suppressed.append({
                    **item,
                    "status": "SUPPRESSED",
                    "planning_notes": "Human review locked this image. No Improvement Candidate is created.",
                })
            elif decision and decision["decision"] == ReviewDecisionValue.NEEDS_REVIEW.value:
                deferred.append({
                    **item,
                    "status": "DEFERRED",
                    "planning_notes": "Human review marked this scope as still needing review.",
                })
            elif decision and decision["decision"] in _SUPPRESSING_DECISIONS:
                suppressed.append({
                    **item,
                    "status": "SUPPRESSED",
                    "planning_notes": _SUPPRESSING_DECISIONS[decision["decision"]],
                })
            else:
                candidates.append({
                    **item,
                    "status": "PLANNING_ONLY",
                    "planning_notes": "Improvement Candidate only. Human approval is required before any future execution.",
                })

    return {
        "schema": IMPROVEMENT_PLAN_SCHEMA,
        "tool_version": __version__,
        "generated_at": timestamp,
        "inputs": _input_references(workspace),
        "summary": {
            "improvement_candidate_count": len(candidates),
            "deferred_improvement_candidate_count": len(deferred),
            "suppressed_improvement_candidate_count": len(suppressed),
            "suggested_improvement_count": len(_operation_counts(candidates)),
        },
        "improvement_candidates": candidates,
        "deferred_improvement_candidates": deferred,
        "suppressed_improvement_candidates": suppressed,
        "suggested_improvements": _operation_summary(candidates),
    }


def render_improvement_plan_markdown(plan: Mapping[str, Any]) -> str:
    """Render a plain Markdown improvement plan."""

    summary = plan["summary"]
    lines = [
        "# Improvement Plan",
        "",
        "## Improvement Planning Summary",
        "",
        f"- Tool version: {plan['tool_version']}",
        f"- Generated at: {plan['generated_at']}",
        f"- Improvement Candidates: {summary['improvement_candidate_count']}",
        f"- Deferred Improvement Candidates: {summary['deferred_improvement_candidate_count']}",
        f"- Suppressed Improvement Candidates: {summary['suppressed_improvement_candidate_count']}",
        f"- Suggested Improvements: {summary['suggested_improvement_count']}",
        "",
    ]
    lines.extend(_markdown_candidates("## Improvement Candidates", plan["improvement_candidates"]))
    lines.extend(_markdown_candidates("## Deferred Improvement Candidates", plan["deferred_improvement_candidates"]))
    lines.extend(_markdown_candidates("## Suppressed Improvement Candidates", plan["suppressed_improvement_candidates"]))
    lines.extend(["## Suggested Improvements", ""])
    if plan["suggested_improvements"]:
        for item in plan["suggested_improvements"]:
            lines.append(f"- {item['suggested_improvement']}: {item['count']}")
    else:
        lines.append("No suggested improvements.")
    lines.extend([
        "",
        "## Important Notes",
        "",
        "An Improvement Plan is a proposal, never an instruction.",
        "",
        "Suggested Improvements are abstract planning concepts only. Dataset Forge did not execute them.",
        "",
        "Human Approval Required before any future execution.",
        "",
        "Planning Only: source images, reports, recommendations, and review decisions were not modified.",
        "",
        "Dataset Forge reduces uncertainty. It does not automate judgment.",
        "",
    ])
    return "\n".join(lines).rstrip() + "\n"


def _load_workspace(inspect_output: Path) -> dict[str, Any]:
    root = inspect_output.expanduser().resolve()
    inspection_path = root / INSPECTION_REPORT_FILENAME
    recommendation_path = root / RECOMMENDATION_SUMMARY_FILENAME
    review_path = root / REVIEW_DECISIONS_FILENAME
    comparison_path = root / COMPARISON_SUMMARY_FILENAME

    if not inspection_path.is_file():
        raise ImprovementPlanError(
            f"Missing inspection report: {inspection_path}. "
            "Run 'dataset-forge inspect <dataset>' first and pass the inspect_output folder."
        )
    if not recommendation_path.is_file():
        raise ImprovementPlanError(
            f"Missing recommendation summary: {recommendation_path}. "
            "Run 'dataset-forge inspect <dataset>' first and pass the inspect_output folder."
        )

    inspection_report = _load_json_object(inspection_path, "inspection report")
    recommendation_summary = _load_json_object(recommendation_path, "recommendation summary")
    _validate_schema(inspection_report, REPORT_SCHEMA, "inspection report")
    _validate_schema(recommendation_summary, RECOMMENDATION_SUMMARY_SCHEMA, "recommendation summary")
    if recommendation_summary.get("source_report_schema") != REPORT_SCHEMA:
        raise ImprovementPlanError(
            "Unsupported recommendation source report schema "
            f"{recommendation_summary.get('source_report_schema')!r}; expected {REPORT_SCHEMA!r}"
        )

    comparison_summary = None
    if comparison_path.is_file():
        comparison_summary = _load_json_object(comparison_path, "comparison summary")
        _validate_schema(comparison_summary, COMPARISON_SUMMARY_SCHEMA, "comparison summary")

    return {
        "path": root,
        "inspection_report_path": inspection_path,
        "recommendation_summary_path": recommendation_path,
        "review_decisions_path": review_path,
        "comparison_summary_path": comparison_path,
        "inspection_report": inspection_report,
        "recommendation_summary": recommendation_summary,
        "review_decisions": load_review_decisions(review_path) if review_path.is_file() else None,
        "comparison_summary": comparison_summary,
    }


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ImprovementPlanError(f"Malformed JSON in {label}: {path}") from exc
    if not isinstance(payload, dict):
        raise ImprovementPlanError(f"{label} must be a JSON object: {path}")
    return payload


def _validate_schema(payload: Mapping[str, Any], expected: str, label: str) -> None:
    schema = payload.get("schema")
    if schema != expected:
        raise ImprovementPlanError(
            f"Unsupported {label} schema {schema!r}; expected {expected!r}"
        )


def _input_references(workspace: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "inspect_output": str(workspace["path"]),
        "inspection_report": str(workspace["inspection_report_path"]),
        "recommendation_summary": str(workspace["recommendation_summary_path"]),
        "review_decisions": (
            str(workspace["review_decisions_path"])
            if workspace["review_decisions_path"].is_file()
            else None
        ),
        "comparison_summary": (
            str(workspace["comparison_summary_path"])
            if workspace["comparison_summary_path"].is_file()
            else None
        ),
    }


def _sorted_recommendations(summary: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return sorted(
        summary.get("recommendations", []),
        key=lambda item: (
            _RECOMMENDATION_SORT.get(str(item.get("recommendation")), 99),
            str(item.get("image_path", "")),
            str(item.get("primary_reason", "")),
        ),
    )


def _finding_refs(recommendation: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    refs = recommendation.get("finding_refs", [])
    if not isinstance(refs, list):
        return []
    return sorted(
        [ref for ref in refs if isinstance(ref, dict)],
        key=lambda ref: (
            str(ref.get("category", "")),
            str(ref.get("analyzer", "")),
            str(ref.get("severity", "")),
        ),
    )


def _planning_item(
    recommendation: Mapping[str, Any],
    finding_ref: Mapping[str, Any],
    decisions: ReviewDecisionSet | None,
) -> dict[str, Any]:
    image_path = str(recommendation["image_path"])
    category = str(finding_ref.get("category", ""))
    analyzer = str(finding_ref.get("analyzer", ""))
    decision = (
        decisions.decision_for(image_path, category, analyzer)
        if decisions is not None
        else None
    )
    return {
        "image_path": image_path,
        "filename": Path(image_path).name,
        "recommendation": str(recommendation.get("display_label") or recommendation.get("recommendation")),
        "recommendation_code": str(recommendation.get("recommendation")),
        "primary_reason": str(recommendation.get("primary_reason", "")),
        "finding_references": [
            {
                "category": category,
                "analyzer": analyzer,
                "severity": str(finding_ref.get("severity", "")),
            }
        ],
        "review_decision": _decision_payload(decision),
        "suggested_improvement": _suggested_improvement(category),
    }


def _is_locked(item: Mapping[str, Any], decisions: ReviewDecisionSet | None) -> bool:
    if decisions is None:
        return False
    if decisions.is_image_locked(str(item["image_path"])):
        return True
    decision = item["review_decision"]
    return bool(decision and decision["decision"] == ReviewDecisionValue.LOCKED.value)


def _decision_payload(decision: ReviewDecision | None) -> dict[str, str | None] | None:
    if decision is None:
        return None
    return decision.to_dict()


def _suggested_improvement(category: str) -> str:
    return _OPERATION_BY_CATEGORY.get(category, "Noise Consistency Review")


def _operation_counts(candidates: list[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in candidates:
        operation = str(item["suggested_improvement"])
        counts[operation] = counts.get(operation, 0) + 1
    return dict(sorted(counts.items()))


def _operation_summary(candidates: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"suggested_improvement": operation, "count": count}
        for operation, count in _operation_counts(candidates).items()
    ]


def _markdown_candidates(title: str, candidates: list[Mapping[str, Any]]) -> list[str]:
    lines = [title, ""]
    if not candidates:
        lines.extend(["No entries.", ""])
        return lines
    for item in candidates:
        ref = item["finding_references"][0]
        decision = item["review_decision"]
        lines.extend([
            f"### {item['filename']}",
            "",
            f"- Recommendation: {item['recommendation']}",
            f"- Why it appears: {item['primary_reason']}",
            f"- Finding: {ref['category']} ({ref['severity']})",
            f"- Analyzer: {ref['analyzer']}",
            f"- Review decision: {decision['decision'] if decision else 'not provided'}",
            f"- Suggested Improvement: {item['suggested_improvement']}",
            f"- Status: {item['status']}",
            f"- Planning notes: {item['planning_notes']}",
            "",
        ])
    return lines
