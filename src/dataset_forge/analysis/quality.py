from __future__ import annotations

import csv
import json
import statistics
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

IMAGE_WEIGHT_NAMES = (
    "artifact_quality",
    "texture_quality",
    "duplicate_quality",
    "resolution",
    "brightness_consistency",
    "contrast",
)
DATASET_WEIGHT_NAMES = (
    "exact_duplicates",
    "probable_duplicates",
    "artifact_burden",
    "texture_burden",
    "resolution_consistency",
    "brightness_consistency",
    "contrast_consistency",
    "aspect_ratio_consistency",
)
RECOMMENDATION_FIELDS = (
    "filename",
    "severity",
    "issue",
    "recommended_action",
    "reason",
    "suggested_preset",
    "suggested_strength",
)


class QualityConfigError(ValueError):
    """Raised when quality scoring configuration is invalid."""


@dataclass(frozen=True)
class QualityWeights:
    image_weights: dict[str, float]
    dataset_weights: dict[str, float]
    source: Path


@dataclass(frozen=True)
class Recommendation:
    filename: str
    severity: str
    issue: str
    recommended_action: str
    reason: str
    suggested_preset: str = ""
    suggested_strength: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class HealthSummary:
    dataset_health_score: float
    total_images: int
    images_requiring_cleanup: int
    likely_duplicates: int
    low_resolution_images: int
    critical_issues: int
    warnings: int


def default_quality_config_path() -> Path:
    return Path(__file__).resolve().parents[1] / "config" / "quality_weights.json"


def load_quality_weights(path: Path | None = None) -> QualityWeights:
    source = (path or default_quality_config_path()).expanduser().resolve()
    try:
        with source.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except json.JSONDecodeError as exc:
        raise QualityConfigError(
            f"Invalid JSON in quality config {source}: "
            f"line {exc.lineno}, column {exc.colno}."
        ) from exc
    except OSError as exc:
        raise QualityConfigError(f"Could not read quality config {source}: {exc}") from exc

    if not isinstance(data, dict):
        raise QualityConfigError(f"Quality config {source} must contain a JSON object.")
    image_weights = _validate_weights(data, "image_weights", IMAGE_WEIGHT_NAMES, source)
    dataset_weights = _validate_weights(
        data,
        "dataset_weights",
        DATASET_WEIGHT_NAMES,
        source,
    )
    return QualityWeights(image_weights, dataset_weights, source)


def assess_dataset_quality(
    rows: list[dict[str, object]],
    weights: QualityWeights,
) -> tuple[dict[str, object], list[Recommendation], HealthSummary]:
    valid = [row for row in rows if row.get("status") != "error"]
    if not valid:
        health = _empty_health(weights.source)
        return health, [], HealthSummary(0, 0, 0, 0, 0, 0, 0)

    brightness_center = statistics.median(
        float(row["average_brightness"]) for row in valid
    )
    contrast_center = statistics.median(float(row["average_contrast"]) for row in valid)

    for row in valid:
        _score_image(row, weights, brightness_center, contrast_center)

    health_score, component_scores = _dataset_health_score(valid, weights)
    average_artifact = _average(valid, "artifact_score")
    average_texture = _average(valid, "texture_score")
    from dataset_forge.evidence import evidence_from_rows
    from dataset_forge.recommendations.engine import (
        recommend_dataset,
        recommend_evidence,
    )

    evidence = evidence_from_rows(valid)
    evidence.dataset_metrics.update(
        {
            "dataset_health_score": health_score,
            "average_artifact_score": round(average_artifact, 2),
            "average_texture_score": round(average_texture, 2),
            "component_scores": component_scores,
        }
    )
    evidence_decisions = recommend_evidence(evidence)
    recommendations = [_legacy_recommendation(item) for item in evidence_decisions]
    decision_by_name = {item.filename: item for item in recommendations}
    cleanup_count = sum(
        decision.action
        in {
            "CLEAN_LIGHT",
            "CLEAN_MEDIUM",
            "CLEAN_STRONG",
            "TEXTURE_NORMALIZE_LIGHT",
            "TEXTURE_NORMALIZE_MEDIUM",
        }
        for decision in evidence_decisions
    )
    likely_duplicates = sum(
        bool(row.get("exact_duplicate_of") or row.get("probable_duplicate_of"))
        for row in valid
    )
    low_resolution = sum(float(row["megapixels"]) < 1 for row in valid)
    critical_issues = sum(item.severity == "CRITICAL" for item in recommendations)
    warnings = sum(item.severity == "WARNING" for item in recommendations)
    problem_rows = sorted(
        valid,
        key=lambda row: float(row["overall_quality_score"]),
    )[:5]
    report = {
        "dataset_health_score": health_score,
        "total_images": len(valid),
        "images_requiring_cleanup": cleanup_count,
        "likely_duplicates": likely_duplicates,
        "low_resolution_images": low_resolution,
        "average_artifact_score": round(average_artifact, 2),
        "average_texture_score": round(average_texture, 2),
        "top_problem_images": [
            {
                "filename": str(row["filename"]),
                "overall_quality_score": float(row["overall_quality_score"]),
                "primary_issue": decision_by_name[str(row["filename"])].issue,
            }
            for row in problem_rows
        ],
        "summary_recommendations": recommend_dataset(
            evidence,
            evidence_decisions,
        ),
        "component_scores": component_scores,
        "quality_config": str(weights.source),
        "evidence_schema": evidence.schema,
        "evidence_version": evidence.version,
    }
    summary = HealthSummary(
        dataset_health_score=health_score,
        total_images=len(valid),
        images_requiring_cleanup=cleanup_count,
        likely_duplicates=likely_duplicates,
        low_resolution_images=low_resolution,
        critical_issues=critical_issues,
        warnings=warnings,
    )
    return report, recommendations, summary


def write_health_report(path: Path, report: dict[str, object]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")


def write_recommendations(path: Path, recommendations: list[Recommendation]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=RECOMMENDATION_FIELDS)
        writer.writeheader()
        writer.writerows(item.to_dict() for item in recommendations)


def _score_image(
    row: dict[str, object],
    weights: QualityWeights,
    brightness_center: float,
    contrast_center: float,
) -> None:
    artifact = float(row["artifact_score"])
    texture = float(row["texture_score"])
    duplicate_risk = 100.0 if row.get("exact_duplicate_of") else (
        75.0 if row.get("probable_duplicate_of") else 0.0
    )
    resolution = _resolution_score(float(row["megapixels"]))
    brightness = _consistency_score(
        float(row["average_brightness"]),
        brightness_center,
        2.5,
    )
    contrast = _contrast_score(
        float(row["average_contrast"]),
        contrast_center,
    )
    components = {
        "artifact_quality": 100 - artifact,
        "texture_quality": 100 - texture,
        "duplicate_quality": 100 - duplicate_risk,
        "resolution": resolution,
        "brightness_consistency": brightness,
        "contrast": contrast,
    }
    overall = _weighted_score(components, weights.image_weights)
    row.update(
        {
            "overall_quality_score": overall,
            "duplicate_risk": duplicate_risk,
            "resolution_score": resolution,
            "brightness_consistency_score": brightness,
            "contrast_score": contrast,
        }
    )


def _legacy_recommendation(decision: Any) -> Recommendation:
    """Render an engine decision using the established recommendations.csv vocabulary."""
    action = {
        "KEEP": "Recommend keep as-is",
        "CLEAN_LIGHT": "Recommend cleanup",
        "CLEAN_MEDIUM": "Recommend cleanup",
        "CLEAN_STRONG": "Recommend cleanup",
        "TEXTURE_NORMALIZE_LIGHT": "Recommend cleanup",
        "TEXTURE_NORMALIZE_MEDIUM": "Recommend cleanup",
        "MANUAL_REVIEW": "Recommend review",
        "DUPLICATE_REVIEW": "Recommend duplicate review/removal",
        "EXCLUDE": "Recommend duplicate removal",
        "REGENERATE": "Recommend regeneration or exclusion",
    }.get(decision.action, "Recommend review")
    return Recommendation(
        filename=decision.filename,
        severity=decision.severity,
        issue=decision.issue,
        recommended_action=action,
        reason=decision.explanation,
        suggested_preset=decision.suggested_preset,
        suggested_strength=decision.suggested_strength,
    )


def _dataset_health_score(
    rows: list[dict[str, object]],
    weights: QualityWeights,
) -> tuple[float, dict[str, float]]:
    total = len(rows)
    exact_percentage = sum(bool(row.get("exact_duplicate_of")) for row in rows) / total
    probable_percentage = sum(
        bool(row.get("probable_duplicate_of")) for row in rows
    ) / total
    components = {
        "exact_duplicates": 100 * (1 - exact_percentage),
        "probable_duplicates": 100 * (1 - probable_percentage),
        "artifact_burden": 100 - _average(rows, "artifact_score"),
        "texture_burden": 100 - _average(rows, "texture_score"),
        "resolution_consistency": _distribution_score(
            [float(row["megapixels"]) for row in rows],
            scale=1.5,
        ),
        "brightness_consistency": _distribution_score(
            [float(row["average_brightness"]) for row in rows],
            scale=18,
        ),
        "contrast_consistency": _distribution_score(
            [float(row["average_contrast"]) for row in rows],
            scale=15,
        ),
        "aspect_ratio_consistency": _distribution_score(
            [float(row["aspect_ratio"]) for row in rows],
            scale=0.35,
        ),
    }
    rounded = {name: _clamp(value) for name, value in components.items()}
    return _weighted_score(rounded, weights.dataset_weights), rounded


def _resolution_score(megapixels: float) -> float:
    if megapixels <= 0.25:
        return _clamp(megapixels / 0.25 * 25)
    if megapixels <= 1:
        return _clamp(25 + (megapixels - 0.25) / 0.75 * 35)
    if megapixels <= 4:
        return _clamp(60 + (megapixels - 1) / 3 * 40)
    return 100.0


def _contrast_score(value: float, center: float) -> float:
    consistency = _consistency_score(value, center, 3)
    useful_range = 100 - min(abs(value - 35) * 2.2, 100)
    return _clamp(0.6 * consistency + 0.4 * useful_range)


def _consistency_score(value: float, center: float, penalty: float) -> float:
    return _clamp(100 - abs(value - center) * penalty)


def _distribution_score(values: list[float], scale: float) -> float:
    if len(values) < 2:
        return 100.0
    return _clamp(100 - statistics.pstdev(values) / scale * 100)


def _weighted_score(values: dict[str, float], weights: dict[str, float]) -> float:
    total_weight = sum(weights.values())
    score = sum(values[name] * weights[name] for name in weights) / total_weight
    return _clamp(score)


def _validate_weights(
    data: dict[str, Any],
    section: str,
    required: tuple[str, ...],
    source: Path,
) -> dict[str, float]:
    values = data.get(section)
    if not isinstance(values, dict):
        raise QualityConfigError(
            f"Quality config section '{section}' must be an object: {source}"
        )
    missing = [name for name in required if name not in values]
    if missing:
        raise QualityConfigError(
            f"Quality config {source} is missing {section} weight(s): "
            f"{', '.join(missing)}."
        )
    normalized: dict[str, float] = {}
    for name in required:
        value = values[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            raise QualityConfigError(
                f"Quality weight '{name}' must be a non-negative number: {source}"
            )
        normalized[name] = float(value)
    if sum(normalized.values()) <= 0:
        raise QualityConfigError(
            f"Quality config section '{section}' must have a positive total weight: {source}"
        )
    return normalized


def _empty_health(source: Path) -> dict[str, object]:
    return {
        "dataset_health_score": 0.0,
        "total_images": 0,
        "images_requiring_cleanup": 0,
        "likely_duplicates": 0,
        "low_resolution_images": 0,
        "average_artifact_score": 0.0,
        "average_texture_score": 0.0,
        "top_problem_images": [],
        "summary_recommendations": ["No readable images were available for assessment."],
        "component_scores": {},
        "quality_config": str(source),
    }


def _average(rows: list[dict[str, object]], field: str) -> float:
    return sum(float(row[field]) for row in rows) / len(rows)


def _clamp(value: float) -> float:
    return round(min(100.0, max(0.0, value)), 2)
