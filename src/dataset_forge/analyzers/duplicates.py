"""Exact duplicate detection analyzer.

Detects byte-identical files and decoded pixel-identical images. This analyzer
is advisory and read-only: it never deletes, moves, copies, quarantines,
excludes, or modifies files.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PIL import Image, ImageOps

from dataset_forge.analyzers.base import Analyzer
from dataset_forge.context import DatasetContext
from dataset_forge.finding import Finding, Severity

if TYPE_CHECKING:
    from dataset_forge.measurements import ImageMeasurements


BENCHMARK_VERSION = "deterministic-exact-v1"


@dataclass(frozen=True)
class _DuplicateRecord:
    path: Path
    file_sha256: str
    pixel_sha256: str
    width: int
    height: int
    mode: str
    image_format: str
    file_size: int

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
class _DuplicateGroup:
    group_id: str
    duplicate_kind: str
    members: tuple[_DuplicateRecord, ...]
    suggested_representative: _DuplicateRecord


class DuplicateDetectionAnalyzer(Analyzer):
    """Detect byte-identical and decoded pixel-identical duplicate images."""

    @property
    def name(self) -> str:
        return "duplicate_detection_analyzer"

    @property
    def version(self) -> str:
        return "v1"

    @property
    def supported_categories(self) -> tuple[str, ...]:
        return ("dataset.duplicate.exact",)

    @property
    def benchmark_version(self) -> str | None:
        return BENCHMARK_VERSION

    def analyze(
        self,
        image_path: Path,
        context: DatasetContext,
        measurements: ImageMeasurements | None = None,
    ) -> list[Finding]:
        groups = _duplicate_groups(_context_key(context.image_paths))
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

        current = next(
            record for record in group.members
            if record.path.resolve() == image_path.resolve()
        )
        role = (
            "suggested_representative"
            if current.path == group.suggested_representative.path
            else "duplicate_candidate"
        )
        member_paths = tuple(_normalized_path(record.path) for record in group.members)
        representative = _normalized_path(group.suggested_representative.path)

        explanation = (
            f"This image belongs to {group.group_id}, an exact duplicate group "
            f"with {len(group.members)} images detected by {group.duplicate_kind}. "
            f"Suggested representative: {representative}. Suggested "
            f"representative is advisory. Dataset Forge does not delete, move, "
            f"or exclude files."
        )
        recommendation = (
            "Review this duplicate group before deciding which image or images "
            "belong in your training dataset. No files were moved, deleted, "
            "copied, quarantined, excluded, or modified."
        )

        return [
            Finding(
                image_path=image_path,
                analyzer=self.analyzer_id,
                category="dataset.duplicate.exact",
                severity=Severity.LOW,
                confidence=1.0,
                false_positive_rate=0.0,
                benchmark_version=BENCHMARK_VERSION,
                evidence={
                    "group_id": group.group_id,
                    "group_size": len(group.members),
                    "duplicate_kind": group.duplicate_kind,
                    "duplicate_member_paths": list(member_paths),
                    "suggested_representative_path": representative,
                    "current_image_role": role,
                    "ranking_evidence": {
                        "current_image": _ranking_evidence(current),
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
def _duplicate_groups(
    context_key: tuple[tuple[str, int, int], ...],
) -> tuple[_DuplicateGroup, ...]:
    records: list[_DuplicateRecord] = []
    for path_text, _mtime, _size in context_key:
        try:
            records.append(_record_for_path(Path(path_text)))
        except Exception:
            continue

    by_pixel_hash: dict[str, list[_DuplicateRecord]] = {}
    for record in records:
        by_pixel_hash.setdefault(record.pixel_sha256, []).append(record)

    groups: list[tuple[str, tuple[_DuplicateRecord, ...]]] = []
    for pixel_records in by_pixel_hash.values():
        if len(pixel_records) < 2:
            continue
        members = tuple(sorted(pixel_records, key=lambda item: _normalized_path(item.path)))
        duplicate_kind = (
            "file_sha256"
            if len({record.file_sha256 for record in members}) == 1
            else "pixel_sha256"
        )
        groups.append((duplicate_kind, members))

    groups.sort(
        key=lambda item: (
            0 if item[0] == "file_sha256" else 1,
            [_normalized_path(record.path) for record in item[1]],
        )
    )

    return tuple(
        _DuplicateGroup(
            group_id=f"duplicate-group-{index:04d}",
            duplicate_kind=duplicate_kind,
            members=members,
            suggested_representative=_suggested_representative(members),
        )
        for index, (duplicate_kind, members) in enumerate(groups, start=1)
    )


def _record_for_path(path: Path) -> _DuplicateRecord:
    file_size = path.stat().st_size
    file_hash = _file_sha256(path)

    with Image.open(path) as source:
        image_format = str(source.format or path.suffix.lstrip(".") or "unknown")
        image = ImageOps.exif_transpose(source)
        target_mode = "RGBA" if "A" in image.getbands() else "RGB"
        converted = image.convert(target_mode)
        width, height = converted.size
        pixel_hash = _pixel_sha256(converted, target_mode, width, height)

    return _DuplicateRecord(
        path=path,
        file_sha256=file_hash,
        pixel_sha256=pixel_hash,
        width=width,
        height=height,
        mode=target_mode,
        image_format=image_format.upper(),
        file_size=file_size,
    )


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
    members: tuple[_DuplicateRecord, ...],
) -> _DuplicateRecord:
    return sorted(members, key=_representative_sort_key)[0]


def _representative_sort_key(record: _DuplicateRecord) -> tuple[Any, ...]:
    return (
        -record.pixel_count,
        -max(record.width, record.height),
        -min(record.width, record.height),
        -int(record.is_lossless_preferred),
        int(record.is_jpeg),
        -record.bytes_per_pixel,
        _normalized_path(record.path),
    )


def _ranking_evidence(record: _DuplicateRecord) -> dict[str, Any]:
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


def _normalized_path(path: Path) -> str:
    return path.resolve().as_posix()


__all__ = ["DuplicateDetectionAnalyzer"]
