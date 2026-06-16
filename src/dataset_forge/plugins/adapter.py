from __future__ import annotations

from pathlib import Path
import json
from typing import Any, Mapping

from dataset_forge.execution.base import PipelineContext, PipelineStage, StageResult
from dataset_forge.plugins.registry import PluginRegistry
from dataset_forge.plugins.sdk import PluginContext


class PluginStageAdapter(PipelineStage):
    def __init__(
        self,
        registry: PluginRegistry,
        plugin_id: str,
        config: Mapping[str, Any] | None = None,
        *,
        fail_fast: bool = False,
    ) -> None:
        self.registry = registry
        self.plugin_id = plugin_id
        self.plugin_class = registry.get(plugin_id)
        self.id = self.plugin_class.id
        self.name = self.plugin_class.name
        self.description = self.plugin_class.description
        self.requires = tuple(self.plugin_class.requires)
        self.produces = tuple(self.plugin_class.produces)
        self.estimated_runtime = self.plugin_class.estimated_runtime
        self.estimated_ram = self.plugin_class.estimated_memory
        self.estimated_vram = self.plugin_class.estimated_gpu
        self.fail_fast = fail_fast
        super().__init__(config)

    def expected_outputs(self, context: PipelineContext) -> Mapping[str, Path]:
        return {
            name: context.output_path / "plugins" / self.plugin_id / f"{name}.json"
            for name in self.produces
        }

    def run(self, context: PipelineContext) -> StageResult:
        plugin_context = PluginContext(
            input_path=context.input_path,
            output_path=context.output_path,
            source_files=context.source_files,
            artifacts=context.artifacts,
            config=dict(self.config),
            resource_manager=context.resource_manager,
            data=context.data,
        )
        result = self.registry.execute(
            self.plugin_id,
            plugin_context,
            config=dict(self.config),
            fail_fast=self.fail_fast,
        )
        if result.status == "failed":
            artifacts = {}
            for name, path in self.expected_outputs(context).items():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    json.dumps(
                        {
                            "plugin_id": self.plugin_id,
                            "status": "failed",
                            "error": result.error,
                        },
                        indent=2,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                artifacts[name] = path
            return StageResult(
                artifacts,
                {"status": "failed", "error": result.error},
            )
        return StageResult(
            artifacts=result.artifacts,
            details={"status": result.status, **dict(result.details)},
        )
