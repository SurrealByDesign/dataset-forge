"""Deterministic local classical preview generation.

This module creates disposable preview candidates only. It reads source images
and writes isolated preview artifacts through ``preview_artifacts.py``; it never
modifies source images, captions, metadata, or datasets.
"""

from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np
from PIL import Image, ImageFilter, UnidentifiedImageError

from dataset_forge import __version__
from dataset_forge.improvement_preview import (
    IMPROVEMENT_PREVIEW_SCHEMA,
    OPERATION_REDUCE_ENCODING_ARTIFACTS,
    OPERATION_REDUCE_HALO,
    PROVIDER_LOCAL_CLASSICAL,
)
from dataset_forge.preview_artifacts import (
    PreviewArtifactError,
    write_generated_preview_candidate,
)


LOCAL_CLASSICAL_PROVIDER_ID = "local_classical/v1"
LOCAL_CLASSICAL_PROVIDER_VERSION = "v1"
SUPPORTED_LOCAL_CLASSICAL_OPERATIONS = (
    OPERATION_REDUCE_HALO,
    OPERATION_REDUCE_ENCODING_ARTIFACTS,
)

_OPERATION_PARAMETERS: dict[str, dict[str, Any]] = {
    OPERATION_REDUCE_HALO: {
        "edge_blur_radius": 0.55,
        "edge_threshold": 0.09,
        "edge_blend_strength": 0.22,
    },
    OPERATION_REDUCE_ENCODING_ARTIFACTS: {
        "median_filter_size": 3,
        "blend_strength": 0.16,
    },
}


class LocalClassicalPreviewError(ValueError):
    """Raised when a local classical preview cannot be generated safely."""


def generate_local_classical_preview(
    inspect_output: Path,
    image_reference: Path | str,
    *,
    replace_existing: bool = False,
) -> dict[str, Any]:
    """Generate one deterministic LOCAL_CLASSICAL preview candidate."""

    root = inspect_output.expanduser().resolve()
    preview_path = root / "improvement_preview.json"
    preview = _load_preview(preview_path)
    source_path = Path(image_reference).expanduser().resolve(strict=True)
    record = _matching_record(preview, source_path)
    operation = str(record.get("recommended_operation", ""))
    provider_type = str(record.get("required_provider_type", ""))
    if provider_type != PROVIDER_LOCAL_CLASSICAL:
        raise LocalClassicalPreviewError(
            "preview record does not request LOCAL_CLASSICAL"
        )
    if operation not in SUPPORTED_LOCAL_CLASSICAL_OPERATIONS:
        raise LocalClassicalPreviewError(
            f"LOCAL_CLASSICAL does not support operation {operation!r}"
        )

    candidate_bytes = _render_candidate(source_path, operation)
    provider = {
        "type": PROVIDER_LOCAL_CLASSICAL,
        "display_name": "Local Classical Provider",
        "provider_id": LOCAL_CLASSICAL_PROVIDER_ID,
        "provider_version": LOCAL_CLASSICAL_PROVIDER_VERSION,
        "execution_available": False,
        "network_access": False,
        "credentials_required": False,
        "generative": False,
        "provenance_available": True,
        "deterministic": True,
    }
    generation = {
        "operation": operation,
        "provider_id": LOCAL_CLASSICAL_PROVIDER_ID,
        "provider_version": LOCAL_CLASSICAL_PROVIDER_VERSION,
        "tool": "dataset-forge",
        "tool_version": __version__,
        "deterministic": True,
        "parameters": _OPERATION_PARAMETERS[operation],
        "source_modified": False,
        "source_dataset_writes": False,
        "image_processing": "local_classical_preview",
    }
    return write_generated_preview_candidate(
        root,
        source_path,
        candidate_bytes,
        candidate_filename=_candidate_filename(operation),
        provider=provider,
        generation=generation,
        replace_existing=replace_existing,
    )


def _load_preview(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise LocalClassicalPreviewError(f"missing required improvement_preview.json: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LocalClassicalPreviewError("malformed JSON in improvement_preview.json") from exc
    if not isinstance(payload, dict):
        raise LocalClassicalPreviewError("improvement_preview.json must be a JSON object")
    if payload.get("schema") != IMPROVEMENT_PREVIEW_SCHEMA:
        raise LocalClassicalPreviewError(
            "unsupported improvement_preview.json schema "
            f"{payload.get('schema')!r}; expected {IMPROVEMENT_PREVIEW_SCHEMA!r}"
        )
    return payload


def _matching_record(preview: Mapping[str, Any], source_path: Path) -> Mapping[str, Any]:
    records = preview.get("preview_records")
    if not isinstance(records, list):
        records = preview.get("preview_entries", [])
    if not isinstance(records, list):
        raise LocalClassicalPreviewError("improvement_preview.json records must be a list")
    source_text = _canonical_path_text(source_path)
    matches = [
        record for record in records
        if isinstance(record, Mapping)
        and _canonical_path_text(Path(_record_image_path(record))) == source_text
    ]
    if not matches:
        raise LocalClassicalPreviewError(
            "no Improvement Preview record matches the requested image reference"
        )
    if len(matches) != 1:
        raise LocalClassicalPreviewError(
            "multiple Improvement Preview records match this image reference; generation is ambiguous"
        )
    return matches[0]


def _record_image_path(record: Mapping[str, Any]) -> str:
    image = record.get("image")
    if isinstance(image, Mapping) and isinstance(image.get("path"), str):
        return str(image["path"])
    value = record.get("image_path")
    return str(value) if isinstance(value, str) else ""


def _canonical_path_text(path: Path) -> str:
    return str(path.expanduser().resolve()).replace("\\", "/")


def _render_candidate(source_path: Path, operation: str) -> bytes:
    try:
        with Image.open(source_path) as image:
            source = image.convert("RGBA")
    except (OSError, UnidentifiedImageError) as exc:
        raise LocalClassicalPreviewError(f"source image is not readable: {source_path}") from exc
    if operation == OPERATION_REDUCE_HALO:
        candidate = _reduce_halo(source)
    elif operation == OPERATION_REDUCE_ENCODING_ARTIFACTS:
        candidate = _reduce_encoding_artifacts(source)
    else:
        raise LocalClassicalPreviewError(
            f"LOCAL_CLASSICAL does not support operation {operation!r}"
        )
    output = BytesIO()
    candidate.save(output, format="PNG", optimize=False, compress_level=9)
    return output.getvalue()


def _reduce_halo(image: Image.Image) -> Image.Image:
    params = _OPERATION_PARAMETERS[OPERATION_REDUCE_HALO]
    arr = np.asarray(image).astype(np.float32)
    rgb = arr[..., :3]
    alpha = arr[..., 3:4]
    luminance = (
        rgb[..., 0] * 0.2126
        + rgb[..., 1] * 0.7152
        + rgb[..., 2] * 0.0722
    ) / 255.0
    gy, gx = np.gradient(luminance)
    edge = np.sqrt(gx * gx + gy * gy)
    edge_mask = np.clip(
        (edge - float(params["edge_threshold"])) / 0.18,
        0.0,
        1.0,
    )[..., None]
    blurred = np.asarray(
        image.filter(ImageFilter.GaussianBlur(float(params["edge_blur_radius"])))
    ).astype(np.float32)[..., :3]
    blend = edge_mask * float(params["edge_blend_strength"])
    out_rgb = rgb * (1.0 - blend) + blurred * blend
    out = np.concatenate([out_rgb, alpha], axis=2)
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), mode="RGBA")


def _reduce_encoding_artifacts(image: Image.Image) -> Image.Image:
    params = _OPERATION_PARAMETERS[OPERATION_REDUCE_ENCODING_ARTIFACTS]
    arr = np.asarray(image).astype(np.float32)
    filtered = np.asarray(
        image.filter(ImageFilter.MedianFilter(int(params["median_filter_size"])))
    ).astype(np.float32)
    blend = float(params["blend_strength"])
    out = arr * (1.0 - blend) + filtered * blend
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), mode="RGBA")


def _candidate_filename(operation: str) -> str:
    return f"local-classical-{operation.lower().replace('_', '-')}.png"


__all__ = [
    "LOCAL_CLASSICAL_PROVIDER_ID",
    "LOCAL_CLASSICAL_PROVIDER_VERSION",
    "LocalClassicalPreviewError",
    "SUPPORTED_LOCAL_CLASSICAL_OPERATIONS",
    "generate_local_classical_preview",
]
