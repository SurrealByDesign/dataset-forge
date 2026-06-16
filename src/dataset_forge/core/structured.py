from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_structured_file(path: Path) -> dict[str, Any]:
    source = path.expanduser().resolve()
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Could not read configuration {source}: {exc}") from exc
    try:
        if source.suffix.lower() == ".json":
            data = json.loads(text)
        elif source.suffix.lower() in {".yaml", ".yml"}:
            data = parse_simple_yaml(text)
        else:
            raise ValueError("Configuration must be JSON or YAML.")
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid JSON in configuration {source}: "
            f"line {exc.lineno}, column {exc.colno}."
        ) from exc
    if not isinstance(data, dict):
        raise ValueError(f"Configuration must contain an object: {source}")
    return data


def parse_simple_yaml(text: str) -> dict[str, Any]:
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]
    for line_number, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.split("#", 1)[0].rstrip()
        if not stripped.strip():
            continue
        indent = len(stripped) - len(stripped.lstrip(" "))
        content = stripped.strip()
        if ":" not in content:
            raise ValueError(f"Invalid YAML at line {line_number}.")
        key, raw_value = content.split(":", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"Invalid YAML key at line {line_number}.")
        while stack[-1][0] >= indent:
            stack.pop()
        parent = stack[-1][1]
        value = raw_value.strip()
        if not value:
            child: dict[str, Any] = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = _yaml_scalar(value)
    return root


def _yaml_scalar(value: str) -> Any:
    lowered = value.lower()
    if lowered in {"true", "yes"}:
        return True
    if lowered in {"false", "no"}:
        return False
    if lowered in {"null", "none", "~"}:
        return None
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    try:
        return float(value) if "." in value else int(value)
    except ValueError:
        return value

