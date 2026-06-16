"""Configuration entry points."""

from dataset_forge.analysis.quality import (
    QualityConfigError,
    QualityWeights,
    default_quality_config_path,
    load_quality_weights,
)

__all__ = [
    "QualityConfigError",
    "QualityWeights",
    "default_quality_config_path",
    "load_quality_weights",
]

