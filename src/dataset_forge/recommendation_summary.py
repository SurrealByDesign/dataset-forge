"""Deterministic recommendation summaries over existing inspection findings."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dataset_forge.context import DatasetContext
from dataset_forge.finding import Finding, Severity


RECOMMENDATION_SUMMARY_SCHEMA = "dataset-forge/recommendation-summary/v1"

READY_FOR_TRAINING = "READY_FOR_TRAINING"
NEEDS_REVIEW = "NEEDS_REVIEW"
PRIORITY_REVIEW = "PRIORITY_REVIEW"

DISPLAY_LABELS = {
    READY_FOR_TRAINING: "Ready for Training",
    NEEDS_REVIEW: "Needs Review",
    PRIORITY_REVIEW: "Priority Review",
}

CONFIDENCE_NOTE = (
    "Recommendations are advisory and based only on existing findings. "
    "Uncalibrated analyzers are review signals, not final judgments."
)

_ERROR_CATEGORIES = {
    "texture.error",
    "artifact.crystalline_faceting.error",
    "artifact.oversharpening_halo.error",
    "artifact.high_frequency_isolated.error",
}
_HIGH_SEVERITIES = {Severity.HIGH, Severity.CRITICAL}
_SEVERITY_SORT = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
    Severity.NONE: 4,
}
_RECOMMENDATION_GROUP_SORT = {
    PRIORITY_REVIEW: 0,
    NEEDS_REVIEW: 1,
    READY_FOR_TRAINING: 2,
}


@dataclass(frozen=True)
class FindingRef:
    analyzer: str
    category: str
    severity: str

    def to_dict(self) -> dict[str, str]:
        return {
            "analyzer": self.analyzer,
            "category": self.category,
            "severity": self.severity,
        }


@dataclass(frozen=True)
class ImageRecommendation:
    image_path: str
    recommendation: str
    display_label: str
    primary_reason: str
    reason_codes: tuple[str, ...]
    finding_refs: tuple[FindingRef, ...]
    guidance: str
    confidence_note: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "image_path": self.image_path,
            "recommendation": self.recommendation,
            "display_label": self.display_label,
            "primary_reason": self.primary_reason,
            "reason_codes": list(self.reason_codes),
            "finding_refs": [ref.to_dict() for ref in self.finding_refs],
            "guidance": self.guidance,
            "confidence_note": self.confidence_note,
        }


@dataclass(frozen=True)
class RecommendationSummary:
    schema: str
    source_report_schema: str
    image_count: int
    ready_for_training_count: int
    needs_review_count: int
    priority_review_count: int
    analyzer_error_count: int
    recommendations: tuple[ImageRecommendation, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "source_report_schema": self.source_report_schema,
            "summary": {
                "image_count": self.image_count,
                "ready_for_training_count": self.ready_for_training_count,
                "needs_review_count": self.needs_review_count,
                "priority_review_count": self.priority_review_count,
                "analyzer_error_count": self.analyzer_error_count,
            },
            "recommendations": [
                recommendation.to_dict()
                for recommendation in self.recommendations
            ],
        }


def build_recommendation_summary(
    findings: list[Finding],
    context: DatasetContext,
    *,
    source_report_schema: str = "dataset-forge/inspection/v1",
) -> RecommendationSummary:
    """Build advisory training-set recommendations from existing findings only."""

    findings_by_image = _group_findings_by_image(findings, context)
    recommendations = tuple(
        sorted(
            (
                _build_image_recommendation(path, list(image_findings))
                for path, image_findings in findings_by_image.items()
            ),
            key=_recommendation_sort_key,
        )
    )

    return RecommendationSummary(
        schema=RECOMMENDATION_SUMMARY_SCHEMA,
        source_report_schema=source_report_schema,
        image_count=context.image_count,
        ready_for_training_count=sum(
            1 for item in recommendations if item.recommendation == READY_FOR_TRAINING
        ),
        needs_review_count=sum(
            1 for item in recommendations if item.recommendation == NEEDS_REVIEW
        ),
        priority_review_count=sum(
            1 for item in recommendations if item.recommendation == PRIORITY_REVIEW
        ),
        analyzer_error_count=sum(1 for finding in findings if _is_analyzer_error(finding)),
        recommendations=recommendations,
    )


def _group_findings_by_image(
    findings: list[Finding],
    context: DatasetContext,
) -> dict[str, tuple[Finding, ...]]:
    groups: dict[str, list[Finding]] = {
        str(path): [] for path in context.image_paths
    }
    for finding in sorted(findings, key=_finding_sort_key):
        groups.setdefault(str(finding.image_path), []).append(finding)
    return {
        path: tuple(items)
        for path, items in sorted(groups.items())
    }


def _build_image_recommendation(
    path: str,
    findings: list[Finding],
) -> ImageRecommendation:
    if not findings:
        return _recommendation(
            path=path,
            recommendation=READY_FOR_TRAINING,
            reason="No findings were emitted for this image.",
            reason_codes=("no_findings",),
            findings=(),
            guidance=(
                "Dataset Forge found no current evidence that this image needs "
                "review before training."
            ),
        )

    if any(_is_analyzer_error(finding) for finding in findings):
        return _recommendation(
            path=path,
            recommendation=PRIORITY_REVIEW,
            reason="Dataset Forge could not inspect this image reliably.",
            reason_codes=("analyzer_error",),
            findings=tuple(findings),
            guidance="Review this image before deciding whether to include it in training.",
        )

    if any(finding.severity in _HIGH_SEVERITIES for finding in findings):
        return _recommendation(
            path=path,
            recommendation=PRIORITY_REVIEW,
            reason="High-severity finding detected.",
            reason_codes=("finding.high_severity",),
            findings=tuple(findings),
            guidance="Review this image early before deciding whether to include it in training.",
        )

    if len({finding.category for finding in findings}) >= 2:
        return _recommendation(
            path=path,
            recommendation=PRIORITY_REVIEW,
            reason="Multiple artifact families detected.",
            reason_codes=("finding.multiple_categories",),
            findings=tuple(findings),
            guidance="Review this image early before deciding whether to include it in training.",
        )

    return _recommendation(
        path=path,
        recommendation=NEEDS_REVIEW,
        reason="Measurable finding detected.",
        reason_codes=("finding.present",),
        findings=tuple(findings),
        guidance="Inspect this image before deciding whether to include it in training.",
    )


def _recommendation(
    *,
    path: str,
    recommendation: str,
    reason: str,
    reason_codes: tuple[str, ...],
    findings: tuple[Finding, ...],
    guidance: str,
) -> ImageRecommendation:
    return ImageRecommendation(
        image_path=path,
        recommendation=recommendation,
        display_label=DISPLAY_LABELS[recommendation],
        primary_reason=reason,
        reason_codes=reason_codes,
        finding_refs=tuple(
            FindingRef(
                analyzer=finding.analyzer,
                category=finding.category,
                severity=finding.severity.name,
            )
            for finding in sorted(findings, key=_finding_sort_key)
        ),
        guidance=guidance,
        confidence_note=CONFIDENCE_NOTE,
    )


def _is_analyzer_error(finding: Finding) -> bool:
    return finding.category in _ERROR_CATEGORIES or finding.category.endswith(".error")


def _finding_sort_key(finding: Finding) -> tuple[str, str, str]:
    return (str(finding.image_path), finding.analyzer, finding.category)


def _recommendation_sort_key(item: ImageRecommendation) -> tuple[int, int, int, str]:
    severities = [
        Severity[ref.severity]
        for ref in item.finding_refs
    ]
    strongest = min(
        (_SEVERITY_SORT[severity] for severity in severities),
        default=_SEVERITY_SORT[Severity.NONE],
    )
    analyzer_error_rank = 0 if "analyzer_error" in item.reason_codes else 1
    return (
        _RECOMMENDATION_GROUP_SORT[item.recommendation],
        analyzer_error_rank,
        strongest,
        Path(item.image_path).as_posix(),
    )


__all__ = [
    "CONFIDENCE_NOTE",
    "DISPLAY_LABELS",
    "NEEDS_REVIEW",
    "PRIORITY_REVIEW",
    "READY_FOR_TRAINING",
    "RECOMMENDATION_SUMMARY_SCHEMA",
    "FindingRef",
    "ImageRecommendation",
    "RecommendationSummary",
    "build_recommendation_summary",
]
