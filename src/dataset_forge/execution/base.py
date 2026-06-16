from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from dataset_forge.presets import Preset


@dataclass(frozen=True)
class StageResult:
    artifacts: Mapping[str, Path]
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class PipelineContext:
    input_path: Path
    output_path: Path
    pipeline_name: str
    pipeline_config: dict[str, Any]
    preset: Preset | None
    source_files: tuple[Path, ...]
    source_file_hashes: dict[str, str]
    resource_manager: Any | None = None
    artifacts: dict[str, Path] = field(default_factory=dict)
    data: dict[str, Any] = field(default_factory=dict)


class PipelineStage(ABC):
    id: str
    name: str
    description: str
    requires: Sequence[str] = ()
    produces: Sequence[str] = ()
    estimated_runtime: str = "unknown"
    estimated_ram: int = 0
    estimated_vram: int = 0
    estimated_disk_write: int = 0
    estimated_temp_storage: int = 0

    def __init__(self, config: Mapping[str, Any] | None = None) -> None:
        self.config = dict(config or {})

    @abstractmethod
    def expected_outputs(self, context: PipelineContext) -> Mapping[str, Path]:
        """Return the output paths this stage owns."""

    @abstractmethod
    def run(self, context: PipelineContext) -> StageResult:
        """Execute the stage without mutating source images."""
