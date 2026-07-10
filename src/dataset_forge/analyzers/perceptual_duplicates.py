"""Conservative perceptual near-duplicate detection analyzer.

Detects image groups that are extremely likely to be the same training example
after small edits such as mild recompression, tiny resize, small crop, or a
minor color shift. This analyzer is advisory and read-only: it never deletes,
moves, copies, quarantines, excludes, generates, or modifies files.

It intentionally avoids semantic similarity, character recognition, style
matching, face recognition, ML, embeddings, CLIP, or neural networks.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
from PIL import Image, ImageOps

from dataset_forge.analyzers.base import Analyzer
from dataset_forge.context import DatasetContext
from dataset_forge.finding import Finding, Severity

if TYPE_CHECKING:
    from dataset_forge.measurements import ImageMeasurements


BENCHMARK_VERSION = "conservative-perceptual-v1"

_HASH_SIZE = 16
_VERIFY_SIZE = 64
_CROP_BORDER_RATIO = 0.08
_AHASH_MAX_DISTANCE = 12
_DHASH_MAX_DISTANCE = 18
_VERIFY_MIN_CORRELATION = 0.965
_VERIFY_MAX_MEAN_ABS_DIFF = 0.050
_VERIFY_MAX_RMS_DIFF = 0.075
_VERIFY_MIN_CROP_CORRELATION = 0.975
_VERIFY_MAX_CROP_MEAN_ABS_DIFF = 0.040
_VERIFY_MIN_LUMINANCE_STD = 0.025
_UNCALIBRATED_FP_RATE = 0.08


@dataclass(frozen=True)
class _PerceptualRecord:
    path: Path
    file_sha256: str
    pixel_sha256: str
    width: int
    height: int
    mode: str
    image_format: str
    file_size: int
    ahash: tuple[int, ...]
    dhash: tuple[int, ...]
    gray64: tuple[float, ...]
    crop64: tuple[float, ...]
    luminance_std: float
    crop_luminance_std: float

    @property
    def pixel_count(self) -> int:
        return self.width * self.height

    @property
    def bytes_per_pixel(self) -> float:
        return round(self.file_size / max(1, self.pixel_count), 6)

    @property
    def is_jpeg(self) -> bool:
        return self.image_format.upper() in {"JPEG", "JPG"} or self.path.suffix.casefold() in {
            ".jpg",
            ".jpeg",
        }

    @property
    def is_lossless_preferred(self) -> bool:
        return self.image_format.upper() in {"PNG", "BMP", "TIFF"} or self.path.suffix.casefold() in {
            ".png",
            ".bmp",
            ".tif",
            ".tiff",
        }


@dataclass(frozen=True)
class _PairVerification:
    first: _PerceptualRecord
    second: _PerceptualRecord
    ahash_distance: int
    dhash_distance: int
    luminance_correlation: float
    mean_abs_diff: float
    rms_diff: float
    crop_luminance_correlation: float
    crop_mean_abs_diff: float

    @property
    def passes(self) -> bool:
        if self.first.pixel_sha256 == self.second.pixel_sha256:
            return False
        if (
            max(self.first.luminance_std, self.second.luminance_std)
            < _VERIFY_MIN_LUMINANCE_STD
        ):
            return False
        if self.ahash_distance > _AHASH_MAX_DISTANCE:
            return False
        if self.dhash_distance > _DHASH_MAX_DISTANCE:
            return False
        if self.luminance_correlation < _VERIFY_MIN_CORRELATION:
            return False
        if self.mean_abs_diff > _VERIFY_MAX_MEAN_ABS_DIFF:
            return False
        if self.rms_diff > _VERIFY_MAX_RMS_DIFF:
            return False
        return (
            self.crop_luminance_correlation >= _VERIFY_MIN_CROP_CORRELATION
            and self.crop_mean_abs_diff <= _VERIFY_MAX_CROP_MEAN_ABS_DIFF
        )


@dataclass(frozen=True)
class _PerceptualGroup:
    group_id: str
    members: tuple[_PerceptualRecord, ...]
    suggested_representative: _PerceptualRecord
    pair_evidence: tuple[_PairVerification, ...]


class PerceptualDuplicateAnalyzer(Analyzer):
    """Detect conservative perceptual near-duplicate groups."""

    @property
    def name(self) -> str:
        return "perceptual_duplicate_analyzer"

    @property
    def version(self) -> str:
        return "v1"

    @property
    def supported_categories(self) -> tuple[str, ...]:
        return ("duplicate.perceptual",)

    @property
    def benchmark_version(self) -> str | None:
        return BENCHMARK_VERSION

    def analyze(
        self,
        image_path: Path,
        context: DatasetContext,
        measurements: ImageMeasurements | None = None,
    ) -> list[Finding]:
        del measurements
        groups = _perceptual_groups(_context_key(context.image_paths))
        group = next(
            (
                candidate
                for candidate in groups
                if any(record.path.resolve() == image_path.resolve() for record in candidate.members)
            ),
            None,
        )
        if group is None:
            return []

        # One finding per group, attached to the deterministic representative.
        if image_path.resolve() != group.suggested_representative.path.resolve():
            return []

        representative = _normalized_path(group.suggested_representative.path)
        duplicate_paths = [
            _normalized_path(record.path)
            for record in group.members
            if record.path.resolve() != group.suggested_representative.path.resolve()
        ]
        explanation = (
            f"{group.group_id} contains {len(group.members)} images that passed "
            "conservative perceptual near-duplicate verification. This means "
            "multiple classical image signals agree that the files are likely "
            "the same training example after small edits. It is not semantic, "
            "style, subject, pose, prompt, or composition matching."
        )
        recommendation = (
            "Review this near-duplicate group manually before deciding which "
            "image or images belong in your dataset. Dataset Forge does not "
            "delete, move, copy, quarantine, exclude, generate, or modify files."
        )

        return [
            Finding(
                image_path=image_path,
                analyzer=self.analyzer_id,
                category="duplicate.perceptual",
                severity=Severity.LOW,
                confidence=_group_confidence(group),
                false_positive_rate=_UNCALIBRATED_FP_RATE,
                benchmark_version=BENCHMARK_VERSION,
                evidence={
                    "group_id": group.group_id,
                    "group_size": len(group.members),
                    "representative_image": representative,
                    "duplicate_images": duplicate_paths,
                    "member_paths": [_normalized_path(record.path) for record in group.members],
                    "matching_algorithms": [
                        "average_hash_16x16",
                        "difference_hash_16x16",
                        "low_resolution_luminance_correlation",
                        "center_crop_luminance_verification",
                    ],
                    "verification_thresholds": {
                        "ahash_max_distance": _AHASH_MAX_DISTANCE,
                        "dhash_max_distance": _DHASH_MAX_DISTANCE,
                        "luminance_correlation_minimum": _VERIFY_MIN_CORRELATION,
                        "mean_abs_diff_maximum": _VERIFY_MAX_MEAN_ABS_DIFF,
                        "rms_diff_maximum": _VERIFY_MAX_RMS_DIFF,
                        "crop_luminance_correlation_minimum": _VERIFY_MIN_CROP_CORRELATION,
                        "crop_mean_abs_diff_maximum": _VERIFY_MAX_CROP_MEAN_ABS_DIFF,
                        "minimum_luminance_std": _VERIFY_MIN_LUMINANCE_STD,
                    },
                    "pair_verification": [
                        _pair_evidence(pair)
                        for pair in group.pair_evidence
                    ],
                    "ranking_evidence": {
                        "suggested_representative": _ranking_evidence(
                            group.suggested_representative
                        ),
                        "ranking_rules": [
                            "highest_pixel_count",
                            "largest_width_height",
                            "prefer_lossless_format",
                            "prefer_non_jpeg",
                            "higher_bytes_per_pixel",
                            "normalized_path",
                        ],
                    },
                },
                explanation=explanation,
                recommendation=recommendation,
            )
        ]


def _context_key(image_paths: tuple[Path, ...]) -> tuple[tuple[str, int, int], ...]:
    return tuple(
        sorted(
            (
                str(path.resolve()),
                path.stat().st_mtime_ns,
                path.stat().st_size,
            )
            for path in image_paths
        )
    )


@lru_cache(maxsize=8)
def _perceptual_groups(
    context_key: tuple[tuple[str, int, int], ...],
) -> tuple[_PerceptualGroup, ...]:
    records: list[_PerceptualRecord] = []
    for path_text, _mtime, _size in context_key:
        try:
            records.append(_record_for_path(Path(path_text)))
        except Exception:
            continue

    pairs: list[_PairVerification] = []
    for left_index, first in enumerate(records):
        for second in records[left_index + 1:]:
            pair = _verify_pair(first, second)
            if pair.passes:
                pairs.append(pair)

    groups = _groups_from_pairs(pairs)
    groups.sort(key=lambda group: [_normalized_path(record.path) for record in group])
    return tuple(
        _PerceptualGroup(
            group_id=f"perceptual-duplicate-group-{index:04d}",
            members=group,
            suggested_representative=_suggested_representative(group),
            pair_evidence=tuple(
                pair for pair in pairs
                if pair.first in group and pair.second in group
            ),
        )
        for index, group in enumerate(groups, start=1)
    )


def _record_for_path(path: Path) -> _PerceptualRecord:
    file_size = path.stat().st_size
    file_hash = _file_sha256(path)
    with Image.open(path) as source:
        image_format = str(source.format or path.suffix.lstrip(".") or "unknown")
        image = ImageOps.exif_transpose(source)
        converted = image.convert("RGB")
        width, height = converted.size
        pixel_hash = _pixel_sha256(converted, "RGB", width, height)
        gray_hash = converted.convert("L")
        ahash = _average_hash(gray_hash)
        dhash = _difference_hash(gray_hash)
        gray64 = _luminance_fingerprint(gray_hash)
        crop64 = _luminance_fingerprint(_center_crop(gray_hash))

    return _PerceptualRecord(
        path=path,
        file_sha256=file_hash,
        pixel_sha256=pixel_hash,
        width=width,
        height=height,
        mode="RGB",
        image_format=image_format.upper(),
        file_size=file_size,
        ahash=ahash,
        dhash=dhash,
        gray64=gray64,
        crop64=crop64,
        luminance_std=round(float(np.std(gray64)), 6),
        crop_luminance_std=round(float(np.std(crop64)), 6),
    )


def _verify_pair(
    first: _PerceptualRecord,
    second: _PerceptualRecord,
) -> _PairVerification:
    gray_first = np.asarray(first.gray64, dtype=np.float32)
    gray_second = np.asarray(second.gray64, dtype=np.float32)
    crop_first = np.asarray(first.crop64, dtype=np.float32)
    crop_second = np.asarray(second.crop64, dtype=np.float32)
    diff = np.abs(gray_first - gray_second)
    crop_diff = np.abs(crop_first - crop_second)
    return _PairVerification(
        first=first,
        second=second,
        ahash_distance=_hamming_distance(first.ahash, second.ahash),
        dhash_distance=_hamming_distance(first.dhash, second.dhash),
        luminance_correlation=_correlation(gray_first, gray_second),
        mean_abs_diff=float(np.mean(diff)),
        rms_diff=float(np.sqrt(np.mean((gray_first - gray_second) ** 2))),
        crop_luminance_correlation=_correlation(crop_first, crop_second),
        crop_mean_abs_diff=float(np.mean(crop_diff)),
    )


def _groups_from_pairs(
    pairs: list[_PairVerification],
) -> list[tuple[_PerceptualRecord, ...]]:
    parent: dict[_PerceptualRecord, _PerceptualRecord] = {}

    def find(record: _PerceptualRecord) -> _PerceptualRecord:
        parent.setdefault(record, record)
        while parent[record] != record:
            parent[record] = parent[parent[record]]
            record = parent[record]
        return record

    def union(first: _PerceptualRecord, second: _PerceptualRecord) -> None:
        first_root = find(first)
        second_root = find(second)
        if first_root == second_root:
            return
        if _normalized_path(first_root.path) <= _normalized_path(second_root.path):
            parent[second_root] = first_root
        else:
            parent[first_root] = second_root

    for pair in pairs:
        union(pair.first, pair.second)

    grouped: dict[_PerceptualRecord, list[_PerceptualRecord]] = {}
    for pair in pairs:
        grouped.setdefault(find(pair.first), []).append(pair.first)
        grouped.setdefault(find(pair.second), []).append(pair.second)

    result: list[tuple[_PerceptualRecord, ...]] = []
    for members in grouped.values():
        unique = tuple(
            sorted(
                set(members),
                key=lambda record: _normalized_path(record.path),
            )
        )
        if len(unique) >= 2:
            result.append(unique)
    return result


def _average_hash(image: Image.Image) -> tuple[int, ...]:
    resized = image.resize((_HASH_SIZE, _HASH_SIZE), Image.Resampling.BICUBIC)
    values = np.asarray(resized, dtype=np.float32)
    mean = float(np.mean(values))
    return tuple(int(value >= mean) for value in values.ravel())


def _difference_hash(image: Image.Image) -> tuple[int, ...]:
    resized = image.resize((_HASH_SIZE + 1, _HASH_SIZE), Image.Resampling.BICUBIC)
    values = np.asarray(resized, dtype=np.float32)
    diff = values[:, 1:] > values[:, :-1]
    return tuple(int(value) for value in diff.ravel())


def _luminance_fingerprint(image: Image.Image) -> tuple[float, ...]:
    resized = image.resize((_VERIFY_SIZE, _VERIFY_SIZE), Image.Resampling.BICUBIC)
    values = np.asarray(resized, dtype=np.float32) / 255.0
    return tuple(float(value) for value in values.ravel())


def _center_crop(image: Image.Image) -> Image.Image:
    width, height = image.size
    dx = int(width * _CROP_BORDER_RATIO)
    dy = int(height * _CROP_BORDER_RATIO)
    if width - 2 * dx < 8 or height - 2 * dy < 8:
        return image
    return image.crop((dx, dy, width - dx, height - dy))


def _hamming_distance(first: tuple[int, ...], second: tuple[int, ...]) -> int:
    return sum(1 for left, right in zip(first, second) if left != right)


def _correlation(first: np.ndarray, second: np.ndarray) -> float:
    first_centered = first - float(np.mean(first))
    second_centered = second - float(np.mean(second))
    denominator = float(np.linalg.norm(first_centered) * np.linalg.norm(second_centered))
    if denominator <= 1e-12:
        return 1.0 if float(np.mean(np.abs(first - second))) <= 0.01 else 0.0
    return float(np.dot(first_centered, second_centered) / denominator)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _pixel_sha256(image: Image.Image, mode: str, width: int, height: int) -> str:
    digest = hashlib.sha256()
    digest.update(mode.encode("utf-8"))
    digest.update(str(width).encode("ascii"))
    digest.update(b"x")
    digest.update(str(height).encode("ascii"))
    digest.update(b"\0")
    digest.update(image.tobytes())
    return digest.hexdigest()


def _suggested_representative(
    members: tuple[_PerceptualRecord, ...],
) -> _PerceptualRecord:
    return sorted(members, key=_representative_sort_key)[0]


def _representative_sort_key(record: _PerceptualRecord) -> tuple[Any, ...]:
    return (
        -record.pixel_count,
        -max(record.width, record.height),
        -min(record.width, record.height),
        -int(record.is_lossless_preferred),
        int(record.is_jpeg),
        -record.bytes_per_pixel,
        _normalized_path(record.path),
    )


def _ranking_evidence(record: _PerceptualRecord) -> dict[str, Any]:
    return {
        "path": _normalized_path(record.path),
        "width": record.width,
        "height": record.height,
        "pixel_count": record.pixel_count,
        "format": record.image_format,
        "file_size_bytes": record.file_size,
        "bytes_per_pixel": record.bytes_per_pixel,
        "is_lossless_preferred": record.is_lossless_preferred,
        "is_jpeg": record.is_jpeg,
    }


def _pair_evidence(pair: _PairVerification) -> dict[str, Any]:
    return {
        "first_image": _normalized_path(pair.first.path),
        "second_image": _normalized_path(pair.second.path),
        "ahash_distance": pair.ahash_distance,
        "dhash_distance": pair.dhash_distance,
        "luminance_correlation": round(pair.luminance_correlation, 6),
        "mean_abs_diff": round(pair.mean_abs_diff, 6),
        "rms_diff": round(pair.rms_diff, 6),
        "crop_luminance_correlation": round(pair.crop_luminance_correlation, 6),
        "crop_mean_abs_diff": round(pair.crop_mean_abs_diff, 6),
        "first_luminance_std": pair.first.luminance_std,
        "second_luminance_std": pair.second.luminance_std,
        "interpretation": (
            "All listed metrics must pass conservative thresholds before "
            "Dataset Forge emits a perceptual near-duplicate finding."
        ),
    }


def _group_confidence(group: _PerceptualGroup) -> float:
    if not group.pair_evidence:
        return 0.0
    weakest = min(
        pair.luminance_correlation + pair.crop_luminance_correlation
        for pair in group.pair_evidence
    ) / 2.0
    return round(min(0.82, max(0.60, weakest - 0.18)), 4)


def _normalized_path(path: Path) -> str:
    return path.resolve().as_posix()


__all__ = [
    "PerceptualDuplicateAnalyzer",
]
