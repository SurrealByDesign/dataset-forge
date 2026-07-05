"""Deterministic comparison of existing Dataset Forge inspect outputs."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from dataset_forge import __version__
from dataset_forge.recommendation_summary import RECOMMENDATION_SUMMARY_SCHEMA
from dataset_forge.report import REPORT_SCHEMA
from dataset_forge.review_decisions import load_review_decisions


COMPARISON_SUMMARY_SCHEMA = "dataset-forge/comparison-summary/v1"

INSPECTION_REPORT_FILENAME = "inspection_report.json"
RECOMMENDATION_SUMMARY_FILENAME = "recommendation_summary.json"
REVIEW_DECISIONS_FILENAME = "review_decisions.json"
COMPARISON_JSON_FILENAME = "comparison_summary.json"
COMPARISON_MARKDOWN_FILENAME = "comparison_summary.md"

_RECOMMENDATION_COUNT_KEYS = (
    "ready_for_training_count",
    "needs_review_count",
    "priority_review_count",
)
_RECOMMENDATION_LABELS = {
    "READY_FOR_TRAINING": "Ready for Training",
    "NEEDS_REVIEW": "Needs Review",
    "PRIORITY_REVIEW": "Priority Review",
    "ready_for_training_count": "Ready for Training",
    "needs_review_count": "Needs Review",
    "priority_review_count": "Priority Review",
}


class ComparisonError(ValueError):
    """Raised when comparison inputs are missing or unsupported."""


def compare_inspect_outputs(
    before_output: Path,
    after_output: Path,
    comparison_output: Path,
) -> tuple[Path, Path]:
    """Compare two inspect output folders and write JSON + Markdown summaries."""

    summary = build_comparison_summary(before_output, after_output)
    comparison_output.mkdir(parents=True, exist_ok=True)
    json_path = comparison_output / COMPARISON_JSON_FILENAME
    markdown_path = comparison_output / COMPARISON_MARKDOWN_FILENAME
    json_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(
        render_comparison_markdown(summary),
        encoding="utf-8",
    )
    return json_path, markdown_path


def build_comparison_summary(before_output: Path, after_output: Path) -> dict[str, Any]:
    """Build a deterministic comparison summary from existing sidecars only."""

    before = _load_inspect_output(before_output, "before")
    after = _load_inspect_output(after_output, "after")
    recommendation_counts = _recommendation_count_comparison(
        before["recommendation_summary"],
        after["recommendation_summary"],
    )
    category_counts = _count_comparison(
        _finding_counts(before["inspection_report"], "category"),
        _finding_counts(after["inspection_report"], "category"),
        "category",
    )
    analyzer_counts = _count_comparison(
        _finding_counts(before["inspection_report"], "analyzer"),
        _finding_counts(after["inspection_report"], "analyzer"),
        "analyzer",
    )
    before_findings = _finding_counter(before["inspection_report"])
    after_findings = _finding_counter(after["inspection_report"])

    return {
        "schema": COMPARISON_SUMMARY_SCHEMA,
        "tool_version": __version__,
        "before": _source_metadata(before),
        "after": _source_metadata(after),
        "review_decisions": {
            "before_available": before["review_decisions_available"],
            "after_available": after["review_decisions_available"],
            "before_decision_count": before["review_decision_count"],
            "after_decision_count": after["review_decision_count"],
        },
        "recommendation_counts": recommendation_counts,
        "finding_category_counts": category_counts,
        "analyzer_output_counts": analyzer_counts,
        "changed_recommendations": _changed_recommendations(
            before["recommendation_summary"],
            after["recommendation_summary"],
        ),
        "images_only_in_before": _images_only_in(
            before["recommendation_summary"],
            after["recommendation_summary"],
        ),
        "images_only_in_after": _images_only_in(
            after["recommendation_summary"],
            before["recommendation_summary"],
        ),
        "new_findings": _finding_delta(after_findings, before_findings),
        "resolved_findings": _finding_delta(before_findings, after_findings),
        "unchanged_findings_count": sum(
            min(before_findings[key], after_findings[key])
            for key in before_findings.keys() & after_findings.keys()
        ),
    }


def render_comparison_markdown(summary: Mapping[str, Any]) -> str:
    """Render a plain Markdown comparison summary."""

    lines: list[str] = [
        "# Dataset Comparison Summary",
        "",
        "## Dataset Summary",
        "",
        f"- Before path: {summary['before']['path']}",
        f"- After path: {summary['after']['path']}",
        f"- Before inspection schema: {summary['before']['inspection_schema']}",
        f"- After inspection schema: {summary['after']['inspection_schema']}",
        f"- Before recommendation schema: {summary['before']['recommendation_schema']}",
        f"- After recommendation schema: {summary['after']['recommendation_schema']}",
        f"- Before inspect version: {summary['before']['inspect_version'] or 'not recorded'}",
        f"- After inspect version: {summary['after']['inspect_version'] or 'not recorded'}",
        f"- Tool version: {summary['tool_version']}",
        "",
        "Recommendation counts:",
    ]
    for key in _RECOMMENDATION_COUNT_KEYS:
        counts = summary["recommendation_counts"][key]
        lines.append(
            f"- {_RECOMMENDATION_LABELS[key]}: "
            f"before {counts['before']}, after {counts['after']}, "
            f"delta {_format_delta(counts['delta'])}"
        )
    review = summary["review_decisions"]
    lines.extend([
        "",
        "Review decisions available:",
        f"- Before: {_yes_no(review['before_available'])}",
        f"- After: {_yes_no(review['after_available'])}",
        f"- Decision count before: {review['before_decision_count']}",
        f"- Decision count after: {review['after_decision_count']}",
        "",
        "## Images With Changed Recommendations",
        "",
    ])
    lines.extend(_markdown_changed_recommendations(summary["changed_recommendations"]))
    lines.extend(["", "## Images With New Findings", ""])
    lines.extend(_markdown_findings(summary["new_findings"]))
    lines.extend(["", "## Images With Resolved Findings", ""])
    lines.extend(_markdown_findings(summary["resolved_findings"]))
    lines.extend(["", "## Recommendation Count Changes", ""])
    lines.extend(_markdown_count_changes(summary["recommendation_counts"]))
    lines.extend(["", "## Finding Category Changes", ""])
    lines.extend(_markdown_named_count_changes(summary["finding_category_counts"], "category"))
    lines.extend(["", "## Analyzer Output Changes", ""])
    lines.extend(_markdown_named_count_changes(summary["analyzer_output_counts"], "analyzer"))
    lines.extend([
        "",
        "Recommendations and findings are compared from existing sidecars only.",
        "Dataset Forge did not inspect images or modify source files.",
        "",
    ])
    return "\n".join(lines).rstrip() + "\n"


def _load_inspect_output(output_dir: Path, label: str) -> dict[str, Any]:
    root = output_dir.expanduser().resolve()
    inspection_path = root / INSPECTION_REPORT_FILENAME
    recommendation_path = root / RECOMMENDATION_SUMMARY_FILENAME
    if not inspection_path.is_file():
        raise ComparisonError(
            f"Missing {label} inspection report: {inspection_path}. "
            "Run 'dataset-forge inspect <dataset>' first and pass the inspect_output folder."
        )
    if not recommendation_path.is_file():
        raise ComparisonError(
            f"Missing {label} recommendation summary: {recommendation_path}. "
            "Run 'dataset-forge inspect <dataset>' first and pass the inspect_output folder."
        )

    inspection_report = _load_json_object(inspection_path, f"{label} inspection report")
    recommendation_summary = _load_json_object(
        recommendation_path,
        f"{label} recommendation summary",
    )
    _validate_schema(
        inspection_report,
        REPORT_SCHEMA,
        f"{label} inspection report",
    )
    _validate_schema(
        recommendation_summary,
        RECOMMENDATION_SUMMARY_SCHEMA,
        f"{label} recommendation summary",
    )
    source_report_schema = recommendation_summary.get("source_report_schema")
    if source_report_schema != REPORT_SCHEMA:
        raise ComparisonError(
            f"Unsupported {label} recommendation source report schema "
            f"{source_report_schema!r}; expected {REPORT_SCHEMA!r}"
        )

    decisions_path = root / REVIEW_DECISIONS_FILENAME
    decisions_available = decisions_path.is_file()
    decision_count = 0
    if decisions_available:
        decision_count = len(load_review_decisions(decisions_path).decisions)

    return {
        "path": root,
        "inspection_report": inspection_report,
        "recommendation_summary": recommendation_summary,
        "review_decisions_available": decisions_available,
        "review_decision_count": decision_count,
    }


def _source_metadata(source: Mapping[str, Any]) -> dict[str, Any]:
    report = source["inspection_report"]
    summary = source["recommendation_summary"]
    return {
        "path": str(source["path"]),
        "inspection_schema": report["schema"],
        "recommendation_schema": summary["schema"],
        "inspect_version": (
            report.get("tool_version")
            or report.get("dataset_forge_version")
            or report.get("version")
        ),
    }


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ComparisonError(f"Malformed JSON in {label}: {path}") from exc
    if not isinstance(data, dict):
        raise ComparisonError(f"{label} must be a JSON object: {path}")
    return data


def _validate_schema(payload: Mapping[str, Any], expected: str, label: str) -> None:
    schema = payload.get("schema")
    if schema != expected:
        raise ComparisonError(
            f"Unsupported {label} schema {schema!r}; expected {expected!r}"
        )


def _recommendation_count_comparison(
    before_summary: Mapping[str, Any],
    after_summary: Mapping[str, Any],
) -> dict[str, dict[str, int]]:
    before_counts = before_summary.get("summary", {})
    after_counts = after_summary.get("summary", {})
    return {
        key: {
            "before": _int_count(before_counts, key),
            "after": _int_count(after_counts, key),
            "delta": _int_count(after_counts, key) - _int_count(before_counts, key),
        }
        for key in _RECOMMENDATION_COUNT_KEYS
    }


def _count_comparison(
    before: Mapping[str, int],
    after: Mapping[str, int],
    name_field: str,
) -> list[dict[str, int | str]]:
    return [
        {
            name_field: name,
            "before": int(before.get(name, 0)),
            "after": int(after.get(name, 0)),
            "delta": int(after.get(name, 0)) - int(before.get(name, 0)),
        }
        for name in sorted(set(before) | set(after))
    ]


def _finding_counts(report: Mapping[str, Any], field: str) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for finding in report.get("findings", []):
        if isinstance(finding, dict):
            counts[str(finding.get(field, ""))] += 1
    counts.pop("", None)
    return dict(sorted(counts.items()))


def _changed_recommendations(
    before_summary: Mapping[str, Any],
    after_summary: Mapping[str, Any],
) -> list[dict[str, str]]:
    before_items = _recommendations_by_image(before_summary)
    after_items = _recommendations_by_image(after_summary)
    changes = []
    for image_path in sorted(before_items.keys() & after_items.keys()):
        before = before_items[image_path]
        after = after_items[image_path]
        if before.get("recommendation") == after.get("recommendation"):
            continue
        changes.append({
            "image_path": image_path,
            "filename": Path(image_path).name or image_path,
            "before_recommendation": _display_recommendation(before),
            "after_recommendation": _display_recommendation(after),
            "primary_reason": str(after.get("primary_reason", "")),
        })
    return changes


def _images_only_in(
    source_summary: Mapping[str, Any],
    other_summary: Mapping[str, Any],
) -> list[dict[str, str]]:
    source_items = _recommendations_by_image(source_summary)
    other_items = _recommendations_by_image(other_summary)
    return [
        {
            "image_path": image_path,
            "filename": Path(image_path).name or image_path,
            "recommendation": _display_recommendation(source_items[image_path]),
        }
        for image_path in sorted(source_items.keys() - other_items.keys())
    ]


def _recommendations_by_image(summary: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    items: dict[str, Mapping[str, Any]] = {}
    for item in summary.get("recommendations", []):
        if isinstance(item, dict) and item.get("image_path"):
            items[_normalize_path(str(item["image_path"]))] = item
    return items


def _display_recommendation(item: Mapping[str, Any]) -> str:
    return str(
        item.get("display_label")
        or _RECOMMENDATION_LABELS.get(str(item.get("recommendation")), item.get("recommendation", ""))
    )


def _finding_counter(report: Mapping[str, Any]) -> Counter[tuple[str, str, str, str]]:
    counter: Counter[tuple[str, str, str, str]] = Counter()
    for finding in report.get("findings", []):
        if not isinstance(finding, dict):
            continue
        counter[
            (
                _normalize_path(str(finding.get("image_path", ""))),
                str(finding.get("category", "")),
                str(finding.get("analyzer", "")),
                str(finding.get("severity", "")),
            )
        ] += 1
    return counter


def _finding_delta(
    source: Counter[tuple[str, str, str, str]],
    baseline: Counter[tuple[str, str, str, str]],
) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for key in sorted(source):
        remaining = source[key] - baseline.get(key, 0)
        for _index in range(max(remaining, 0)):
            image_path, category, analyzer, severity = key
            items.append({
                "image_path": image_path,
                "filename": Path(image_path).name or image_path,
                "category": category,
                "severity": severity,
                "analyzer": analyzer,
            })
    return items


def _markdown_changed_recommendations(items: list[Mapping[str, str]]) -> list[str]:
    if not items:
        return ["No recommendation changes."]
    lines: list[str] = []
    for item in items:
        lines.extend([
            f"### {item['filename']}",
            "",
            item["before_recommendation"],
            "",
            "->",
            "",
            item["after_recommendation"],
            "",
            "Primary reason:",
            item["primary_reason"] or "not recorded",
            "",
        ])
    return lines


def _markdown_findings(items: list[Mapping[str, str]]) -> list[str]:
    if not items:
        return ["No findings in this group."]
    lines: list[str] = []
    for item in items:
        lines.extend([
            f"### {item['filename']}",
            "",
            f"- Category: {item['category']}",
            f"- Severity: {item['severity']}",
            f"- Analyzer: {item['analyzer']}",
            "",
        ])
    return lines


def _markdown_count_changes(items: Mapping[str, Mapping[str, int]]) -> list[str]:
    return [
        (
            f"- {_RECOMMENDATION_LABELS[key]}: before {value['before']}, "
            f"after {value['after']}, delta {_format_delta(value['delta'])}"
        )
        for key, value in items.items()
    ]


def _markdown_named_count_changes(
    items: list[Mapping[str, int | str]],
    name_field: str,
) -> list[str]:
    if not items:
        return ["No findings in either output."]
    return [
        (
            f"- {item[name_field]}: before {item['before']}, "
            f"after {item['after']}, delta {_format_delta(int(item['delta']))}"
        )
        for item in items
    ]


def _int_count(payload: Mapping[str, Any], key: str) -> int:
    value = payload.get(key, 0)
    if not isinstance(value, int):
        raise ComparisonError(f"Recommendation summary count must be an integer: {key}")
    return value


def _normalize_path(value: str) -> str:
    return value.replace("\\", "/")


def _format_delta(value: int) -> str:
    return f"+{value}" if value > 0 else str(value)


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


__all__ = [
    "COMPARISON_JSON_FILENAME",
    "COMPARISON_MARKDOWN_FILENAME",
    "COMPARISON_SUMMARY_SCHEMA",
    "ComparisonError",
    "build_comparison_summary",
    "compare_inspect_outputs",
    "render_comparison_markdown",
]
