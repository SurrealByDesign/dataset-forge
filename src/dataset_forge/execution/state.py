from __future__ import annotations

import json
from pathlib import Path
from typing import Any

STATE_FILENAME = "pipeline_state.json"
REPORT_FILENAME = "pipeline_report.json"


def load_state(output_path: Path) -> dict[str, Any]:
    path = output_path / STATE_FILENAME
    try:
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except OSError as exc:
        raise ValueError(f"Could not read pipeline state {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid pipeline state {path}: line {exc.lineno}, column {exc.colno}."
        ) from exc
    if not isinstance(data, dict):
        raise ValueError(f"Pipeline state must contain a JSON object: {path}")
    return data


def write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
        handle.write("\n")
    temporary.replace(path)

