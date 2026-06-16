"""The sole policy engine that converts Evidence into recommendations."""

from __future__ import annotations

from dataclasses import dataclass
import statistics
from typing import Any, Mapping

from dataset_forge.evidence import Evidence, ImageEvidence


@dataclass(frozen=True)
class EvidenceRecommendation:
    image_id: str
    filename: str
    action: str
    severity: str
    issue: str
    explanation: str
    confidence: int
    suggested_preset: str = ""
    suggested_strength: str = ""


def recommend_evidence(
    evidence: Evidence,
    *,
    rules: Any | None = None,
) -> list[EvidenceRecommendation]:
    """Return exactly one authoritative recommendation for each image."""
    return [_recommend_image(image, evidence, rules) for image in evidence.images]


def recommend_dataset(
    evidence: Evidence,
    decisions: list[EvidenceRecommendation] | None = None,
) -> list[str]:
    """Produce dataset-level guidance from the same evidence and policy surface."""
    if not evidence.images:
        return ["No readable images were available for analysis."]
    decisions = decisions if decisions is not None else recommend_evidence(evidence)
    metrics = evidence.dataset_metrics
    guidance: list[str] = []
    health = float(metrics.get("dataset_health_score", 100) or 0)
    cleanup_count = sum(
        item.action
        in {
            "CLEAN_LIGHT",
            "CLEAN_MEDIUM",
            "CLEAN_STRONG",
            "TEXTURE_NORMALIZE_LIGHT",
            "TEXTURE_NORMALIZE_MEDIUM",
        }
        for item in decisions
    )
    duplicate_count = sum(
        item.action in {"EXCLUDE", "DUPLICATE_REVIEW"} for item in decisions
    )
    low_resolution_count = sum(
        _number(item.quality_metrics, "megapixels") < 1
        for item in evidence.images
        if "megapixels" in item.quality_metrics
    )
    if "dataset_health_score" in metrics and health < 60:
        guidance.append("Prioritize critical and warning items before dataset use.")
    if cleanup_count:
        guidance.append(
            f"Review {cleanup_count} image(s) recommended for non-destructive cleanup."
        )
    if duplicate_count:
        guidance.append(
            f"Review {duplicate_count} likely duplicate image(s) before selecting data."
        )
    if low_resolution_count:
        guidance.append(
            f"Review {low_resolution_count} image(s) below 1 megapixel."
        )
    if float(metrics.get("average_artifact_score", 0) or 0) >= 50:
        guidance.append("The dataset has an elevated average artifact burden.")
    if float(metrics.get("average_texture_score", 0) or 0) >= 65:
        guidance.append("The dataset has an elevated average texture burden.")
    aspect_ratios = {
        round(_number(item.quality_metrics, "aspect_ratio"), 1)
        for item in evidence.images
        if "aspect_ratio" in item.quality_metrics
    }
    if len(aspect_ratios) >= 3:
        guidance.append(
            "Mixed aspect ratios: consider grouping crops for workflows that need consistency."
        )
    brightness = [
        _number(item.quality_metrics, "average_brightness")
        for item in evidence.images
        if "average_brightness" in item.quality_metrics
    ]
    if len(brightness) > 1 and (
        max(brightness) - min(brightness) >= 30
        or statistics.pstdev(brightness) >= 15
    ):
        guidance.append(
            "Strong brightness variation: inspect very dark and very bright images for consistency."
        )
    if not guidance:
        guidance.append("No major dataset-level issues require immediate review.")
    return guidance


def _recommend_image(
    image: ImageEvidence,
    evidence: Evidence,
    rules: Any | None,
) -> EvidenceRecommendation:
    quality = image.quality_metrics
    artifact = image.artifact_metrics
    texture = image.texture_metrics
    relative = image.dataset_relative_metrics

    if image.status == "error":
        return _decision(
            image,
            "MANUAL_REVIEW",
            "CRITICAL",
            "Unreadable image",
            "The image could not be read or analyzed reliably.",
            99,
        )
    if quality.get("exact_duplicate_of"):
        return _decision(
            image,
            "EXCLUDE",
            "CRITICAL",
            "Exact duplicate",
            f"File content matches {quality['exact_duplicate_of']}.",
            99,
        )
    if quality.get("probable_duplicate_of"):
        return _decision(
            image,
            "DUPLICATE_REVIEW",
            "WARNING",
            "Probable duplicate",
            f"Visual hash is similar to {quality['probable_duplicate_of']}.",
            90,
        )

    megapixels = _number(quality, "megapixels")
    very_low_mp = _rule(rules, "very_low_resolution_mp", 0.25)
    low_mp = _rule(rules, "low_resolution_mp", 1.0)
    if megapixels and megapixels < very_low_mp:
        return _decision(
            image,
            "REGENERATE",
            "CRITICAL",
            "Very low resolution",
            f"Image resolution is {megapixels:.3f} MP, below {very_low_mp:.2f} MP.",
            _confidence(rules, very_low_mp - megapixels, scale=100),
        )

    artifact_score = _number(artifact, "artifact_score")
    legacy_texture = _number(texture, "texture_score")
    microtexture = _number(texture, "microtexture_density_score")
    highlight_speck = _number(texture, "highlight_speck_score")
    edge_sharpness = _number(texture, "edge_sharpness_score")
    texture_average = float(
        evidence.dataset_metrics.get("average_microtexture_density", 0) or 0
    )
    texture_deviation = float(
        evidence.dataset_metrics.get("microtexture_standard_deviation", 0) or 0
    )

    if microtexture or highlight_speck or edge_sharpness:
        high = texture_average + max(10.0, texture_deviation)
        very_high = texture_average + max(20.0, 1.6 * texture_deviation)
        if (
            highlight_speck >= 55
            or microtexture >= very_high and edge_sharpness >= 75
        ):
            return _texture_decision(
                image,
                "MANUAL_REVIEW",
                "Texture signals require review",
                microtexture,
                texture_average,
                82,
            )
        if highlight_speck >= 28 or microtexture >= high:
            return _texture_decision(
                image,
                "TEXTURE_NORMALIZE_MEDIUM",
                "Elevated texture burden",
                microtexture,
                texture_average,
                84,
            )
        if (
            highlight_speck >= 12
            or microtexture >= texture_average + max(6.0, 0.5 * texture_deviation)
        ):
            return _texture_decision(
                image,
                "TEXTURE_NORMALIZE_LIGHT",
                "Mild texture burden",
                microtexture,
                texture_average,
                78,
            )

    required = (
        "overall_quality_score",
        "megapixels",
    )
    has_quality_context = any(name in quality for name in required)
    if rules is not None and (
        not has_quality_context
        or "artifact_score" not in artifact
        or "texture_score" not in texture
    ):
        return _decision(
            image,
            "MANUAL_REVIEW",
            "WARNING",
            "Missing analysis evidence",
            "Required quality, artifact, texture, or resolution metrics are missing.",
            96,
        )

    artifact_strong = _rule(rules, "artifact_strong", 75)
    artifact_medium = _rule(rules, "artifact_medium", 55)
    artifact_light = _rule(rules, "artifact_light", 45)
    texture_light = _rule(rules, "texture_light", 75)
    if artifact_score >= artifact_strong:
        return _decision(
            image,
            "CLEAN_STRONG",
            "CRITICAL",
            "High artifact burden",
            _artifact_explanation(artifact_score, evidence),
            _confidence(rules, artifact_score - artifact_strong),
            "general_artifact_cleanup",
            "strong",
        )
    if artifact_score >= artifact_medium:
        return _decision(
            image,
            "CLEAN_MEDIUM",
            "WARNING",
            "Elevated artifact burden",
            _artifact_explanation(artifact_score, evidence),
            _confidence(rules, artifact_score - artifact_medium),
            "general_artifact_cleanup",
            "medium",
        )
    if artifact_score >= artifact_light:
        return _decision(
            image,
            "CLEAN_LIGHT",
            "WARNING",
            "Mild artifact burden",
            _artifact_explanation(artifact_score, evidence),
            _confidence(rules, artifact_score - artifact_light),
            "general_artifact_cleanup",
            "light",
        )
    if legacy_texture >= texture_light:
        return _decision(
            image,
            "TEXTURE_NORMALIZE_LIGHT",
            "WARNING",
            "High texture burden",
            f"Texture score is {legacy_texture:.2f}/100.",
            _confidence(rules, legacy_texture - texture_light),
            "general_artifact_cleanup",
            "light",
        )
    if megapixels and megapixels < low_mp:
        return _decision(
            image,
            "MANUAL_REVIEW",
            "WARNING",
            "Low resolution",
            f"Image resolution is below {low_mp:g} megapixel.",
            70,
        )
    if _number(quality, "brightness_consistency_score", 100) < 60:
        return _decision(
            image,
            "MANUAL_REVIEW",
            "WARNING",
            "Brightness outlier",
            "Brightness differs substantially from the dataset median.",
            70,
        )
    if _number(quality, "contrast_score", 100) < 60:
        return _decision(
            image,
            "MANUAL_REVIEW",
            "WARNING",
            "Contrast outlier",
            "Contrast differs substantially from the dataset or useful range.",
            70,
        )
    return _decision(
        image,
        "KEEP",
        "INFO",
        "No major quality issue",
        "Available evidence does not justify processing.",
        90,
    )


def _texture_decision(
    image: ImageEvidence,
    action: str,
    issue: str,
    microtexture: float,
    average: float,
    confidence: int,
) -> EvidenceRecommendation:
    relation = (
        "above"
        if microtexture > average + 2
        else "below"
        if microtexture < average - 2
        else "near"
    )
    detail = (
        f"Microtexture is {relation} the dataset average "
        f"({microtexture:.1f} versus {average:.1f}). "
    )
    endings = {
        "KEEP": "Leave this image unchanged.",
        "TEXTURE_NORMALIZE_LIGHT": (
            "A light normalization pass may reduce mild fine grain or bright specks."
        ),
        "TEXTURE_NORMALIZE_MEDIUM": (
            "Fine texture or bright specks justify moderate normalization."
        ),
        "MANUAL_REVIEW": (
            "Texture and edge signals are unusually strong or conflicting."
        ),
    }
    return _decision(
        image,
        action,
        "WARNING" if action != "KEEP" else "INFO",
        issue,
        detail + endings[action],
        confidence,
        "watercolor_pencil_cleanup" if action.startswith("TEXTURE_") else "",
        "medium" if action.endswith("MEDIUM") else "light" if action.endswith("LIGHT") else "",
    )


def _decision(
    image: ImageEvidence,
    action: str,
    severity: str,
    issue: str,
    explanation: str,
    confidence: int,
    preset: str = "",
    strength: str = "",
) -> EvidenceRecommendation:
    return EvidenceRecommendation(
        image_id=image.image_id,
        filename=image.filename,
        action=action,
        severity=severity,
        issue=issue,
        explanation=explanation,
        confidence=max(0, min(100, int(round(confidence)))),
        suggested_preset=preset,
        suggested_strength=strength,
    )


def _artifact_explanation(score: float, evidence: Evidence) -> str:
    average = float(evidence.dataset_metrics.get("average_artifact_score", 0) or 0)
    if average > 0:
        difference = (score - average) / average * 100
        return f"Artifact score is {score:.1f}, {difference:.0f}% above the dataset average."
    return f"Artifact score is {score:.2f}/100."


def _number(values: Mapping[str, Any], key: str, default: float = 0.0) -> float:
    try:
        value = values.get(key, default)
        return default if value in ("", None) else float(value)
    except (TypeError, ValueError):
        return default


def _rule(rules: Any | None, name: str, default: float) -> float:
    return float(getattr(rules, name, default)) if rules is not None else default


def _confidence(
    rules: Any | None,
    margin: float,
    *,
    scale: float = 1.0,
) -> int:
    base = float(getattr(rules, "confidence_base", 68))
    margin_scale = float(getattr(rules, "confidence_margin_scale", 1.2))
    return min(97, int(round(base + max(0.0, margin) * margin_scale * scale)))


# Compatibility exports remain available from their historical module.
from dataset_forge.analysis.quality import (  # noqa: E402
    HealthSummary,
    Recommendation,
    assess_dataset_quality,
    write_health_report,
    write_recommendations,
)

__all__ = [
    "EvidenceRecommendation",
    "HealthSummary",
    "Recommendation",
    "assess_dataset_quality",
    "recommend_evidence",
    "recommend_dataset",
    "write_health_report",
    "write_recommendations",
]
