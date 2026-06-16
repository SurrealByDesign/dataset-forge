from __future__ import annotations

from dataclasses import dataclass, field
import logging
from pathlib import Path
from typing import Any

from dataset_forge.core.structured import load_structured_file

LOGGER = logging.getLogger("dataset_forge.cleanup.profiles")
PROFILE_ALIASES = {
    "gpt_watercolor_microcleanup_light": "watercolor_microcleanup_light",
}

OPERATION_NAMES = (
    "median_filter",
    "bilateral_filter",
    "adaptive_bilateral",
    "isolated_pixel_removal",
    "speck_removal",
    "local_contrast_normalization",
    "edge_preserving_smoothing",
    "frequency_smoothing",
    "morphology_cleanup",
)


class CleanupProfileError(ValueError):
    """Raised when a cleanup profile file is missing or malformed."""


@dataclass(frozen=True)
class CleanupOperation:
    name: str
    parameters: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "parameters": dict(self.parameters)}


@dataclass(frozen=True)
class CleanupProfile:
    name: str
    description: str
    operations: tuple[CleanupOperation, ...]
    acceptance_checks: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "operations": [operation.to_dict() for operation in self.operations],
            "acceptance_checks": dict(self.acceptance_checks),
        }


def default_cleanup_profile_directory() -> Path:
    return Path(__file__).resolve().parents[3] / "presets" / "cleanup_profiles"


def load_cleanup_profile(
    value: str | Path, profile_directory: Path | None = None
) -> CleanupProfile:
    requested = str(value)
    if requested in PROFILE_ALIASES:
        replacement = PROFILE_ALIASES[requested]
        LOGGER.warning(
            "Cleanup profile '%s' is deprecated; use '%s' instead.",
            requested,
            replacement,
        )
        value = replacement
    source = _resolve_profile_path(value, profile_directory)
    try:
        data = load_structured_file(source)
    except ValueError as exc:
        raise CleanupProfileError(f"Could not read cleanup profile {source}: {exc}") from exc
    return _parse_profile(data, source)


def list_cleanup_profiles(profile_directory: Path | None = None) -> list[CleanupProfile]:
    directory = (profile_directory or default_cleanup_profile_directory()).resolve()
    if not directory.is_dir():
        raise CleanupProfileError(f"Cleanup profile folder does not exist: {directory}")
    return [load_cleanup_profile(path, directory) for path in sorted(directory.glob("*.json"))]


def _resolve_profile_path(value: str | Path, profile_directory: Path | None) -> Path:
    requested = Path(value).expanduser()
    if requested.is_file():
        return requested.resolve()

    directory = (profile_directory or default_cleanup_profile_directory()).resolve()
    filename = requested.name
    if not filename.lower().endswith(".json"):
        filename += ".json"
    candidate = directory / filename
    if candidate.is_file():
        return candidate.resolve()
    raise CleanupProfileError(
        f"Cleanup profile not found: {value}. Use a JSON file path or a name "
        "from the presets/cleanup_profiles directory."
    )


def _parse_profile(data: Any, source: Path) -> CleanupProfile:
    if not isinstance(data, dict):
        raise CleanupProfileError(f"Cleanup profile must be an object: {source}")

    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        raise CleanupProfileError(f"Cleanup profile 'name' must be a string: {source}")

    description = data.get("description", "")
    if not isinstance(description, str):
        raise CleanupProfileError(f"Cleanup profile 'description' must be a string: {source}")

    raw_operations = data.get("operations", [])
    if not isinstance(raw_operations, list):
        raise CleanupProfileError(f"Cleanup profile 'operations' must be a list: {source}")

    operations: list[CleanupOperation] = []
    for entry in raw_operations:
        if not isinstance(entry, dict):
            raise CleanupProfileError(f"Each cleanup operation must be an object: {source}")
        op_name = entry.get("name")
        if op_name not in OPERATION_NAMES:
            raise CleanupProfileError(
                f"Unsupported cleanup operation '{op_name}' in {source}. "
                f"Supported operations: {', '.join(OPERATION_NAMES)}."
            )
        parameters = entry.get("parameters", {})
        if not isinstance(parameters, dict):
            raise CleanupProfileError(
                f"Operation '{op_name}' parameters must be an object: {source}"
            )
        operations.append(CleanupOperation(name=op_name, parameters=dict(parameters)))

    acceptance_checks = data.get("acceptance_checks", {})
    if not isinstance(acceptance_checks, dict):
        raise CleanupProfileError(
            f"Cleanup profile 'acceptance_checks' must be an object: {source}"
        )
    parsed_checks: dict[str, float] = {}
    for key in (
        "max_average_pixel_difference",
        "max_color_histogram_difference",
        "max_edge_difference",
    ):
        value = acceptance_checks.get(key)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            raise CleanupProfileError(
                f"Acceptance threshold '{key}' must be non-negative: {source}"
            )
        parsed_checks[key] = float(value)

    return CleanupProfile(
        name=name,
        description=description,
        operations=tuple(operations),
        acceptance_checks=parsed_checks,
    )
