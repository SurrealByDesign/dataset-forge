from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from dataset_forge.presets import Preset


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hash_json(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def hash_source_list(paths: Iterable[Path], input_path: Path) -> str:
    relative = [path.relative_to(input_path).as_posix() for path in paths]
    return hash_json(relative)


def hash_source_files(
    paths: Iterable[Path],
    input_path: Path,
) -> tuple[str, dict[str, str]]:
    file_hashes = {
        path.relative_to(input_path).as_posix(): hash_file(path)
        for path in paths
    }
    return hash_json(file_hashes), file_hashes


def hash_preset(preset: Preset | None) -> str:
    if preset is None:
        return hash_json(None)
    return hash_json(
        {
            "name": preset.name,
            "description": preset.description,
            "prompt": preset.prompt,
            "negative_prompt": preset.negative_prompt,
            "transforms": [
                {"name": transform.name, **transform.parameters}
                for transform in preset.transforms
            ],
            "strengths": preset.strengths,
            "notes": preset.notes,
        }
    )

