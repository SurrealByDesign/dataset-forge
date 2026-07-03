"""Additive post-inspection aggregation, summary, and review queue helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dataset_forge.context import DatasetContext
from dataset_forge.finding import Finding, Severity

DATASET_SUMMARY_SCHEMA = "dataset-forge/dataset-summary/v1"
REVIEW_QUEUE_SCHEMA = "dataset-forge/review-queue/v1"

_SEVERITY_ORDER = (Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW)
_ERROR_CATEGORIES = {
    "texture.error",
    "artifact.crystalline_faceting.error",
    "artifact.oversharpening_halo.error",
    "artifact.high_frequency_isolated.error",
}


def _finding_sort_key(finding: Finding) -> tuple[str, str, str]:
    return (str(finding.image_path), finding.analyzer, finding.category)


def _is_analyzer_error(finding: Finding) -> bool:
    return finding.category in _ERROR_CATEGORIES or finding.category.endswith(".error")


def _artifact_family(finding: Finding) -> str:
    if _is_analyzer_error(finding):
        return f"{finding.analyzer}:error"
    return finding.category


def _is_calibrated(finding: Finding) -> bool:
    return bool(finding.evidence.get("calibrated", False))


@dataclass(frozen=True)
class Aggregation:
    """Internal deterministic aggregation over a finished inspect finding set."""

    findings_by_image: dict[str, tuple[Finding, ...]]
    findings_by_category: dict[str, int]
    findings_by_severity: dict[str, int]
    analyzer_error_count: int
    images_with_findings: int
    images_without_findings: int
    images_with_multiple_finding_families: int
    calibrated_finding_count: int
    uncalibrated_finding_count: int


@dataclass(frozen=True)
class DatasetSummary:
    schema: str
    image_count: int
    images_with_findings: int
    images_without_findings: int
    findings_by_category: dict[str, int]
    findings_by_severity: dict[str, int]
    analyzer_error_count: int
    calibrated_finding_count: int
    uncalibrated_finding_count: int
    dominant_artifact_families: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "image_count": self.image_count,
            "images_with_findings": self.images_with_findings,
            "images_without_findings": self.images_without_findings,
            "findings_by_category": dict(self.findings_by_category),
            "findings_by_severity": dict(self.findings_by_severity),
            "analyzer_error_count": self.analyzer_error_count,
            "calibrated_finding_count": self.calibrated_finding_count,
            "uncalibrated_finding_count": self.uncalibrated_finding_count,
            "dominant_artifact_families": list(self.dominant_artifact_families),
        }


@dataclass(frozen=True)
class ReviewQueueItem:
    image_path: str
    outcome: str
    priority: str
    finding_count: int
    artifact_family_count: int
    strongest_severity: str | None
    has_analyzer_error: bool
    drivers: list[dict[str, Any]]
    explanation: str
    recommended_action: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "image_path": self.image_path,
            "outcome": self.outcome,
            "priority": self.priority,
            "finding_count": self.finding_count,
            "artifact_family_count": self.artifact_family_count,
            "strongest_severity": self.strongest_severity,
            "has_analyzer_error": self.has_analyzer_error,
            "drivers": list(self.drivers),
            "explanation": self.explanation,
            "recommended_action": self.recommended_action,
        }


@dataclass(frozen=True)
class ReviewQueue:
    schema: str
    outcomes: dict[str, int]
    items: list[ReviewQueueItem]
    advisory_notice: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "outcomes": dict(self.outcomes),
            "items": [item.to_dict() for item in self.items],
            "advisory_notice": self.advisory_notice,
        }


def build_aggregation(context: DatasetContext, findings: list[Finding]) -> Aggregation:
    findings_by_image: dict[str, list[Finding]] = {
        str(path): [] for path in context.image_paths
    }
    findings_by_category: dict[str, int] = {}
    findings_by_severity: dict[str, int] = {severity.name: 0 for severity in _SEVERITY_ORDER}
    findings_by_severity["NONE"] = 0
    analyzer_error_count = 0
    calibrated_finding_count = 0
    uncalibrated_finding_count = 0

    for finding in sorted(findings, key=_finding_sort_key):
        path = str(finding.image_path)
        findings_by_image.setdefault(path, []).append(finding)
        findings_by_category[finding.category] = findings_by_category.get(finding.category, 0) + 1
        findings_by_severity[finding.severity.name] = (
            findings_by_severity.get(finding.severity.name, 0) + 1
        )
        if _is_analyzer_error(finding):
            analyzer_error_count += 1
        if _is_calibrated(finding):
            calibrated_finding_count += 1
        else:
            uncalibrated_finding_count += 1

    frozen_by_image = {
        path: tuple(items)
        for path, items in sorted(findings_by_image.items())
    }
    images_with_findings = sum(1 for items in frozen_by_image.values() if items)
    images_without_findings = max(0, context.image_count - images_with_findings)
    images_with_multiple_finding_families = sum(
        1
        for items in frozen_by_image.values()
        if len({_artifact_family(finding) for finding in items}) > 1
    )

    return Aggregation(
        findings_by_image=frozen_by_image,
        findings_by_category=dict(sorted(findings_by_category.items())),
        findings_by_severity=findings_by_severity,
        analyzer_error_count=analyzer_error_count,
        images_with_findings=images_with_findings,
        images_without_findings=images_without_findings,
        images_with_multiple_finding_families=images_with_multiple_finding_families,
        calibrated_finding_count=calibrated_finding_count,
        uncalibrated_finding_count=uncalibrated_finding_count,
    )


def build_dataset_summary(context: DatasetContext, aggregation: Aggregation) -> DatasetSummary:
    dominant = [
        category
        for category, _ in sorted(
            (
                (category, count)
                for category, count in aggregation.findings_by_category.items()
                if not category.endswith(".error")
            ),
            key=lambda item: (-item[1], item[0]),
        )
    ]
    return DatasetSummary(
        schema=DATASET_SUMMARY_SCHEMA,
        image_count=context.image_count,
        images_with_findings=aggregation.images_with_findings,
        images_without_findings=aggregation.images_without_findings,
        findings_by_category=aggregation.findings_by_category,
        findings_by_severity=aggregation.findings_by_severity,
        analyzer_error_count=aggregation.analyzer_error_count,
        calibrated_finding_count=aggregation.calibrated_finding_count,
        uncalibrated_finding_count=aggregation.uncalibrated_finding_count,
        dominant_artifact_families=dominant,
    )


def build_review_queue(context: DatasetContext, aggregation: Aggregation) -> ReviewQueue:
    items: list[ReviewQueueItem] = []
    outcomes = {
        "no_attention_needed": 0,
        "review_recommended": 0,
        "priority_review": 0,
    }
    for path in sorted(str(image_path) for image_path in context.image_paths):
        findings = list(aggregation.findings_by_image.get(path, ()))
        item = _build_review_queue_item(path, findings)
        outcomes[item.outcome] += 1
        items.append(item)

    return ReviewQueue(
        schema=REVIEW_QUEUE_SCHEMA,
        outcomes=outcomes,
        items=items,
        advisory_notice=(
            "Review Queue is advisory only. Dataset Forge does not delete, modify, "
            "repair, reject, regenerate, or export images."
        ),
    )


def _build_review_queue_item(path: str, findings: list[Finding]) -> ReviewQueueItem:
    if not findings:
        return ReviewQueueItem(
            image_path=path,
            outcome="no_attention_needed",
            priority="none",
            finding_count=0,
            artifact_family_count=0,
            strongest_severity=None,
            has_analyzer_error=False,
            drivers=[],
            explanation="No findings were emitted for this image.",
            recommended_action="No attention needed from Dataset Forge findings.",
        )

    has_error = any(_is_analyzer_error(finding) for finding in findings)
    families = {_artifact_family(finding) for finding in findings}
    strongest = max((finding.severity for finding in findings), default=Severity.NONE)

    if has_error or len(families) > 1:
        outcome = "priority_review"
        priority = "high"
        explanation = (
            "This image should be reviewed early because it has analyzer errors "
            "or findings across multiple artifact families."
        )
    elif strongest >= Severity.MEDIUM:
        outcome = "review_recommended"
        priority = "medium"
        explanation = "This image has a medium-or-higher finding and deserves review."
    else:
        outcome = "review_recommended"
        priority = "low"
        explanation = "This image has a low-severity finding and deserves light review."

    return ReviewQueueItem(
        image_path=path,
        outcome=outcome,
        priority=priority,
        finding_count=len(findings),
        artifact_family_count=len(families),
        strongest_severity=strongest.name,
        has_analyzer_error=has_error,
        drivers=[
            {
                "category": finding.category,
                "analyzer": finding.analyzer,
                "severity": finding.severity.name,
                "confidence": finding.confidence,
            }
            for finding in sorted(findings, key=_finding_sort_key)
        ],
        explanation=explanation,
        recommended_action=(
            "Review manually before taking any action. Do not delete, modify, "
            "repair, reject, regenerate, or export automatically."
        ),
    )


def build_post_inspection_sections(
    findings: list[Finding],
    context: DatasetContext,
) -> tuple[DatasetSummary, ReviewQueue]:
    aggregation = build_aggregation(context, findings)
    return (
        build_dataset_summary(context, aggregation),
        build_review_queue(context, aggregation),
    )


__all__ = [
    "DATASET_SUMMARY_SCHEMA",
    "REVIEW_QUEUE_SCHEMA",
    "Aggregation",
    "DatasetSummary",
    "ReviewQueue",
    "ReviewQueueItem",
    "build_aggregation",
    "build_dataset_summary",
    "build_post_inspection_sections",
    "build_review_queue",
]
