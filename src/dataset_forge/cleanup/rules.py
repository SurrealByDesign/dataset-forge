from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dataset_forge.core.structured import load_structured_file
from dataset_forge.cleanup.models import CleanupAction


@dataclass(frozen=True)
class CleanupRules:
    artifact_light: float
    artifact_medium: float
    artifact_strong: float
    texture_light: float
    very_low_resolution_mp: float
    low_resolution_mp: float
    healthy_quality: float
    conflicting_margin: float
    confidence_base: int
    confidence_margin_scale: float
    quality_gain_light: float
    quality_gain_medium: float
    quality_gain_strong: float
    quality_gain_caption: float
    exact_duplicate_action: str
    very_low_resolution_action: str
    presets: dict[str, str]
    capabilities: dict[str, str]


def default_cleanup_rules_path() -> Path:
    return Path(__file__).resolve().parents[1] / "config" / "cleanup_rules.json"


def load_cleanup_rules(path: Path | None = None) -> CleanupRules:
    source = path or default_cleanup_rules_path()
    data = load_structured_file(source)
    thresholds = _mapping(data, "thresholds", source)
    benefits = _mapping(data, "quality_gains", source)
    actions = _mapping(data, "actions", source)
    presets = _string_mapping(data, "presets", source)
    capabilities = _string_mapping(data, "capabilities", source)
    rules = CleanupRules(
        artifact_light=_number(thresholds, "artifact_light", source),
        artifact_medium=_number(thresholds, "artifact_medium", source),
        artifact_strong=_number(thresholds, "artifact_strong", source),
        texture_light=_number(thresholds, "texture_light", source),
        very_low_resolution_mp=_number(
            thresholds,
            "very_low_resolution_mp",
            source,
        ),
        low_resolution_mp=_number(thresholds, "low_resolution_mp", source),
        healthy_quality=_number(thresholds, "healthy_quality", source),
        conflicting_margin=_number(thresholds, "conflicting_margin", source),
        confidence_base=int(_number(data, "confidence_base", source)),
        confidence_margin_scale=_number(data, "confidence_margin_scale", source),
        quality_gain_light=_number(benefits, "light", source),
        quality_gain_medium=_number(benefits, "medium", source),
        quality_gain_strong=_number(benefits, "strong", source),
        quality_gain_caption=_number(benefits, "caption_only", source),
        exact_duplicate_action=_string(actions, "exact_duplicate", source),
        very_low_resolution_action=_string(
            actions,
            "very_low_resolution",
            source,
        ),
        presets=presets,
        capabilities=capabilities,
    )
    if not rules.artifact_light < rules.artifact_medium < rules.artifact_strong:
        raise ValueError(
            "artifact thresholds must increase from light to medium to strong."
        )
    if rules.very_low_resolution_mp >= rules.low_resolution_mp:
        raise ValueError(
            "very_low_resolution_mp must be below low_resolution_mp."
        )
    for action in (
        rules.exact_duplicate_action,
        rules.very_low_resolution_action,
    ):
        try:
            CleanupAction(action)
        except ValueError as exc:
            raise ValueError(f"Unsupported cleanup action in rules: {action}") from exc
    return rules


def _mapping(data: dict[str, Any], key: str, source: Path) -> dict[str, Any]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"Cleanup rules '{key}' must be an object: {source}")
    return value


def _string_mapping(
    data: dict[str, Any],
    key: str,
    source: Path,
) -> dict[str, str]:
    values = _mapping(data, key, source)
    if not all(isinstance(name, str) and isinstance(value, str) for name, value in values.items()):
        raise ValueError(f"Cleanup rules '{key}' values must be strings: {source}")
    return dict(values)


def _number(data: dict[str, Any], key: str, source: Path) -> float:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Cleanup rule '{key}' must be numeric: {source}")
    return float(value)


def _string(data: dict[str, Any], key: str, source: Path) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Cleanup rule '{key}' must be a string: {source}")
    return value
