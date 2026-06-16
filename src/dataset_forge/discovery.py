from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

SUPPORTED_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp"})


@dataclass(frozen=True)
class DiscoveryResult:
    images: list[Path]
    skipped_files: int


def discover_images(
    input_path: Path,
    *,
    recursive: bool,
    limit: int | None = None,
    excluded_root: Path | None = None,
) -> DiscoveryResult:
    """Return supported images in deterministic order without modifying them."""
    input_path = input_path.resolve()
    excluded_root = excluded_root.resolve() if excluded_root else None
    iterator = input_path.rglob("*") if recursive else input_path.glob("*")

    images: list[Path] = []
    skipped = 0
    for path in sorted(iterator, key=lambda item: str(item).casefold()):
        if not path.is_file():
            continue
        resolved = path.resolve()
        if excluded_root and _is_relative_to(resolved, excluded_root):
            continue
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            skipped += 1
            continue
        if limit is None or len(images) < limit:
            images.append(resolved)

    return DiscoveryResult(images=images, skipped_files=skipped)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False
