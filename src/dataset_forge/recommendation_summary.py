"""Deterministic recommendation summaries over existing inspection findings."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping

from dataset_forge.context import DatasetContext
from dataset_forge.finding import Finding, Severity


RECOMMENDATION_SUMMARY_SCHEMA = "dataset-forge/recommendation-summary/v1"

READY_FOR_TRAINING = "READY_FOR_TRAINING"
NEEDS_REVIEW = "NEEDS_REVIEW"
PRIORITY_REVIEW = "PRIORITY_REVIEW"

DISPLAY_LABELS = {
    READY_FOR_TRAINING: "No Findings Emitted",
    NEEDS_REVIEW: "Needs Review",
    PRIORITY_REVIEW: "Priority Review",
}

CONFIDENCE_NOTE = (
    "Recommendations are advisory and based only on existing findings. "
    "Uncalibrated analyzers are review signals, not final judgments. "
    "No finding means no current analyzer emitted a review signal; it is not "
    "a guarantee that the image is artifact-free or training-ready."
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
class FindingEvidence:
    analyzer: str
    category: str
    severity: str
    confidence: float
    false_positive_rate: float
    benchmark_version: str
    evidence: dict[str, Any]
    explanation: str
    recommendation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "analyzer": self.analyzer,
            "category": self.category,
            "severity": self.severity,
            "confidence": self.confidence,
            "false_positive_rate": self.false_positive_rate,
            "benchmark_version": self.benchmark_version,
            "evidence": dict(self.evidence),
            "explanation": self.explanation,
            "recommendation": self.recommendation,
        }


@dataclass(frozen=True)
class ImageRecommendation:
    image_path: str
    recommendation: str
    display_label: str
    primary_reason: str
    reason_codes: tuple[str, ...]
    finding_refs: tuple[FindingRef, ...]
    findings: tuple[FindingEvidence, ...]
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
            "findings": [finding.to_dict() for finding in self.findings],
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
    analyzer_coverage: dict[str, Any]
    recommendations: tuple[ImageRecommendation, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "source_report_schema": self.source_report_schema,
            "summary": {
                "image_count": self.image_count,
                "no_findings_emitted_count": self.ready_for_training_count,
                "ready_for_training_count": self.ready_for_training_count,
                "needs_review_count": self.needs_review_count,
                "priority_review_count": self.priority_review_count,
                "analyzer_error_count": self.analyzer_error_count,
            },
            "analyzer_coverage": self.analyzer_coverage,
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
        analyzer_coverage=_analyzer_coverage(findings, context),
        recommendations=recommendations,
    )


def build_recommendation_summary_from_report(
    report: Mapping[str, Any],
) -> RecommendationSummary:
    """Rebuild Recommendation Summary from inspection_report.json content."""

    review_queue = report.get("review_queue", {})
    image_paths = [
        Path(str(item["image_path"]))
        for item in review_queue.get("items", [])
        if "image_path" in item
    ]
    findings = [_finding_from_report(item) for item in report.get("findings", [])]
    for finding in findings:
        if finding.image_path not in image_paths:
            image_paths.append(finding.image_path)

    context = replace(
        DatasetContext.empty(image_paths=image_paths),
        analyzer_versions=_analyzer_versions_from_findings(findings),
    )
    return build_recommendation_summary(
        findings,
        context,
        source_report_schema=str(report.get("schema", "dataset-forge/inspection/v1")),
    )


def write_recommendation_summary_files(
    summary: RecommendationSummary,
    output_dir: Path,
    *,
    review_statuses: Mapping[str, Any] | None = None,
) -> tuple[Path, Path]:
    """Write recommendation_summary.json and recommendation_summary.md."""

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "recommendation_summary.json"
    md_path = output_dir / "recommendation_summary.md"
    json_path.write_text(
        json.dumps(summary.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    md_path.write_text(
        render_recommendation_summary_markdown(
            summary,
            review_statuses=review_statuses,
        ),
        encoding="utf-8",
    )
    return json_path, md_path


def render_recommendation_summary_markdown(
    summary: RecommendationSummary,
    *,
    review_statuses: Mapping[str, Any] | None = None,
) -> str:
    """Render a plain Markdown review-priority summary."""

    lines = [
        "# Dataset Recommendation Summary",
        "",
        "## Dataset Summary",
        "",
        f"- Images inspected: {summary.image_count}",
        f"- No Findings Emitted: {summary.ready_for_training_count}",
        f"- Needs Review: {summary.needs_review_count}",
        f"- Priority Review: {summary.priority_review_count}",
        "- Most common finding categories:",
    ]
    lines.extend(_markdown_common_categories(summary))
    lines.extend([
        "",
        "## Analyzer Coverage",
        "",
    ])
    lines.extend(_markdown_analyzer_coverage(summary))
    lines.extend([
        "",
        "# Recommended Review Order",
        "",
    ])
    lines.extend(_markdown_review_group(summary, PRIORITY_REVIEW, review_statuses))
    lines.extend(_markdown_review_group(summary, NEEDS_REVIEW, review_statuses))
    lines.extend([
        "# No Findings Emitted",
        "",
        (
            f"{summary.ready_for_training_count} "
            f"{_image_word(summary.ready_for_training_count)} emitted no current "
            "findings requiring review."
        ),
        "",
        "# Important Notes",
        "",
        (
            "No Findings Emitted means Dataset Forge emitted no current "
            "findings requiring review."
        ),
        "",
        "Recommendations are based only on current deterministic findings.",
        "",
        (
            "It does not guarantee the image is artifact-free, caption-ready, "
            "or suitable for LoRA training."
        ),
        "",
        "Recommendations are advisory.",
        "",
        "Dataset Forge never modifies source images.",
        "",
        (
            "Dataset Forge does not execute cleanup, export datasets, or modify "
            "pixels in this workflow."
        ),
        "",
        "# Next Step",
        "",
        "Review Priority Review images first.",
        "",
        "Then review Needs Review images if appropriate.",
        "",
        (
            "After review, decide whether each image belongs in your training "
            "dataset."
        ),
        "",
    ])
    return "\n".join(lines).rstrip() + "\n"


def _markdown_review_group(
    summary: RecommendationSummary,
    recommendation: str,
    review_statuses: Mapping[str, Any] | None,
) -> list[str]:
    items = [
        item for item in summary.recommendations
        if item.recommendation == recommendation
    ]
    lines = [f"## {DISPLAY_LABELS[recommendation]}", ""]
    if not items:
        lines.extend(["No images in this group.", ""])
        return lines

    for family, family_items in _group_by_artifact_family(items):
        lines.extend([f"### {family}", ""])
        for item in family_items:
            lines.extend(_markdown_explanation_item(item, review_statuses))
        lines.append("")
    lines.append("")
    return lines


def _markdown_common_categories(summary: RecommendationSummary) -> list[str]:
    counts = _category_counts(summary)
    if not counts:
        return ["  - none"]
    return [
        f"  - {category}: {count}"
        for category, count in counts[:5]
    ]


def _markdown_analyzer_coverage(summary: RecommendationSummary) -> list[str]:
    analyzers = summary.analyzer_coverage.get("analyzers", [])
    if not analyzers:
        return ["- No analyzers were registered for this run."]
    lines: list[str] = []
    for item in analyzers:
        name = str(item.get("analyzer", ""))
        version = str(item.get("version", ""))
        finding_count = int(item.get("finding_count", 0))
        image_count = int(item.get("image_count", 0))
        calibration = str(item.get("calibration_status", "unknown"))
        categories = ", ".join(str(v) for v in item.get("categories", [])) or "none"
        lines.append(
            f"- {name}/{version}: {finding_count} findings on "
            f"{image_count} images; calibration: {calibration}; "
            f"categories: {categories}"
        )
    uncovered = summary.analyzer_coverage.get("currently_uncovered", [])
    if uncovered:
        lines.append(
            "- Currently uncovered artifact families: "
            + ", ".join(str(item) for item in uncovered)
        )
    return lines


def _markdown_explanation_item(
    item: ImageRecommendation,
    review_statuses: Mapping[str, Any] | None,
) -> list[str]:
    categories = _ref_values(item, "category")
    analyzers = _ref_values(item, "analyzer")
    severities = _ref_values(item, "severity")
    review_status, review_decision = _review_status_text(item.image_path, review_statuses)
    lines = [
        "---",
        "",
        f"#### {Path(item.image_path).name}",
        "",
        "Recommendation:",
        f"{item.display_label}",
        "",
        "Review Status:",
        review_status,
        "",
        "Decision:",
        review_decision,
        "",
        "Primary reason:",
        f"{item.primary_reason}",
        "",
        "Finding categories:",
    ]
    lines.extend(f"- {category}" for category in categories)
    lines.extend([
        "",
        "Analyzer:",
    ])
    lines.extend(f"- {analyzer}" for analyzer in analyzers)
    lines.extend([
        "",
        "Severity:",
        "; ".join(severities),
        "",
        "Finding count:",
        str(len(item.finding_refs)),
        "",
        "Suggested human action:",
        item.guidance,
        "",
        "Finding evidence:",
    ])
    if item.findings:
        for finding in item.findings:
            lines.extend([
                (
                    f"- {finding.category} / {finding.analyzer} / "
                    f"{finding.severity}"
                ),
                f"  - Benchmark: {finding.benchmark_version}",
                f"  - Evidence: {_evidence_summary(finding.evidence)}",
                f"  - Why: {finding.explanation}",
                f"  - Human review note: {finding.recommendation}",
            ])
    else:
        lines.append("- none")
    lines.extend([
        "",
    ])
    return lines


def _group_by_artifact_family(
    items: list[ImageRecommendation],
) -> list[tuple[str, list[ImageRecommendation]]]:
    groups: dict[str, list[ImageRecommendation]] = {}
    for item in items:
        groups.setdefault(_artifact_family_label(item), []).append(item)
    return [
        (family, groups[family])
        for family in sorted(groups)
    ]


def _artifact_family_label(item: ImageRecommendation) -> str:
    categories = sorted({ref.category for ref in item.finding_refs})
    if not categories:
        return "No finding family"
    if any(category.endswith(".error") for category in categories):
        return "Analyzer errors"
    if len(categories) > 1:
        return "Multiple artifact families"
    return categories[0]


def _category_counts(summary: RecommendationSummary) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for item in summary.recommendations:
        for ref in item.finding_refs:
            counts[ref.category] = counts.get(ref.category, 0) + 1
    return sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))


def _ref_values(item: ImageRecommendation, field: str) -> list[str]:
    values: list[str] = []
    for ref in item.finding_refs:
        value = getattr(ref, field)
        if value not in values:
            values.append(value)
    return values or ["none"]


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


def _image_word(count: int) -> str:
    return "image" if count == 1 else "images"


def _evidence_summary(evidence: Mapping[str, Any]) -> str:
    parts = [
        f"{key}={value}"
        for key, value in evidence.items()
        if key != "calibrated" and not isinstance(value, dict | list)
    ]
    return ", ".join(parts) if parts else "none"


def _finding_from_report(item: Mapping[str, Any]) -> Finding:
    return Finding(
        image_path=Path(str(item["image_path"])),
        analyzer=str(item["analyzer"]),
        category=str(item["category"]),
        severity=Severity[str(item["severity"])],
        confidence=float(item["confidence"]),
        false_positive_rate=float(item["false_positive_rate"]),
        benchmark_version=str(item["benchmark_version"]),
        evidence=dict(item.get("evidence", {})),
        explanation=str(item.get("explanation", "")),
        recommendation=str(item.get("recommendation", "")),
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
                "Dataset Forge emitted no current review finding for this "
                "image. You may still review it for style fit, caption fit, "
                "composition, licensing, duplicates, or training intent."
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
            guidance=(
                "Review this image first. Priority Review is an ordering signal, "
                "not an instruction to change, clean, export, or modify it."
            ),
        )

    if len({finding.category for finding in findings}) >= 2:
        return _recommendation(
            path=path,
            recommendation=PRIORITY_REVIEW,
            reason="Multiple artifact families detected.",
            reason_codes=("finding.multiple_categories",),
            findings=tuple(findings),
            guidance=(
                "Review this image first because multiple analyzer families "
                "emitted signals. This is not an instruction to execute cleanup."
            ),
        )

    return _recommendation(
        path=path,
        recommendation=NEEDS_REVIEW,
        reason="Measurable finding detected.",
        reason_codes=("finding.present",),
        findings=tuple(findings),
        guidance=(
            "Inspect this image before deciding whether the finding is a true "
            "artifact, acceptable style, or irrelevant to your training goal."
        ),
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
        findings=tuple(
            FindingEvidence(
                analyzer=finding.analyzer,
                category=finding.category,
                severity=finding.severity.name,
                confidence=finding.confidence,
                false_positive_rate=finding.false_positive_rate,
                benchmark_version=finding.benchmark_version,
                evidence=dict(finding.evidence),
                explanation=finding.explanation,
                recommendation=finding.recommendation,
            )
            for finding in sorted(findings, key=_finding_sort_key)
        ),
        guidance=guidance,
        confidence_note=CONFIDENCE_NOTE,
    )


def _analyzer_coverage(
    findings: list[Finding],
    context: DatasetContext,
) -> dict[str, Any]:
    image_paths_by_analyzer: dict[str, set[str]] = {}
    categories_by_analyzer: dict[str, set[str]] = {}
    findings_by_analyzer: dict[str, int] = {}
    for finding in findings:
        analyzer_name = finding.analyzer.split("/", 1)[0]
        image_paths_by_analyzer.setdefault(analyzer_name, set()).add(
            str(finding.image_path)
        )
        categories_by_analyzer.setdefault(analyzer_name, set()).add(finding.category)
        findings_by_analyzer[analyzer_name] = findings_by_analyzer.get(analyzer_name, 0) + 1

    analyzers = []
    for analyzer, version in sorted(context.analyzer_versions.items()):
        categories = sorted(categories_by_analyzer.get(analyzer, set()))
        analyzers.append({
            "analyzer": analyzer,
            "version": version,
            "ran": True,
            "finding_count": findings_by_analyzer.get(analyzer, 0),
            "image_count": len(image_paths_by_analyzer.get(analyzer, set())),
            "categories": categories,
            "calibration_status": (
                "uncalibrated" if categories or analyzer in context.analyzer_versions else "unknown"
            ),
        })

    return {
        "schema": "dataset-forge/analyzer-coverage/v1",
        "analyzers": analyzers,
        "currently_uncovered": [
            "periodic_frequency_contamination",
            "recursive_detail",
        ],
        "notes": [
            "Analyzer coverage reports what ran and what emitted findings.",
            "No finding from an analyzer is not proof that the artifact family is absent.",
            "All current artifact analyzers remain advisory review signals.",
        ],
    }


def _analyzer_versions_from_findings(findings: list[Finding]) -> dict[str, str]:
    versions: dict[str, str] = {}
    for finding in findings:
        if "/" not in finding.analyzer:
            continue
        analyzer, version = finding.analyzer.split("/", 1)
        versions.setdefault(analyzer, version)
    return versions


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
    "FindingEvidence",
    "ImageRecommendation",
    "RecommendationSummary",
    "build_recommendation_summary",
    "build_recommendation_summary_from_report",
    "render_recommendation_summary_markdown",
    "write_recommendation_summary_files",
]
