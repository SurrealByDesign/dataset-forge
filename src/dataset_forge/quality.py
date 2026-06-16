"""Backward-compatible quality and recommendation imports."""

from dataset_forge.analysis.quality import (
    DATASET_WEIGHT_NAMES,
    IMAGE_WEIGHT_NAMES,
    RECOMMENDATION_FIELDS,
    HealthSummary,
    QualityConfigError,
    QualityWeights,
    Recommendation,
    assess_dataset_quality,
    default_quality_config_path,
    load_quality_weights,
    write_health_report,
    write_recommendations,
)

__all__ = [
    "DATASET_WEIGHT_NAMES",
    "IMAGE_WEIGHT_NAMES",
    "RECOMMENDATION_FIELDS",
    "HealthSummary",
    "QualityConfigError",
    "QualityWeights",
    "Recommendation",
    "assess_dataset_quality",
    "default_quality_config_path",
    "load_quality_weights",
    "write_health_report",
    "write_recommendations",
]

