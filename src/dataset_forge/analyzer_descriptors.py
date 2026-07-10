"""Internal analyzer metadata descriptors.

Analyzer descriptors are metadata only. They do not execute analyzers, configure
review signals, expose plugins, or change thresholds.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from dataset_forge.analyzers.base import Analyzer

EXECUTION_ENABLED = "enabled"
EXECUTION_DISABLED = "disabled"
DISPLAY_VISIBLE = "visible"
DISPLAY_HIDDEN = "hidden"
TRIAGE_INCLUDED = "included"
TRIAGE_EXCLUDED = "excluded"

FAMILY_TECHNICAL_QUALITY = "Technical Quality"
FAMILY_DATASET_STRUCTURE = "Dataset Structure"
FAMILY_DIVERSITY = "Diversity"
FAMILY_STYLE_CONSISTENCY = "Style Consistency"
FAMILY_METADATA = "Metadata"

CALIBRATION_ADVISORY = "advisory"
CALIBRATION_EXPERIMENTAL = "experimental"
CALIBRATION_CALIBRATED = "calibrated"


@dataclass(frozen=True)
class AnalyzerDescriptor:
    id: str
    display_name: str
    description: str
    version: str
    family: str
    categories_emitted: tuple[str, ...]
    calibration_status: str
    deterministic: bool
    requires_dataset_context: bool
    requires_image_measurements: bool
    default_execution_policy: str
    default_display_policy: str
    default_triage_policy: str


BUILT_IN_ANALYZER_DESCRIPTORS: tuple[AnalyzerDescriptor, ...] = (
    AnalyzerDescriptor(
        id="texture_analyzer",
        display_name="Texture Analyzer",
        description=(
            "Detects elevated microtexture density relative to the dataset "
            "baseline."
        ),
        version="v1",
        family=FAMILY_TECHNICAL_QUALITY,
        categories_emitted=("texture.high_microtexture", "texture.error"),
        calibration_status=CALIBRATION_ADVISORY,
        deterministic=True,
        requires_dataset_context=True,
        requires_image_measurements=True,
        default_execution_policy=EXECUTION_ENABLED,
        default_display_policy=DISPLAY_VISIBLE,
        default_triage_policy=TRIAGE_INCLUDED,
    ),
    AnalyzerDescriptor(
        id="crystalline_faceting_analyzer",
        display_name="Crystalline Faceting Analyzer",
        description=(
            "Detects angular micro-polygon shading consistent with crystalline "
            "faceting artifacts."
        ),
        version="v1",
        family=FAMILY_TECHNICAL_QUALITY,
        categories_emitted=(
            "artifact.crystalline_faceting",
            "artifact.crystalline_faceting.error",
        ),
        calibration_status=CALIBRATION_ADVISORY,
        deterministic=True,
        requires_dataset_context=True,
        requires_image_measurements=True,
        default_execution_policy=EXECUTION_ENABLED,
        default_display_policy=DISPLAY_VISIBLE,
        default_triage_policy=TRIAGE_INCLUDED,
    ),
    AnalyzerDescriptor(
        id="oversharpening_halo_analyzer",
        display_name="Oversharpening Halo Analyzer",
        description=(
            "Detects edge-localized residuals consistent with oversharpening "
            "and halo artifacts."
        ),
        version="v1",
        family=FAMILY_TECHNICAL_QUALITY,
        categories_emitted=(
            "artifact.oversharpening_halo",
            "artifact.oversharpening_halo.error",
        ),
        calibration_status=CALIBRATION_ADVISORY,
        deterministic=True,
        requires_dataset_context=False,
        requires_image_measurements=True,
        default_execution_policy=EXECUTION_ENABLED,
        default_display_policy=DISPLAY_VISIBLE,
        default_triage_policy=TRIAGE_INCLUDED,
    ),
    AnalyzerDescriptor(
        id="high_frequency_isolated_artifact_analyzer",
        display_name="High Frequency Isolated Artifact Analyzer",
        description=(
            "Detects sparse isolated high-frequency residual components such "
            "as bright or dark specks."
        ),
        version="v1",
        family=FAMILY_TECHNICAL_QUALITY,
        categories_emitted=(
            "artifact.high_frequency_isolated",
            "artifact.high_frequency_isolated.error",
        ),
        calibration_status=CALIBRATION_ADVISORY,
        deterministic=True,
        requires_dataset_context=False,
        requires_image_measurements=True,
        default_execution_policy=EXECUTION_ENABLED,
        default_display_policy=DISPLAY_VISIBLE,
        default_triage_policy=TRIAGE_INCLUDED,
    ),
    AnalyzerDescriptor(
        id="duplicate_detection_analyzer",
        display_name="Duplicate Detection Analyzer",
        description=(
            "Detects byte-identical and decoded pixel-identical duplicate "
            "images for advisory human review."
        ),
        version="v1",
        family=FAMILY_DATASET_STRUCTURE,
        categories_emitted=("dataset.duplicate.exact",),
        calibration_status=CALIBRATION_ADVISORY,
        deterministic=True,
        requires_dataset_context=True,
        requires_image_measurements=False,
        default_execution_policy=EXECUTION_ENABLED,
        default_display_policy=DISPLAY_VISIBLE,
        default_triage_policy=TRIAGE_INCLUDED,
    ),
    AnalyzerDescriptor(
        id="image_encoding_analyzer",
        display_name="Image Encoding Analyzer",
        description=(
            "Detects conservative source-encoding context that may explain "
            "texture, halo, crystalline, or high-frequency findings."
        ),
        version="v1",
        family=FAMILY_TECHNICAL_QUALITY,
        categories_emitted=(
            "source_encoding.jpeg_compression",
            "source_encoding.jpeg_blocking",
            "source_encoding.jpeg_ringing",
            "source_encoding.chroma_artifact",
            "source_encoding.banding",
            "source_encoding.low_source_quality",
        ),
        calibration_status=CALIBRATION_ADVISORY,
        deterministic=True,
        requires_dataset_context=False,
        requires_image_measurements=False,
        default_execution_policy=EXECUTION_ENABLED,
        default_display_policy=DISPLAY_VISIBLE,
        default_triage_policy=TRIAGE_INCLUDED,
    ),
    AnalyzerDescriptor(
        id="caption_metadata_analyzer",
        display_name="Caption / Metadata Analyzer",
        description=(
            "Inspects image-adjacent caption sidecars for deterministic "
            "metadata consistency signals."
        ),
        version="v1",
        family=FAMILY_METADATA,
        categories_emitted=(
            "caption.missing",
            "caption.empty",
            "caption.duplicate",
            "caption.short",
            "caption.long",
            "caption.token_imbalance",
        ),
        calibration_status=CALIBRATION_ADVISORY,
        deterministic=True,
        requires_dataset_context=True,
        requires_image_measurements=False,
        default_execution_policy=EXECUTION_ENABLED,
        default_display_policy=DISPLAY_VISIBLE,
        default_triage_policy=TRIAGE_INCLUDED,
    ),
    AnalyzerDescriptor(
        id="perceptual_duplicate_analyzer",
        display_name="Perceptual Near-Duplicate Analyzer",
        description=(
            "Detects conservative perceptual near-duplicate image groups for "
            "advisory human review."
        ),
        version="v1",
        family=FAMILY_DATASET_STRUCTURE,
        categories_emitted=("duplicate.perceptual",),
        calibration_status=CALIBRATION_ADVISORY,
        deterministic=True,
        requires_dataset_context=True,
        requires_image_measurements=False,
        default_execution_policy=EXECUTION_ENABLED,
        default_display_policy=DISPLAY_VISIBLE,
        default_triage_policy=TRIAGE_INCLUDED,
    ),
)

_DESCRIPTORS_BY_ID: Mapping[str, AnalyzerDescriptor] = {
    descriptor.id: descriptor
    for descriptor in BUILT_IN_ANALYZER_DESCRIPTORS
}


def built_in_descriptors() -> tuple[AnalyzerDescriptor, ...]:
    """Return built-in analyzer descriptors in stable descriptor order."""

    return BUILT_IN_ANALYZER_DESCRIPTORS


def descriptor_for_id(analyzer_id: str) -> AnalyzerDescriptor | None:
    """Return descriptor metadata for a built-in analyzer id, if known."""

    return _DESCRIPTORS_BY_ID.get(analyzer_id)


def descriptor_for_analyzer(analyzer: Analyzer) -> AnalyzerDescriptor:
    """Return descriptor metadata for an analyzer instance.

    Built-in analyzers must use the dedicated registry. Unknown test or
    development analyzers get a deterministic fallback descriptor so manifest
    tests can keep using local fixtures without registering fake analyzers.
    """

    descriptor = descriptor_for_id(str(analyzer.name))
    if descriptor is not None:
        return descriptor
    return fallback_descriptor_for_analyzer(analyzer)


def descriptors_for_analyzers(
    analyzers: Iterable[Analyzer],
) -> tuple[AnalyzerDescriptor, ...]:
    """Return descriptor metadata for analyzer instances in input order."""

    return tuple(descriptor_for_analyzer(analyzer) for analyzer in analyzers)


def fallback_descriptor_for_analyzer(analyzer: Analyzer) -> AnalyzerDescriptor:
    """Build deterministic metadata for unregistered test/development analyzers."""

    analyzer_id = str(analyzer.name)
    return AnalyzerDescriptor(
        id=analyzer_id,
        display_name=_display_name(analyzer_id),
        description="Unregistered analyzer metadata fallback.",
        version=str(analyzer.version),
        family=FAMILY_TECHNICAL_QUALITY,
        categories_emitted=tuple(
            str(category)
            for category in getattr(analyzer, "supported_categories", ())
        ),
        calibration_status=CALIBRATION_ADVISORY,
        deterministic=True,
        requires_dataset_context=True,
        requires_image_measurements=True,
        default_execution_policy=EXECUTION_ENABLED,
        default_display_policy=DISPLAY_VISIBLE,
        default_triage_policy=TRIAGE_INCLUDED,
    )


def _display_name(analyzer_id: str) -> str:
    return " ".join(part.capitalize() for part in analyzer_id.split("_"))


__all__ = [
    "AnalyzerDescriptor",
    "BUILT_IN_ANALYZER_DESCRIPTORS",
    "CALIBRATION_ADVISORY",
    "CALIBRATION_CALIBRATED",
    "CALIBRATION_EXPERIMENTAL",
    "DISPLAY_HIDDEN",
    "DISPLAY_VISIBLE",
    "EXECUTION_DISABLED",
    "EXECUTION_ENABLED",
    "FAMILY_DATASET_STRUCTURE",
    "FAMILY_DIVERSITY",
    "FAMILY_METADATA",
    "FAMILY_STYLE_CONSISTENCY",
    "FAMILY_TECHNICAL_QUALITY",
    "TRIAGE_EXCLUDED",
    "TRIAGE_INCLUDED",
    "built_in_descriptors",
    "descriptor_for_analyzer",
    "descriptor_for_id",
    "descriptors_for_analyzers",
    "fallback_descriptor_for_analyzer",
]
