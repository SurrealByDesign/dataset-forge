"""Explicit per-image measurements shared across analyzers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dataset_forge.analysis.texture import TextureImageResult, evaluate_texture
from dataset_forge.measurement_cache import (
    build_cache_key,
    cache_is_enabled,
    file_sha256,
    read_cache_payload,
    write_cache_payload,
)

MEASUREMENT_SCHEMA_VERSION = 1
# Bump this whenever evaluate_texture scoring or preprocessing semantics change.
TEXTURE_MEASUREMENT_VERSION = "texture-v1"


@dataclass(frozen=True)
class ImageMeasurements:
    """Immutable measurements computed once for a single image."""

    image_path: Path
    texture: TextureImageResult


def measure_image(path: Path) -> ImageMeasurements:
    """Compute all currently supported image measurements."""
    resolved = path.expanduser().resolve()
    cache_lookup = _cache_lookup_values(resolved)
    if cache_lookup is not None:
        file_hash, cache_key = cache_lookup
        payload = read_cache_payload(
            cache_key,
            file_hash,
            MEASUREMENT_SCHEMA_VERSION,
            TEXTURE_MEASUREMENT_VERSION,
        )
        measurements = _measurements_from_payload(payload, resolved)
        if measurements is not None:
            return measurements

    measurements = ImageMeasurements(
        image_path=resolved,
        texture=evaluate_texture(resolved),
    )
    if cache_lookup is not None:
        file_hash, cache_key = cache_lookup
        write_cache_payload(
            cache_key,
            file_hash,
            MEASUREMENT_SCHEMA_VERSION,
            TEXTURE_MEASUREMENT_VERSION,
            _measurements_to_payload(measurements),
        )
    return measurements


def _cache_lookup_values(path: Path) -> tuple[str, str] | None:
    if not cache_is_enabled():
        return None
    try:
        file_hash = file_sha256(path)
    except OSError:
        return None
    return (
        file_hash,
        build_cache_key(
            file_hash,
            MEASUREMENT_SCHEMA_VERSION,
            TEXTURE_MEASUREMENT_VERSION,
        ),
    )


def _measurements_to_payload(measurements: ImageMeasurements) -> dict[str, Any]:
    return {
        "texture": measurements.texture.to_dict(),
    }


def _measurements_from_payload(
    payload: dict[str, Any] | None,
    image_path: Path,
) -> ImageMeasurements | None:
    if not isinstance(payload, dict):
        return None
    texture_payload = payload.get("texture")
    if not isinstance(texture_payload, dict):
        return None
    try:
        texture_data = dict(texture_payload)
        original_path = str(texture_data.get("original_path", ""))
        current_path = str(image_path)
        texture_data["filename"] = image_path.name
        texture_data["original_path"] = current_path
        if original_path and isinstance(texture_data.get("error"), str):
            texture_data["error"] = texture_data["error"].replace(
                original_path,
                current_path,
            )
        texture = TextureImageResult(**texture_data)
    except (TypeError, ValueError):
        return None
    return ImageMeasurements(image_path=image_path, texture=texture)


__all__ = [
    "ImageMeasurements",
    "MEASUREMENT_SCHEMA_VERSION",
    "TEXTURE_MEASUREMENT_VERSION",
    "measure_image",
]
