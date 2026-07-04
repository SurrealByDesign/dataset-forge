"""Internal validation dossier helpers for analyzer reliability review.

This module composes existing inspection reports, calibration labels, and
optional review decisions. It does not run analyzers, change thresholds, modify
images, or plan cleanup/repair/export work.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dataset_forge.calibration_evidence import (
    CalibrationEvidence,
    CalibrationLabels,
    ConfusionMetrics,
    evaluate_calibration,
    load_calibration_labels,
)
from dataset_forge.review_decisions import (
    REVIEW_DECISIONS_SCHEMA,
    ReviewDecisionSet,
    ReviewDecisionValue,
    load_review_decisions,
)

VALIDATION_DOSSIER_SCHEMA = "dataset-forge/validation-dossier/v1"

MIN_EVALUATED_IMAGES_FOR_REPAIR_PLANNING = 10
MIN_POSITIVE_LABELS_FOR_REPAIR_PLANNING = 3
MIN_NEGATIVE_LABELS_FOR_REPAIR_PLANNING = 3
MIN_PRECISION_FOR_REPAIR_PLANNING = 0.95
MIN_RECALL_FOR_REPAIR_PLANNING = 0.90
MAX_FALSE_POSITIVE_RATE_FOR_REPAIR_PLANNING = 0.05

READINESS_READY = "ready"
READINESS_INSUFFICIENT_EVIDENCE = "insufficient_evidence"
READINESS_FALSE_POSITIVES = "not_ready_due_to_false_positives"
READINESS_FALSE_NEGATIVES = "not_ready_due_to_false_negatives"
READINESS_REVIEW_DISAGREEMENT = "not_ready_due_to_review_disagreement"


@dataclass(frozen=True)
class CategoryValidationSummary:
    category: str
    analyzer: str
    metrics: ConfusionMetrics
    evaluated_image_count: int
    positive_label_count: int
    negative_label_count: int
    confirmed_artifact_count: int
    false_positive_review_decision_count: int
    false_positive_examples: list[dict[str, Any]]
    false_negative_examples: list[dict[str, Any]]
    ready_for_repair_planning: bool
    readiness_status: str
    readiness_explanation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "analyzer": self.analyzer,
            "metrics": self.metrics.to_dict(),
            "evaluated_image_count": self.evaluated_image_count,
            "positive_label_count": self.positive_label_count,
            "negative_label_count": self.negative_label_count,
            "confirmed_artifact_count": self.confirmed_artifact_count,
            "false_positive_review_decision_count": self.false_positive_review_decision_count,
            "false_positive_examples": list(self.false_positive_examples),
            "false_negative_examples": list(self.false_negative_examples),
            "ready_for_repair_planning": self.ready_for_repair_planning,
            "readiness_status": self.readiness_status,
            "readiness_explanation": self.readiness_explanation,
        }


@dataclass(frozen=True)
class AnalyzerValidationSummary:
    analyzer: str
    metrics: ConfusionMetrics
    categories: list[str]
    confirmed_artifact_count: int
    false_positive_review_decision_count: int
    ready_category_count: int
    not_ready_category_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "analyzer": self.analyzer,
            "metrics": self.metrics.to_dict(),
            "categories": list(self.categories),
            "confirmed_artifact_count": self.confirmed_artifact_count,
            "false_positive_review_decision_count": self.false_positive_review_decision_count,
            "ready_category_count": self.ready_category_count,
            "not_ready_category_count": self.not_ready_category_count,
        }


@dataclass(frozen=True)
class ValidationDossier:
    schema: str
    report_schema: str
    label_schema: str
    review_decision_schema: str | None
    evaluated_image_count: int
    readiness_policy: dict[str, Any]
    analyzer_summaries: dict[str, AnalyzerValidationSummary]
    category_summaries: dict[str, CategoryValidationSummary]
    false_positive_examples: list[dict[str, Any]]
    false_negative_examples: list[dict[str, Any]]
    threshold_review_candidates: list[dict[str, Any]]
    review_decision_summary: dict[str, Any] | None
    calibration_evidence: CalibrationEvidence

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "report_schema": self.report_schema,
            "label_schema": self.label_schema,
            "review_decision_schema": self.review_decision_schema,
            "evaluated_image_count": self.evaluated_image_count,
            "readiness_policy": dict(self.readiness_policy),
            "analyzer_summaries": {
                analyzer: summary.to_dict()
                for analyzer, summary in self.analyzer_summaries.items()
            },
            "category_summaries": {
                category: summary.to_dict()
                for category, summary in self.category_summaries.items()
            },
            "false_positive_examples": list(self.false_positive_examples),
            "false_negative_examples": list(self.false_negative_examples),
            "threshold_review_candidates": list(self.threshold_review_candidates),
            "review_decision_summary": self.review_decision_summary,
            "calibration_evidence": self.calibration_evidence.to_dict(),
        }


def build_validation_dossier(
    inspection_report: dict[str, Any],
    labels: CalibrationLabels,
    review_decisions: ReviewDecisionSet | None = None,
) -> ValidationDossier:
    """Build a deterministic validation dossier from existing evidence."""
    evidence = evaluate_calibration(inspection_report, labels)
    predictions_by_image = _predictions_by_image(inspection_report)
    findings_by_scope = _findings_by_scope(inspection_report)
    confirmed_counts, false_positive_review_counts = _review_counts_by_category(review_decisions)

    category_summaries: dict[str, CategoryValidationSummary] = {}
    for category, analyzer in sorted(evidence.category_to_analyzer.items()):
        positive_count = sum(
            1 for truth in labels.labels_by_image.values()
            if category in truth
        )
        negative_count = labels.image_count - positive_count
        fp_examples = _false_positive_examples(
            category,
            labels,
            findings_by_scope,
        )
        fn_examples = _false_negative_examples(
            category,
            analyzer,
            labels,
            predictions_by_image,
            review_decisions,
        )
        metrics = evidence.category_results[category]
        readiness_status, readiness_explanation = _readiness_status(
            metrics=metrics,
            evaluated_image_count=labels.image_count,
            positive_label_count=positive_count,
            negative_label_count=negative_count,
            false_positive_review_decision_count=false_positive_review_counts.get(category, 0),
        )
        category_summaries[category] = CategoryValidationSummary(
            category=category,
            analyzer=analyzer,
            metrics=metrics,
            evaluated_image_count=labels.image_count,
            positive_label_count=positive_count,
            negative_label_count=negative_count,
            confirmed_artifact_count=confirmed_counts.get(category, 0),
            false_positive_review_decision_count=false_positive_review_counts.get(category, 0),
            false_positive_examples=fp_examples,
            false_negative_examples=fn_examples,
            ready_for_repair_planning=readiness_status == READINESS_READY,
            readiness_status=readiness_status,
            readiness_explanation=readiness_explanation,
        )

    analyzer_summaries = _analyzer_summaries(
        evidence,
        category_summaries,
        confirmed_counts,
        false_positive_review_counts,
    )
    false_positive_examples = [
        example
        for summary in category_summaries.values()
        for example in summary.false_positive_examples
    ]
    false_negative_examples = [
        example
        for summary in category_summaries.values()
        for example in summary.false_negative_examples
    ]
    threshold_review_candidates = _threshold_review_candidates(category_summaries)

    return ValidationDossier(
        schema=VALIDATION_DOSSIER_SCHEMA,
        report_schema=evidence.report_schema,
        label_schema=evidence.label_schema,
        review_decision_schema=(
            REVIEW_DECISIONS_SCHEMA if review_decisions is not None else None
        ),
        evaluated_image_count=labels.image_count,
        readiness_policy=_readiness_policy(),
        analyzer_summaries=analyzer_summaries,
        category_summaries=category_summaries,
        false_positive_examples=sorted(false_positive_examples, key=_example_sort_key),
        false_negative_examples=sorted(false_negative_examples, key=_example_sort_key),
        threshold_review_candidates=threshold_review_candidates,
        review_decision_summary=(
            review_decisions.summary().to_dict()
            if review_decisions is not None
            else None
        ),
        calibration_evidence=evidence,
    )


def build_validation_dossier_files(
    inspection_report_path: Path,
    labels_path: Path,
    review_decisions_path: Path | None = None,
) -> ValidationDossier:
    """Load report, labels, optional decisions, then build a dossier."""
    report = json.loads(inspection_report_path.read_text(encoding="utf-8"))
    labels = load_calibration_labels(labels_path)
    decisions = (
        load_review_decisions(review_decisions_path)
        if review_decisions_path is not None
        else None
    )
    return build_validation_dossier(report, labels, decisions)


def write_validation_dossier_json(
    dossier: ValidationDossier,
    output_path: Path,
) -> None:
    """Write validation dossier JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(dossier.to_dict(), indent=2) + "\n",
        encoding="utf-8",
    )


def _analyzer_summaries(
    evidence: CalibrationEvidence,
    category_summaries: dict[str, CategoryValidationSummary],
    confirmed_counts: dict[str, int],
    false_positive_review_counts: dict[str, int],
) -> dict[str, AnalyzerValidationSummary]:
    grouped: dict[str, list[str]] = {}
    for category, analyzer in evidence.category_to_analyzer.items():
        grouped.setdefault(analyzer, []).append(category)

    summaries: dict[str, AnalyzerValidationSummary] = {}
    for analyzer, categories in sorted(grouped.items()):
        categories = sorted(categories)
        ready_count = sum(
            1 for category in categories
            if category_summaries[category].ready_for_repair_planning
        )
        summaries[analyzer] = AnalyzerValidationSummary(
            analyzer=analyzer,
            metrics=evidence.analyzer_results[analyzer],
            categories=categories,
            confirmed_artifact_count=sum(confirmed_counts.get(category, 0) for category in categories),
            false_positive_review_decision_count=sum(
                false_positive_review_counts.get(category, 0)
                for category in categories
            ),
            ready_category_count=ready_count,
            not_ready_category_count=len(categories) - ready_count,
        )
    return summaries


def _readiness_status(
    *,
    metrics: ConfusionMetrics,
    evaluated_image_count: int,
    positive_label_count: int,
    negative_label_count: int,
    false_positive_review_decision_count: int,
) -> tuple[str, str]:
    if (
        evaluated_image_count < MIN_EVALUATED_IMAGES_FOR_REPAIR_PLANNING
        or positive_label_count < MIN_POSITIVE_LABELS_FOR_REPAIR_PLANNING
        or negative_label_count < MIN_NEGATIVE_LABELS_FOR_REPAIR_PLANNING
    ):
        return (
            READINESS_INSUFFICIENT_EVIDENCE,
            "Not enough labeled positive and negative examples for repair-planning readiness.",
        )
    if false_positive_review_decision_count > 0:
        return (
            READINESS_REVIEW_DISAGREEMENT,
            "Human review marked one or more category findings as false positives.",
        )
    if (
        metrics.fp > 0
        or metrics.precision < MIN_PRECISION_FOR_REPAIR_PLANNING
        or metrics.false_positive_rate > MAX_FALSE_POSITIVE_RATE_FOR_REPAIR_PLANNING
    ):
        return (
            READINESS_FALSE_POSITIVES,
            "False-positive evidence is too high for repair-planning readiness.",
        )
    if metrics.fn > 0 or metrics.recall < MIN_RECALL_FOR_REPAIR_PLANNING:
        return (
            READINESS_FALSE_NEGATIVES,
            "False-negative evidence is too high for repair-planning readiness.",
        )
    return (
        READINESS_READY,
        "Category meets conservative validation thresholds for future repair-planning consideration.",
    )


def _threshold_review_candidates(
    category_summaries: dict[str, CategoryValidationSummary],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    candidate_statuses = {
        READINESS_FALSE_POSITIVES,
        READINESS_FALSE_NEGATIVES,
        READINESS_REVIEW_DISAGREEMENT,
    }
    for category, summary in sorted(category_summaries.items()):
        if summary.readiness_status not in candidate_statuses:
            continue
        candidates.append({
            "category": category,
            "analyzer": summary.analyzer,
            "readiness_status": summary.readiness_status,
            "precision": summary.metrics.precision,
            "recall": summary.metrics.recall,
            "false_positive_rate": summary.metrics.false_positive_rate,
            "false_positive_example_count": len(summary.false_positive_examples),
            "false_negative_example_count": len(summary.false_negative_examples),
            "false_positive_review_decision_count": summary.false_positive_review_decision_count,
            "recommended_action": (
                "Review analyzer thresholds, guards, and evidence examples. "
                "Do not change thresholds automatically."
            ),
        })
    return candidates


def _false_positive_examples(
    category: str,
    labels: CalibrationLabels,
    findings_by_scope: dict[tuple[str, str], list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    examples: list[dict[str, Any]] = []
    for image_path, truth in sorted(labels.labels_by_image.items()):
        if category in truth:
            continue
        for finding in findings_by_scope.get((image_path, category), []):
            examples.append(_example_from_finding(finding, "false_positive"))
    return sorted(examples, key=_example_sort_key)


def _false_negative_examples(
    category: str,
    analyzer: str,
    labels: CalibrationLabels,
    predictions_by_image: dict[str, frozenset[str]],
    review_decisions: ReviewDecisionSet | None,
) -> list[dict[str, Any]]:
    examples: list[dict[str, Any]] = []
    for image_path, truth in sorted(labels.labels_by_image.items()):
        if category not in truth:
            continue
        if category in predictions_by_image.get(image_path, frozenset()):
            continue
        example = {
            "image_path": image_path,
            "category": category,
            "analyzer": analyzer,
            "example_type": "false_negative",
        }
        if review_decisions is not None:
            decision = review_decisions.decision_for(image_path, category)
            if decision is not None:
                example["review_decision"] = decision.decision
        examples.append(example)
    return sorted(examples, key=_example_sort_key)


def _example_from_finding(
    finding: dict[str, Any],
    example_type: str,
) -> dict[str, Any]:
    return {
        "image_path": _normalize_path(finding.get("image_path")),
        "category": str(finding.get("category", "")),
        "analyzer": str(finding.get("analyzer", "")),
        "severity": str(finding.get("severity", "")),
        "confidence": finding.get("confidence"),
        "example_type": example_type,
    }


def _predictions_by_image(report: dict[str, Any]) -> dict[str, frozenset[str]]:
    grouped: dict[str, set[str]] = {}
    for finding in report.get("findings", []):
        if not isinstance(finding, dict):
            continue
        category = str(finding.get("category", ""))
        if _is_error_category(category):
            continue
        image_path = _normalize_path(finding.get("image_path"))
        grouped.setdefault(image_path, set()).add(category)
    return {
        image_path: frozenset(categories)
        for image_path, categories in sorted(grouped.items())
    }


def _findings_by_scope(report: dict[str, Any]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for finding in report.get("findings", []):
        if not isinstance(finding, dict):
            continue
        category = str(finding.get("category", ""))
        if _is_error_category(category):
            continue
        image_path = _normalize_path(finding.get("image_path"))
        grouped.setdefault((image_path, category), []).append(finding)
    return {
        key: sorted(items, key=lambda item: (
            str(item.get("analyzer", "")),
            str(item.get("severity", "")),
        ))
        for key, items in sorted(grouped.items())
    }


def _review_counts_by_category(
    review_decisions: ReviewDecisionSet | None,
) -> tuple[dict[str, int], dict[str, int]]:
    confirmed: dict[str, int] = {}
    false_positive: dict[str, int] = {}
    if review_decisions is None:
        return confirmed, false_positive

    for decision in review_decisions.decisions:
        if decision.category is None:
            continue
        if decision.decision == ReviewDecisionValue.CONFIRMED_ARTIFACT.value:
            confirmed[decision.category] = confirmed.get(decision.category, 0) + 1
        elif decision.decision == ReviewDecisionValue.FALSE_POSITIVE.value:
            false_positive[decision.category] = false_positive.get(decision.category, 0) + 1
    return dict(sorted(confirmed.items())), dict(sorted(false_positive.items()))


def _readiness_policy() -> dict[str, Any]:
    return {
        "minimum_evaluated_images": MIN_EVALUATED_IMAGES_FOR_REPAIR_PLANNING,
        "minimum_positive_labels_per_category": MIN_POSITIVE_LABELS_FOR_REPAIR_PLANNING,
        "minimum_negative_labels_per_category": MIN_NEGATIVE_LABELS_FOR_REPAIR_PLANNING,
        "minimum_precision": MIN_PRECISION_FOR_REPAIR_PLANNING,
        "minimum_recall": MIN_RECALL_FOR_REPAIR_PLANNING,
        "maximum_false_positive_rate": MAX_FALSE_POSITIVE_RATE_FOR_REPAIR_PLANNING,
        "requires_zero_false_positive_review_decisions": True,
    }


def _is_error_category(category: str) -> bool:
    return category.endswith(".error")


def _normalize_path(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("image_path must be a non-empty string")
    return value.replace("\\", "/")


def _example_sort_key(example: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(example.get("image_path", "")),
        str(example.get("category", "")),
        str(example.get("analyzer", "")),
        str(example.get("example_type", "")),
    )


__all__ = [
    "READINESS_FALSE_NEGATIVES",
    "READINESS_FALSE_POSITIVES",
    "READINESS_INSUFFICIENT_EVIDENCE",
    "READINESS_READY",
    "READINESS_REVIEW_DISAGREEMENT",
    "VALIDATION_DOSSIER_SCHEMA",
    "AnalyzerValidationSummary",
    "CategoryValidationSummary",
    "ValidationDossier",
    "build_validation_dossier",
    "build_validation_dossier_files",
    "write_validation_dossier_json",
]
