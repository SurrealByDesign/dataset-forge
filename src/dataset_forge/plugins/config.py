from __future__ import annotations

from pathlib import Path
from typing import Any

from dataset_forge.core.structured import load_structured_file


def load_plugin_configuration(path: Path) -> dict[str, dict[str, Any]]:
    data = load_structured_file(path)
    values = data.get("plugins", data)
    if not isinstance(values, dict):
        raise ValueError("Plugin configuration must contain an object.")
    configurations: dict[str, dict[str, Any]] = {}
    for plugin_id, config in values.items():
        if not isinstance(plugin_id, str) or not isinstance(config, dict):
            raise ValueError("Each plugin configuration must be an object.")
        configurations[plugin_id] = dict(config)
    return configurations

