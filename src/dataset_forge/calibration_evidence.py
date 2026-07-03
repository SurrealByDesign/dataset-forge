"""Internal calibration evidence helpers for inspection reports.

This module compares an existing inspection report against a small
ground-truth label file. It computes deterministic metrics only; it does not
run analyzers, change thresholds, or modify images.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dataset_forge.analyzers.registry import create_analyzers

CALIBRATION_LABELS_SCHEMA = "dataset-forge/calibration-labels/v1"
CALIBRATION_EVIDENCE_SCHEMA = "dataset-forge/calibration-evidence/v1"


@dataclass(frozen=True)
class CalibrationLabels:
    schema: str
    labels_by_image: dict[str, frozenset[str]]

    @property
    def image_count(self) -> int:
        return len(self.labels_by_image)


@dataclass(frozen=True)
class ConfusionMetrics:
    tp: int
    fp: int
    fn: int
    tn: int

    @property
    def precision(self) -> float:
        return _ratio(self.tp, self.tp + self.fp)

    @property
    def recall(self) -> float:
        return _ratio(self.tp, self.tp + self.fn)

    @property
    def f1(self) -> float:
        denom = (2 * self.tp) + self.fp + self.fn
        return _ratio(2 * self.tp, denom)

    @property
    def false_positive_rate(self) -> float:
        return _ratio(self.fp, self.fp + self.tn)

    def to_dict(self) -> dict[str, int | float]:
        return {
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
            "tn": self.tn,
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
            "false_positive_rate": self.false_positive_rate,
        }


@dataclass(frozen=True)
class CalibrationEvidence:
    schema: str
    report_schema: str
    label_schema: str
    evaluated_image_count: int
    analyzer_results: dict[str, ConfusionMetrics]
    category_results: dict[str, ConfusionMetrics]
    category_to_analyzer: dict[str, str]
    ignored_error_finding_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "report_schema": self.report_schema,
            "label_schema": self.label_schema,
            "evaluated_image_count": self.evaluated_image_count,
            "analyzer_results": {
                analyzer_id: metrics.to_dict()
                for analyzer_id, metrics in self.analyzer_results.items()
            },
            "category_results": {
                category: metrics.to_dict()
                for category, metrics in self.category_results.items()
            },
            "category_to_analyzer": dict(self.category_to_analyzer),
            "ignored_error_finding_count": self.ignored_error_finding_count,
        }


def load_calibration_labels(path: Path) -> CalibrationLabels:
    """Load a schema-versioned ground-truth label file."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid calibration label JSON: {path}") from exc
    return parse_calibration_labels(data)


def parse_calibration_labels(data: dict[str, Any]) -> CalibrationLabels:
    """Parse and validate a calibration label payload."""
    schema = data.get("schema")
    if schema != CALIBRATION_LABELS_SCHEMA:
        raise ValueError(
            f"Unsupported calibration label schema {schema!r}; "
            f"expected {CALIBRATION_LABELS_SCHEMA!r}"
        )

    known_categories = set(_category_to_analyzer())
    labels_by_image: dict[str, frozenset[str]] = {}
    raw_labels = data.get("labels")
    if not isinstance(raw_labels, list):
        raise ValueError("calibration labels must contain a 'labels' list")

    for raw in raw_labels:
        if not isinstance(raw, dict):
            raise ValueError("each calibration label must be an object")
        image_path = _normalize_path(raw.get("image_path"))
        if image_path in labels_by_image:
            raise ValueError(f"duplicate calibration label for image: {image_path}")
        categories = raw.get("categories", [])
        if not isinstance(categories, list):
            raise ValueError(f"categories must be a list for image: {image_path}")
        category_set = frozenset(str(category) for category in categories)
        unknown = sorted(category_set - known_categories)
        if unknown:
            raise ValueError(
                f"unknown calibration categories for {image_path}: {unknown}"
            )
        labels_by_image[image_path] = category_set

    return CalibrationLabels(
        schema=CALIBRATION_LABELS_SCHEMA,
        labels_by_image=dict(sorted(labels_by_image.items())),
    )


def evaluate_calibration(
    inspection_report: dict[str, Any],
    labels: CalibrationLabels,
) -> CalibrationEvidence:
    """Compute calibration evidence from an inspection report and labels."""
    category_to_analyzer = _category_to_analyzer()
    analyzer_to_categories = _analyzer_to_categories(category_to_analyzer)
    predictions_by_image = _predictions_by_image(inspection_report)
    ignored_error_count = _ignored_error_finding_count(inspection_report)

    category_results = {
        category: _evaluate_category(category, labels, predictions_by_image)
        for category in sorted(category_to_analyzer)
    }
    analyzer_results = {
        analyzer_id: _evaluate_analyzer(
            categories, labels, predictions_by_image
        )
        for analyzer_id, categories in sorted(analyzer_to_categories.items())
    }

    return CalibrationEvidence(
        schema=CALIBRATION_EVIDENCE_SCHEMA,
        report_schema=str(inspection_report.get("schema", "")),
        label_schema=labels.schema,
        evaluated_image_count=labels.image_count,
        analyzer_results=analyzer_results,
        category_results=category_results,
        category_to_analyzer=category_to_analyzer,
        ignored_error_finding_count=ignored_error_count,
    )


def evaluate_calibration_files(
    inspection_report_path: Path,
    labels_path: Path,
) -> CalibrationEvidence:
    """Load report and label files, then compute calibration evidence."""
    report = json.loads(inspection_report_path.read_text(encoding="utf-8"))
    labels = load_calibration_labels(labels_path)
    return evaluate_calibration(report, labels)


def write_calibration_evidence_json(
    evidence: CalibrationEvidence,
    output_path: Path,
) -> None:
    """Write calibration evidence JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(evidence.to_dict(), indent=2) + "\n",
        encoding="utf-8",
    )


def _category_to_analyzer() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for analyzer in create_analyzers():
        for category in analyzer.supported_categories:
            if _is_error_category(category):
                continue
            mapping[category] = analyzer.analyzer_id
    return dict(sorted(mapping.items()))


def _analyzer_to_categories(category_to_analyzer: dict[str, str]) -> dict[str, tuple[str, ...]]:
    grouped: dict[str, list[str]] = {}
    for category, analyzer_id in category_to_analyzer.items():
        grouped.setdefault(analyzer_id, []).append(category)
    return {
        analyzer_id: tuple(sorted(categories))
        for analyzer_id, categories in grouped.items()
    }


def _evaluate_category(
    category: str,
    labels: CalibrationLabels,
    predictions_by_image: dict[str, frozenset[str]],
) -> ConfusionMetrics:
    tp = fp = fn = tn = 0
    for image_path, truth in labels.labels_by_image.items():
        actual = category in truth
        predicted = category in predictions_by_image.get(image_path, frozenset())
        tp, fp, fn, tn = _accumulate(tp, fp, fn, tn, actual, predicted)
    return ConfusionMetrics(tp=tp, fp=fp, fn=fn, tn=tn)


def _evaluate_analyzer(
    categories: tuple[str, ...],
    labels: CalibrationLabels,
    predictions_by_image: dict[str, frozenset[str]],
) -> ConfusionMetrics:
    category_set = set(categories)
    tp = fp = fn = tn = 0
    for image_path, truth in labels.labels_by_image.items():
        predictions = predictions_by_image.get(image_path, frozenset())
        actual = bool(category_set.intersection(truth))
        predicted = bool(category_set.intersection(predictions))
        tp, fp, fn, tn = _accumulate(tp, fp, fn, tn, actual, predicted)
    return ConfusionMetrics(tp=tp, fp=fp, fn=fn, tn=tn)


def _accumulate(
    tp: int,
    fp: int,
    fn: int,
    tn: int,
    actual: bool,
    predicted: bool,
) -> tuple[int, int, int, int]:
    if actual and predicted:
        tp += 1
    elif not actual and predicted:
        fp += 1
    elif actual and not predicted:
        fn += 1
    else:
        tn += 1
    return tp, fp, fn, tn


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


def _ignored_error_finding_count(report: dict[str, Any]) -> int:
    return sum(
        1
        for finding in report.get("findings", [])
        if isinstance(finding, dict)
        and _is_error_category(str(finding.get("category", "")))
    )


def _is_error_category(category: str) -> bool:
    return category.endswith(".error")


def _normalize_path(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("image_path must be a non-empty string")
    return value.replace("\\", "/")


def _ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 6)


__all__ = [
    "CALIBRATION_EVIDENCE_SCHEMA",
    "CALIBRATION_LABELS_SCHEMA",
    "CalibrationEvidence",
    "CalibrationLabels",
    "ConfusionMetrics",
    "evaluate_calibration",
    "evaluate_calibration_files",
    "load_calibration_labels",
    "parse_calibration_labels",
    "write_calibration_evidence_json",
]
