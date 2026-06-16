from __future__ import annotations

import json
from pathlib import Path

from dataset_forge.presets.schema import Preset, PresetError, validate_preset


def default_preset_directory() -> Path:
    return Path(__file__).resolve().parents[3] / "presets"


def load_preset(value: str | Path, preset_directory: Path | None = None) -> Preset:
    source = _resolve_preset_path(value, preset_directory)
    try:
        with source.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except json.JSONDecodeError as exc:
        raise PresetError(
            f"Invalid JSON in preset {source}: line {exc.lineno}, column {exc.colno}."
        ) from exc
    except OSError as exc:
        raise PresetError(f"Could not read preset {source}: {exc}") from exc

    return validate_preset(data, source)


def list_presets(preset_directory: Path | None = None) -> list[Preset]:
    directory = (preset_directory or default_preset_directory()).resolve()
    if not directory.is_dir():
        raise PresetError(f"Preset folder does not exist: {directory}")
    return [load_preset(path, directory) for path in sorted(directory.glob("*.json"))]


def _resolve_preset_path(value: str | Path, preset_directory: Path | None) -> Path:
    requested = Path(value).expanduser()
    if requested.is_file():
        return requested.resolve()

    directory = (preset_directory or default_preset_directory()).resolve()
    filename = requested.name
    if not filename.lower().endswith(".json"):
        filename += ".json"
    candidate = directory / filename
    if candidate.is_file():
        return candidate.resolve()
    raise PresetError(
        f"Preset not found: {value}. Use a JSON file path or a name from --list-presets."
    )
