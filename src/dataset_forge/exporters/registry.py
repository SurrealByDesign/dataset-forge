from __future__ import annotations

from dataset_forge.exporters.base import Exporter


class ExporterRegistry:
    def __init__(self) -> None:
        self._exporters: dict[str, type[Exporter]] = {}

    def register(self, exporter: type[Exporter]) -> type[Exporter]:
        name = getattr(exporter, "name", "")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Exporter classes must define a non-empty name.")
        if name in self._exporters:
            raise ValueError(f"Exporter already registered: {name}")
        self._exporters[name] = exporter
        return exporter

    def get(self, name: str) -> type[Exporter]:
        try:
            return self._exporters[name]
        except KeyError as exc:
            raise KeyError(f"Unknown exporter: {name}") from exc

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._exporters))

    def clear(self) -> None:
        self._exporters.clear()


exporter_registry = ExporterRegistry()

