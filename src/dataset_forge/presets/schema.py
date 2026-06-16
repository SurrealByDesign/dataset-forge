from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

REQUIRED_FIELDS = ("name", "description", "prompt", "negative_prompt")
STRENGTH_NAMES = ("light", "medium", "strong")


class PresetError(ValueError):
    """Raised when a preset cannot be found, read, or validated."""


@dataclass(frozen=True)
class TransformSpec:
    name: str
    parameters: dict[str, Any]


@dataclass(frozen=True)
class Preset:
    name: str
    description: str
    prompt: str
    negative_prompt: str
    transforms: tuple[TransformSpec, ...]
    strengths: dict[str, float]
    notes: str
    source: Path


def validate_preset(data: Any, source: Path) -> Preset:
    if not isinstance(data, dict):
        raise PresetError(f"Preset {source} must contain a JSON object.")

    missing = [field for field in REQUIRED_FIELDS if field not in data]
    if missing:
        raise PresetError(
            f"Preset {source} is missing required field(s): {', '.join(missing)}."
        )

    for field in REQUIRED_FIELDS:
        if not isinstance(data[field], str):
            raise PresetError(f"Preset field '{field}' must be a string: {source}")

    notes = data.get("notes", "")
    if not isinstance(notes, str):
        raise PresetError(f"Preset field 'notes' must be a string: {source}")

    strengths = _validate_strengths(data.get("strengths"), source)
    transforms = _validate_transforms(data.get("transforms", []), source)
    return Preset(
        name=data["name"],
        description=data["description"],
        prompt=data["prompt"],
        negative_prompt=data["negative_prompt"],
        transforms=transforms,
        strengths=strengths,
        notes=notes,
        source=source,
    )


def _validate_strengths(value: Any, source: Path) -> dict[str, float]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise PresetError(f"Preset field 'strengths' must be an object: {source}")
    missing = [name for name in STRENGTH_NAMES if name not in value]
    if missing:
        raise PresetError(
            f"Preset {source} is missing strength(s): {', '.join(missing)}."
        )
    normalized: dict[str, float] = {}
    for name in STRENGTH_NAMES:
        strength = value[name]
        if isinstance(strength, bool) or not isinstance(strength, (int, float)):
            raise PresetError(f"Preset strength '{name}' must be a number: {source}")
        if not 0 <= strength <= 1:
            raise PresetError(
                f"Preset strength '{name}' must be between 0 and 1: {source}"
            )
        normalized[name] = float(strength)
    return normalized


def _validate_transforms(value: Any, source: Path) -> tuple[TransformSpec, ...]:
    if not isinstance(value, list):
        raise PresetError(f"Preset field 'transforms' must be a list: {source}")
    transforms: list[TransformSpec] = []
    for index, item in enumerate(value):
        label = f"Preset transform at index {index}"
        if not isinstance(item, dict):
            raise PresetError(f"{label} must be an object: {source}")
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            raise PresetError(f"{label} must have a non-empty string name: {source}")
        parameters = {key: parameter for key, parameter in item.items() if key != "name"}
        for key in parameters:
            if not isinstance(key, str) or not key:
                raise PresetError(f"{label} parameter names must be strings: {source}")
        strength = parameters.get("strength")
        if strength is not None and (
            isinstance(strength, bool)
            or not isinstance(strength, (int, float))
            or not 0 <= strength <= 100
        ):
            raise PresetError(
                f"{label} strength must be a number between 0 and 100: {source}"
            )
        transforms.append(TransformSpec(name=name, parameters=parameters))
    return tuple(transforms)

