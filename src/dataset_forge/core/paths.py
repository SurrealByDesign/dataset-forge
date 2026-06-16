from __future__ import annotations

from pathlib import Path

from dataset_forge.discovery import DiscoveryResult, discover_images


def resolve_directory(path: Path) -> Path:
    return path.expanduser().resolve()


__all__ = ["DiscoveryResult", "discover_images", "resolve_directory"]

