from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence


class PluginMetadataError(ValueError):
    """Raised when a plugin does not satisfy the SDK metadata contract."""


@dataclass
class PluginContext:
    input_path: Path
    output_path: Path
    source_files: tuple[Path, ...] = ()
    artifacts: dict[str, Path] = field(default_factory=dict)
    config: dict[str, Any] = field(default_factory=dict)
    resource_manager: Any | None = None
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PluginExecutionResult:
    plugin_id: str
    status: str
    artifacts: Mapping[str, Path] = field(default_factory=dict)
    details: Mapping[str, Any] = field(default_factory=dict)
    error: str | None = None


class Plugin(ABC):
    category = "plugin"
    id: str
    name: str
    version: str
    author: str
    description: str
    tags: Sequence[str] = ()
    capabilities: Sequence[str] = ()
    compatible_presets: Sequence[str] = ()
    input_types: Sequence[str] = ()
    output_types: Sequence[str] = ()
    configurable_parameters: Mapping[str, Any] = {}
    requires: Sequence[str] = ()
    produces: Sequence[str] = ()
    estimated_runtime: str = "unknown"
    estimated_memory: int = 0
    estimated_gpu: int = 0
    estimated_quality_gain: float = 0.0

    def __init__(self, config: Mapping[str, Any] | None = None) -> None:
        self.validate_metadata()
        self.config = _configuration_defaults(self.configurable_parameters)
        self.config.update(dict(config or {}))

    @classmethod
    def metadata(cls) -> dict[str, Any]:
        cls.validate_metadata()
        return {
            "id": cls.id,
            "category": cls.category,
            "name": cls.name,
            "version": cls.version,
            "author": cls.author,
            "description": cls.description,
            "tags": list(cls.tags),
            "capabilities": list(cls.capabilities),
            "compatible_presets": list(cls.compatible_presets),
            "input_types": list(cls.input_types),
            "output_types": list(cls.output_types),
            "configurable_parameters": dict(cls.configurable_parameters),
            "requires": list(cls.requires),
            "produces": list(cls.produces),
            "estimated_runtime": cls.estimated_runtime,
            "estimated_memory": cls.estimated_memory,
            "estimated_gpu": cls.estimated_gpu,
            "estimated_quality_gain": cls.estimated_quality_gain,
        }

    @classmethod
    def validate_metadata(cls) -> None:
        string_fields = ("id", "name", "version", "author", "description")
        for field_name in string_fields:
            value = getattr(cls, field_name, None)
            if not isinstance(value, str) or not value.strip():
                raise PluginMetadataError(
                    f"Plugin {cls.__name__} must define non-empty '{field_name}'."
                )
        for field_name in (
            "tags",
            "capabilities",
            "compatible_presets",
            "input_types",
            "output_types",
            "requires",
            "produces",
        ):
            value = getattr(cls, field_name, None)
            if not isinstance(value, (tuple, list)) or not all(
                isinstance(item, str) and item.strip() for item in value
            ):
                raise PluginMetadataError(
                    f"Plugin '{cls.id}' field '{field_name}' must be a string sequence."
                )
        if not isinstance(cls.configurable_parameters, Mapping):
            raise PluginMetadataError(
                f"Plugin '{cls.id}' configurable_parameters must be a mapping."
            )
        for field_name in ("estimated_memory", "estimated_gpu"):
            value = getattr(cls, field_name, None)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise PluginMetadataError(
                    f"Plugin '{cls.id}' field '{field_name}' must be non-negative."
                )
        if (
            isinstance(cls.estimated_quality_gain, bool)
            or not isinstance(cls.estimated_quality_gain, (int, float))
            or cls.estimated_quality_gain < 0
        ):
            raise PluginMetadataError(
                f"Plugin '{cls.id}' estimated_quality_gain must be non-negative."
            )

    @abstractmethod
    def run(self, context: PluginContext) -> PluginExecutionResult:
        """Execute specialized plugin behavior."""


class Analyzer(Plugin):
    category = "analyzer"


class Transform(Plugin):
    category = "transform"


class Validator(Plugin):
    category = "validator"


class Captioner(Plugin):
    category = "captioner"


class Exporter(Plugin):
    category = "exporter"


class Importer(Plugin):
    category = "importer"


class ReviewProvider(Plugin):
    category = "review_provider"


def _configuration_defaults(schema: Mapping[str, Any]) -> dict[str, Any]:
    defaults: dict[str, Any] = {}
    for name, definition in schema.items():
        if isinstance(definition, Mapping) and "default" in definition:
            defaults[name] = definition["default"]
    return defaults
