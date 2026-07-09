"""Image encoding analyzer.

Detects conservative source-encoding context that may explain texture, halo,
crystalline, or high-frequency findings. JPEG presence alone is not a finding.
The analyzer is advisory and read-only: it never repairs, denoises, upscales,
excludes, exports, or modifies files.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
from PIL import Image, ImageOps

from dataset_forge.analyzers.base import Analyzer
from dataset_forge.context import DatasetContext
from dataset_forge.finding import Finding, Severity

if TYPE_CHECKING:
    from dataset_forge.measurements import ImageMeasurements


BENCHMARK_VERSION = "advisory-encoding-v1"

_UNCALIBRATED_FP_RATE = 0.35
_UNCALIBRATED_MAX_CONFIDENCE = 0.48
_ANALYSIS_MAX_SIZE = 768

_LOW_JPEG_QUALITY_THRESHOLD = 45
_MEDIUM_JPEG_QUALITY_THRESHOLD = 30
_LOW_BYTES_PER_PIXEL_JPEG_WITHOUT_QUALITY = 0.035

_BLOCKING_RATIO_LOW = 1.35
_BLOCKING_SCORE_LOW = 4.0
_BLOCKING_RATIO_MEDIUM = 1.75
_BLOCKING_SCORE_MEDIUM = 7.0

_RINGING_SCORE_LOW = 9.0
_RINGING_SCORE_MEDIUM = 14.0
_MOSQUITO_SCORE_LOW = 0.020
_MOSQUITO_SCORE_MEDIUM = 0.045

_CHROMA_SCORE_LOW = 7.0
_CHROMA_SCORE_MEDIUM = 12.0

_BANDING_SCORE_LOW = 0.55
_BANDING_SCORE_MEDIUM = 0.72
_BANDING_MAX_UNIQUE_TONES = 48
_BANDING_MIN_TONAL_RANGE = 64

_LOW_SOURCE_PIXEL_COUNT = 32_768
_LOW_SOURCE_MIN_DIMENSION = 160


@dataclass(frozen=True)
class EncodingMeasurement:
    status: str
    error: str = ""
    image_format: str = "UNKNOWN"
    width: int = 0
    height: int = 0
    pixel_count: int = 0
    file_size_bytes: int = 0
    bytes_per_pixel: float = 0.0
    is_jpeg: bool = False
    quantization_table_available: bool = False
    approximate_jpeg_quality: int | None = None
    jpeg_quality_estimate_note: str = "not_available"
    chroma_subsampling: str = "not_available"
    block_boundary_score: float = 0.0
    block_interior_score: float = 0.0
    blocking_ratio: float = 0.0
    edge_ringing_score: float = 0.0
    mosquito_noise_score: float = 0.0
    chroma_artifact_score: float = 0.0
    banding_score: float = 0.0
    unique_tone_count: int = 0
    tonal_range: float = 0.0
    low_resolution_source: bool = False


class ImageEncodingAnalyzer(Analyzer):
    """Detect conservative source-encoding context for human review."""

    @property
    def name(self) -> str:
        return "image_encoding_analyzer"

    @property
    def version(self) -> str:
        return "v1"

    @property
    def supported_categories(self) -> tuple[str, ...]:
        return (
            "source_encoding.jpeg_compression",
            "source_encoding.jpeg_blocking",
            "source_encoding.jpeg_ringing",
            "source_encoding.chroma_artifact",
            "source_encoding.banding",
            "source_encoding.low_source_quality",
        )

    @property
    def benchmark_version(self) -> str | None:
        return None

    def analyze(
        self,
        image_path: Path,
        context: DatasetContext,
        measurements: ImageMeasurements | None = None,
    ) -> list[Finding]:
        del context, measurements
        result = measure_image_encoding(image_path)
        if result.status != "analyzed":
            return []

        findings: list[Finding] = []
        findings.extend(_jpeg_compression_finding(image_path, self.analyzer_id, result))
        findings.extend(_jpeg_blocking_finding(image_path, self.analyzer_id, result))
        findings.extend(_jpeg_ringing_finding(image_path, self.analyzer_id, result))
        findings.extend(_chroma_artifact_finding(image_path, self.analyzer_id, result))
        findings.extend(_banding_finding(image_path, self.analyzer_id, result))
        findings.extend(_low_source_quality_finding(image_path, self.analyzer_id, result))
        return findings


def measure_image_encoding(path: Path) -> EncodingMeasurement:
    """Measure source-encoding context without modifying the source image."""

    resolved = path.expanduser().resolve()
    try:
        file_size = resolved.stat().st_size
        with Image.open(resolved) as opened:
            image_format = str(opened.format or resolved.suffix.lstrip(".") or "unknown").upper()
            is_jpeg = image_format in {"JPEG", "JPG"} or resolved.suffix.casefold() in {
                ".jpg",
                ".jpeg",
            }
            quantization = getattr(opened, "quantization", None) or {}
            quality = _estimate_jpeg_quality(quantization) if is_jpeg else None
            subsampling = _chroma_subsampling(opened) if is_jpeg else "not_applicable"
            image = ImageOps.exif_transpose(opened).convert("RGB")
            width, height = image.size
            pixel_count = width * height
            analysis = image.copy()
            analysis.thumbnail((_ANALYSIS_MAX_SIZE, _ANALYSIS_MAX_SIZE), Image.Resampling.LANCZOS)
            rgb = np.asarray(analysis, dtype=np.float32)
    except (OSError, ValueError) as exc:
        return EncodingMeasurement(status="error", error=str(exc))

    gray = _rgb_to_gray(rgb)
    block_boundary_score, block_interior_score, blocking_ratio = _blocking_metrics(gray)
    edge_ringing_score, mosquito_noise_score = _edge_noise_metrics(gray)
    chroma_artifact_score = _chroma_artifact_score(rgb, gray)
    banding_score, unique_tone_count, tonal_range = _banding_metrics(gray)
    bytes_per_pixel = round(file_size / max(1, pixel_count), 6)
    low_resolution_source = pixel_count <= _LOW_SOURCE_PIXEL_COUNT or min(width, height) < _LOW_SOURCE_MIN_DIMENSION

    return EncodingMeasurement(
        status="analyzed",
        image_format=image_format,
        width=width,
        height=height,
        pixel_count=pixel_count,
        file_size_bytes=file_size,
        bytes_per_pixel=bytes_per_pixel,
        is_jpeg=is_jpeg,
        quantization_table_available=bool(quantization),
        approximate_jpeg_quality=quality,
        jpeg_quality_estimate_note=(
            "approximate_from_quantization_tables" if quality is not None else "not_available"
        ),
        chroma_subsampling=subsampling,
        block_boundary_score=round(block_boundary_score, 4),
        block_interior_score=round(block_interior_score, 4),
        blocking_ratio=round(blocking_ratio, 4),
        edge_ringing_score=round(edge_ringing_score, 4),
        mosquito_noise_score=round(mosquito_noise_score, 6),
        chroma_artifact_score=round(chroma_artifact_score, 4),
        banding_score=round(banding_score, 4),
        unique_tone_count=unique_tone_count,
        tonal_range=round(tonal_range, 4),
        low_resolution_source=low_resolution_source,
    )


def _jpeg_compression_finding(
    image_path: Path,
    analyzer_id: str,
    result: EncodingMeasurement,
) -> list[Finding]:
    if not result.is_jpeg:
        return []
    quality = result.approximate_jpeg_quality
    if not (
        (quality is not None and quality <= _LOW_JPEG_QUALITY_THRESHOLD)
        or (
            quality is None
            and result.bytes_per_pixel <= _LOW_BYTES_PER_PIXEL_JPEG_WITHOUT_QUALITY
        )
    ):
        return []
    severity = Severity.MEDIUM if quality is not None and quality <= _MEDIUM_JPEG_QUALITY_THRESHOLD else Severity.LOW
    explanation = (
        "Compression artifacts detected. This does not mean JPEG is unsuitable; "
        "it may explain other visual findings. "
        f"Approximate JPEG quality is {quality if quality is not None else 'not available'} "
        f"and bytes per pixel is {result.bytes_per_pixel:.3f}."
    )
    recommendation = (
        "Use this as source-encoding context while reviewing texture, halo, "
        "crystalline, or high-frequency findings. Dataset Forge does not "
        "repair, denoise, exclude, export, or modify the image automatically."
    )
    return [_finding(image_path, analyzer_id, "source_encoding.jpeg_compression", severity, result, explanation, recommendation)]


def _jpeg_blocking_finding(
    image_path: Path,
    analyzer_id: str,
    result: EncodingMeasurement,
) -> list[Finding]:
    if not result.is_jpeg:
        return []
    if result.blocking_ratio < _BLOCKING_RATIO_LOW or result.block_boundary_score < _BLOCKING_SCORE_LOW:
        return []
    severity = (
        Severity.MEDIUM
        if result.blocking_ratio >= _BLOCKING_RATIO_MEDIUM and result.block_boundary_score >= _BLOCKING_SCORE_MEDIUM
        else Severity.LOW
    )
    explanation = (
        "8x8 block boundary evidence was detected. Source encoding evidence "
        "may explain texture, halo, crystalline, or high-frequency findings. "
        f"Block boundary score is {result.block_boundary_score:.2f}, interior "
        f"score is {result.block_interior_score:.2f}, and blocking ratio is "
        f"{result.blocking_ratio:.2f}."
    )
    recommendation = (
        "Review visually before deciding. Blocking is a review signal only, "
        "not an automatic defect or exclusion."
    )
    return [_finding(image_path, analyzer_id, "source_encoding.jpeg_blocking", severity, result, explanation, recommendation)]


def _jpeg_ringing_finding(
    image_path: Path,
    analyzer_id: str,
    result: EncodingMeasurement,
) -> list[Finding]:
    if not result.is_jpeg:
        return []
    if result.edge_ringing_score < _RINGING_SCORE_LOW and result.mosquito_noise_score < _MOSQUITO_SCORE_LOW:
        return []
    severity = (
        Severity.MEDIUM
        if result.edge_ringing_score >= _RINGING_SCORE_MEDIUM or result.mosquito_noise_score >= _MOSQUITO_SCORE_MEDIUM
        else Severity.LOW
    )
    explanation = (
        "Edge-adjacent ringing or mosquito-noise evidence was detected. This "
        "may indicate JPEG compression around hard edges, or intentional hard "
        "edge illustration texture. "
        f"Ringing score is {result.edge_ringing_score:.2f}; mosquito-noise "
        f"score is {result.mosquito_noise_score:.4f}."
    )
    recommendation = (
        "Treat this as encoding context for human review. Leave the image alone "
        "if the edge texture is stylistically intentional."
    )
    return [_finding(image_path, analyzer_id, "source_encoding.jpeg_ringing", severity, result, explanation, recommendation)]


def _chroma_artifact_finding(
    image_path: Path,
    analyzer_id: str,
    result: EncodingMeasurement,
) -> list[Finding]:
    if not result.is_jpeg or result.chroma_artifact_score < _CHROMA_SCORE_LOW:
        return []
    severity = Severity.MEDIUM if result.chroma_artifact_score >= _CHROMA_SCORE_MEDIUM else Severity.LOW
    explanation = (
        "Localized chroma residual evidence was detected near luminance edges. "
        "This may reflect JPEG chroma artifacts or intentional color texture. "
        f"Chroma artifact score is {result.chroma_artifact_score:.2f}; "
        f"subsampling is {result.chroma_subsampling}."
    )
    recommendation = (
        "Review visually before deciding. Chroma evidence is advisory and does "
        "not imply cleanup, repair, or exclusion."
    )
    return [_finding(image_path, analyzer_id, "source_encoding.chroma_artifact", severity, result, explanation, recommendation)]


def _banding_finding(
    image_path: Path,
    analyzer_id: str,
    result: EncodingMeasurement,
) -> list[Finding]:
    if result.banding_score < _BANDING_SCORE_LOW:
        return []
    if result.unique_tone_count > _BANDING_MAX_UNIQUE_TONES:
        return []
    if result.tonal_range < _BANDING_MIN_TONAL_RANGE:
        return []
    severity = Severity.MEDIUM if result.banding_score >= _BANDING_SCORE_MEDIUM else Severity.LOW
    explanation = (
        "Posterization or banding evidence was detected in broad tonal areas. "
        f"Banding score is {result.banding_score:.2f}, with "
        f"{result.unique_tone_count} observed luminance tones across a tonal "
        f"range of {result.tonal_range:.1f}."
    )
    recommendation = (
        "Use this as source-encoding context. Banding may be compression, a "
        "source limitation, or deliberate posterized style."
    )
    return [_finding(image_path, analyzer_id, "source_encoding.banding", severity, result, explanation, recommendation)]


def _low_source_quality_finding(
    image_path: Path,
    analyzer_id: str,
    result: EncodingMeasurement,
) -> list[Finding]:
    if not result.low_resolution_source:
        return []
    compressed_tiny_jpeg = result.is_jpeg and (
        result.bytes_per_pixel <= 0.85
        or (
            result.approximate_jpeg_quality is not None
            and result.approximate_jpeg_quality <= _LOW_JPEG_QUALITY_THRESHOLD
        )
    )
    if not compressed_tiny_jpeg:
        return []
    explanation = (
        "Small or heavily compressed source characteristics detected. Treat as "
        "review context, not an automatic exclusion. "
        f"Image dimensions are {result.width}x{result.height}, pixel count is "
        f"{result.pixel_count}, and bytes per pixel is {result.bytes_per_pixel:.3f}."
    )
    recommendation = (
        "Review whether this source fits your dataset goal. Dataset Forge does "
        "not upscale, repair, move, exclude, export, or modify the file."
    )
    return [_finding(image_path, analyzer_id, "source_encoding.low_source_quality", Severity.LOW, result, explanation, recommendation)]


def _finding(
    image_path: Path,
    analyzer_id: str,
    category: str,
    severity: Severity,
    result: EncodingMeasurement,
    explanation: str,
    recommendation: str,
) -> Finding:
    return Finding(
        image_path=image_path,
        analyzer=analyzer_id,
        category=category,
        severity=severity,
        confidence=_confidence_for(category, severity, result),
        false_positive_rate=_UNCALIBRATED_FP_RATE,
        benchmark_version=BENCHMARK_VERSION,
        evidence=_evidence(result),
        explanation=explanation,
        recommendation=recommendation,
    )


def _evidence(result: EncodingMeasurement) -> dict[str, Any]:
    return {
        "image_format": result.image_format,
        "width": result.width,
        "height": result.height,
        "pixel_count": result.pixel_count,
        "file_size_bytes": result.file_size_bytes,
        "bytes_per_pixel": result.bytes_per_pixel,
        "is_jpeg": result.is_jpeg,
        "quantization_table_available": result.quantization_table_available,
        "approximate_jpeg_quality": result.approximate_jpeg_quality,
        "jpeg_quality_estimate_note": result.jpeg_quality_estimate_note,
        "chroma_subsampling": result.chroma_subsampling,
        "block_boundary_score": result.block_boundary_score,
        "block_interior_score": result.block_interior_score,
        "blocking_ratio": result.blocking_ratio,
        "edge_ringing_score": result.edge_ringing_score,
        "mosquito_noise_score": result.mosquito_noise_score,
        "chroma_artifact_score": result.chroma_artifact_score,
        "banding_score": result.banding_score,
        "unique_tone_count": result.unique_tone_count,
        "tonal_range": result.tonal_range,
        "low_resolution_source": result.low_resolution_source,
        "calibrated": False,
        "context_note": (
            "Source encoding evidence may explain texture, halo, crystalline, "
            "or high-frequency findings. Review visually before deciding."
        ),
    }


def _confidence_for(
    category: str,
    severity: Severity,
    result: EncodingMeasurement,
) -> float:
    base = 0.28 if severity is Severity.LOW else 0.36
    if category == "source_encoding.jpeg_blocking":
        base += min(0.08, max(0.0, result.blocking_ratio - _BLOCKING_RATIO_LOW) * 0.04)
    elif category == "source_encoding.jpeg_ringing":
        base += min(0.08, result.edge_ringing_score / 250.0)
    elif category == "source_encoding.banding":
        base += min(0.08, result.banding_score * 0.08)
    elif category == "source_encoding.jpeg_compression" and result.approximate_jpeg_quality is not None:
        base += min(0.08, (_LOW_JPEG_QUALITY_THRESHOLD - result.approximate_jpeg_quality) / 250.0)
    return round(min(_UNCALIBRATED_MAX_CONFIDENCE, base), 4)


def _estimate_jpeg_quality(quantization: dict[int, list[int]]) -> int | None:
    values = [value for table in quantization.values() for value in table if value > 0]
    if not values:
        return None
    mean_q = float(np.mean(values))
    # Advisory approximation only: larger quantization values generally mean
    # stronger compression, but encoders differ.
    quality = 100.0 - (mean_q * 1.6)
    return int(max(1, min(100, round(quality))))


def _chroma_subsampling(opened: Image.Image) -> str:
    layers = getattr(opened, "layer", None)
    if not layers or len(layers) < 3:
        return "not_available"
    try:
        y = layers[0][1:3]
        cb = layers[1][1:3]
        cr = layers[2][1:3]
    except (TypeError, IndexError):
        return "not_available"
    if cb == y and cr == y:
        return "4:4:4"
    if cb == (1, 1) and cr == (1, 1) and y == (2, 2):
        return "4:2:0"
    if cb == (1, 1) and cr == (1, 1) and y == (2, 1):
        return "4:2:2"
    return f"Y{y}_Cb{cb}_Cr{cr}"


def _rgb_to_gray(rgb: np.ndarray) -> np.ndarray:
    return (0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]).astype(np.float32)


def _blocking_metrics(gray: np.ndarray) -> tuple[float, float, float]:
    if min(gray.shape) < 16:
        return 0.0, 0.0, 0.0
    horizontal = np.abs(np.diff(gray, axis=0))
    vertical = np.abs(np.diff(gray, axis=1))
    h_rows = np.arange(horizontal.shape[0])
    v_cols = np.arange(vertical.shape[1])
    h_boundary = (h_rows + 1) % 8 == 0
    v_boundary = (v_cols + 1) % 8 == 0
    boundary_values = np.concatenate([
        horizontal[h_boundary, :].ravel(),
        vertical[:, v_boundary].ravel(),
    ])
    interior_values = np.concatenate([
        horizontal[~h_boundary, :].ravel(),
        vertical[:, ~v_boundary].ravel(),
    ])
    boundary = float(np.mean(boundary_values)) if boundary_values.size else 0.0
    interior = float(np.mean(interior_values)) if interior_values.size else 0.0
    return boundary, interior, boundary / max(interior, 0.25)


def _edge_noise_metrics(gray: np.ndarray) -> tuple[float, float]:
    if min(gray.shape) < 8:
        return 0.0, 0.0
    blur = _box_blur3(gray)
    residual = np.abs(gray - blur)
    gy = np.zeros_like(gray)
    gx = np.zeros_like(gray)
    gy[1:, :] = np.abs(gray[1:, :] - gray[:-1, :])
    gx[:, 1:] = np.abs(gray[:, 1:] - gray[:, :-1])
    edges = (gx + gy) >= 45.0
    edge_zone = _dilate(edges, radius=2)
    near_edge = edge_zone & ~edges
    far_zone = ~_dilate(edges, radius=5)
    if not np.any(near_edge):
        return 0.0, 0.0
    near = residual[near_edge]
    far = residual[far_zone] if np.any(far_zone) else residual
    ringing = float(np.mean(near) - np.mean(far))
    mosquito = float(np.mean(near >= 8.0))
    return max(0.0, ringing), mosquito


def _chroma_artifact_score(rgb: np.ndarray, gray: np.ndarray) -> float:
    if min(gray.shape) < 8:
        return 0.0
    cb = -0.168736 * rgb[:, :, 0] - 0.331264 * rgb[:, :, 1] + 0.5 * rgb[:, :, 2] + 128.0
    cr = 0.5 * rgb[:, :, 0] - 0.418688 * rgb[:, :, 1] - 0.081312 * rgb[:, :, 2] + 128.0
    chroma_residual = np.abs(cb - _box_blur3(cb)) + np.abs(cr - _box_blur3(cr))
    gy = np.zeros_like(gray)
    gx = np.zeros_like(gray)
    gy[1:, :] = np.abs(gray[1:, :] - gray[:-1, :])
    gx[:, 1:] = np.abs(gray[:, 1:] - gray[:, :-1])
    edge_zone = _dilate((gx + gy) >= 45.0, radius=2)
    if not np.any(edge_zone):
        return 0.0
    return float(np.percentile(chroma_residual[edge_zone], 90))


def _banding_metrics(gray: np.ndarray) -> tuple[float, int, float]:
    rounded = np.clip(np.rint(gray), 0, 255).astype(np.uint8)
    unique_tones = int(np.unique(rounded).size)
    tonal_range = float(np.max(gray) - np.min(gray)) if gray.size else 0.0
    if tonal_range <= 0.0:
        return 0.0, unique_tones, tonal_range
    diffs = np.concatenate([
        np.abs(np.diff(gray, axis=0)).ravel(),
        np.abs(np.diff(gray, axis=1)).ravel(),
    ])
    strong_edge_fraction = float(np.mean(diffs >= 20.0)) if diffs.size else 0.0
    if strong_edge_fraction > 0.03:
        return 0.0, unique_tones, tonal_range
    flat_fraction = float(np.mean(diffs <= 0.75)) if diffs.size else 0.0
    unique_pressure = max(0.0, 1.0 - (unique_tones / max(1, min(256, int(tonal_range)))))
    score = flat_fraction * 0.55 + unique_pressure * 0.45
    return score, unique_tones, tonal_range


def _box_blur3(values: np.ndarray) -> np.ndarray:
    padded = np.pad(values, ((1, 1), (1, 1)), mode="edge")
    return (
        padded[:-2, :-2]
        + padded[:-2, 1:-1]
        + padded[:-2, 2:]
        + padded[1:-1, :-2]
        + padded[1:-1, 1:-1]
        + padded[1:-1, 2:]
        + padded[2:, :-2]
        + padded[2:, 1:-1]
        + padded[2:, 2:]
    ) / 9.0


def _dilate(mask: np.ndarray, *, radius: int) -> np.ndarray:
    result = np.zeros_like(mask, dtype=bool)
    padded = np.pad(mask, ((radius, radius), (radius, radius)), mode="constant")
    size = radius * 2 + 1
    for y in range(size):
        for x in range(size):
            result |= padded[y:y + mask.shape[0], x:x + mask.shape[1]]
    return result


__all__ = ["ImageEncodingAnalyzer", "EncodingMeasurement", "measure_image_encoding"]
