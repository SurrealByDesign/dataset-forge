"""Internal analyzer registry for the inspect pipeline.

This is deliberately small and static. It is not a plugin system; it only
centralizes the built-in analyzers supported by the current inspect surface.
"""

from __future__ import annotations

from typing import TypeAlias

from dataset_forge.analyzers.base import Analyzer
from dataset_forge.analyzers.crystalline import CrystallineFacetingAnalyzer
from dataset_forge.analyzers.duplicates import DuplicateDetectionAnalyzer
from dataset_forge.analyzers.high_frequency_isolated import (
    HighFrequencyIsolatedArtifactAnalyzer,
)
from dataset_forge.analyzers.image_encoding import ImageEncodingAnalyzer
from dataset_forge.analyzers.oversharpening import OversharpeningHaloAnalyzer
from dataset_forge.analyzers.texture import TextureAnalyzer

AnalyzerClass: TypeAlias = type[Analyzer]

ANALYZER_CLASSES: tuple[AnalyzerClass, ...] = (
    TextureAnalyzer,
    CrystallineFacetingAnalyzer,
    OversharpeningHaloAnalyzer,
    HighFrequencyIsolatedArtifactAnalyzer,
    DuplicateDetectionAnalyzer,
    ImageEncodingAnalyzer,
)


def create_analyzers() -> list[Analyzer]:
    """Return fresh analyzer instances in inspect execution order."""
    return [analyzer_class() for analyzer_class in ANALYZER_CLASSES]


def analyzer_versions() -> dict[str, str]:
    """Return analyzer name -> version for DatasetContext metadata."""
    return {
        analyzer.name: analyzer.version
        for analyzer in create_analyzers()
    }


def create_analyzer_registry() -> dict[str, Analyzer]:
    """Return analyzer_id -> instance for benchmark expectation lookup."""
    return {
        analyzer.analyzer_id: analyzer
        for analyzer in create_analyzers()
    }


__all__ = [
    "ANALYZER_CLASSES",
    "analyzer_versions",
    "create_analyzer_registry",
    "create_analyzers",
]
