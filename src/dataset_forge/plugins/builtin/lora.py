from __future__ import annotations

import json

from dataset_forge.plugins.sdk import (
    Analyzer,
    Captioner,
    Exporter,
    PluginContext,
    PluginExecutionResult,
    Transform,
)

AUTHOR = "Dataset Forge"
VERSION = "0.1.0"


class _PlaceholderSupport:
    def _write_placeholder(
        self,
        context: PluginContext,
        artifact_name: str,
        message: str,
    ) -> PluginExecutionResult:
        destination = (
            context.output_path
            / "plugins"
            / self.id
            / f"{artifact_name}.json"
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(
                {
                    "plugin_id": self.id,
                    "status": "placeholder",
                    "message": message,
                    "source_image_count": len(context.source_files),
                    "configuration": self.config,
                    "source_images_modified": False,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return PluginExecutionResult(
            plugin_id=self.id,
            status="success",
            artifacts={artifact_name: destination},
            details={"placeholder": True, "source_images_modified": False},
        )


class LoraDatasetAnalyzer(_PlaceholderSupport, Analyzer):
    id = "lora.dataset_analyzer"
    name = "LoRA Dataset Analyzer"
    version = VERSION
    author = AUTHOR
    description = "Placeholder analysis of dataset suitability for LoRA workflows."
    tags = ("lora", "analysis", "dataset")
    input_types = ("source_images",)
    output_types = ("json_report",)
    configurable_parameters = {
        "target_concept": {"type": "string", "default": ""},
    }
    requires = ("source_images",)
    produces = ("lora_dataset_report",)
    estimated_runtime = "seconds"
    estimated_memory = 64 * 1024 * 1024
    estimated_gpu = 0

    def run(self, context: PluginContext) -> PluginExecutionResult:
        return self._write_placeholder(
            context,
            "lora_dataset_report",
            "No LoRA suitability model is implemented yet.",
        )


class ArtifactRiskAnalyzer(_PlaceholderSupport, Analyzer):
    id = "lora.artifact_risk_analyzer"
    name = "Artifact Risk Analyzer"
    version = VERSION
    author = AUTHOR
    description = "Placeholder for future artifact-risk analysis."
    tags = ("lora", "analysis", "artifacts")
    input_types = ("source_images",)
    output_types = ("json_report",)
    configurable_parameters = {
        "sensitivity": {"type": "number", "default": 50},
    }
    requires = ("source_images",)
    produces = ("artifact_risk_report",)
    estimated_runtime = "seconds"
    estimated_memory = 64 * 1024 * 1024
    estimated_gpu = 0

    def run(self, context: PluginContext) -> PluginExecutionResult:
        return self._write_placeholder(
            context,
            "artifact_risk_report",
            "No AI artifact-risk model is implemented yet.",
        )


class DuplicateRiskAnalyzer(_PlaceholderSupport, Analyzer):
    id = "lora.duplicate_risk_analyzer"
    name = "Duplicate Risk Analyzer"
    version = VERSION
    author = AUTHOR
    description = "Placeholder for future LoRA-focused duplicate-risk policy."
    tags = ("lora", "analysis", "duplicates")
    input_types = ("source_images",)
    output_types = ("json_report",)
    configurable_parameters = {
        "similarity_threshold": {"type": "number", "default": 0.9},
    }
    requires = ("source_images",)
    produces = ("duplicate_risk_report",)
    estimated_runtime = "seconds"
    estimated_memory = 64 * 1024 * 1024
    estimated_gpu = 0

    def run(self, context: PluginContext) -> PluginExecutionResult:
        return self._write_placeholder(
            context,
            "duplicate_risk_report",
            "No additional duplicate analysis is implemented by this plugin yet.",
        )


class CaptionPlaceholderPlugin(_PlaceholderSupport, Captioner):
    id = "lora.caption_placeholder"
    name = "Caption Placeholder"
    version = VERSION
    author = AUTHOR
    description = "Proves captioner integration without generating captions."
    tags = ("lora", "captioning", "placeholder")
    capabilities = ("captioning",)
    input_types = ("source_images",)
    output_types = ("caption_plan",)
    configurable_parameters = {
        "caption_style": {"type": "string", "default": "descriptive"},
    }
    requires = ("source_images",)
    produces = ("caption_plan",)
    estimated_runtime = "instant"
    estimated_memory = 32 * 1024 * 1024
    estimated_gpu = 0

    def run(self, context: PluginContext) -> PluginExecutionResult:
        return self._write_placeholder(
            context,
            "caption_plan",
            "No captions were generated.",
        )


class LoraExportPlaceholderPlugin(_PlaceholderSupport, Exporter):
    id = "lora.export_placeholder"
    name = "LoRA Export Placeholder"
    version = VERSION
    author = AUTHOR
    description = "Proves exporter integration without copying or packaging images."
    tags = ("lora", "export", "placeholder")
    capabilities = ("lora_export",)
    input_types = ("source_images",)
    output_types = ("export_plan",)
    configurable_parameters = {
        "layout": {"type": "string", "default": "training_folder"},
    }
    requires = ("source_images",)
    produces = ("lora_export_plan",)
    estimated_runtime = "instant"
    estimated_memory = 32 * 1024 * 1024
    estimated_gpu = 0

    def run(self, context: PluginContext) -> PluginExecutionResult:
        return self._write_placeholder(
            context,
            "lora_export_plan",
            "No images were copied and no dataset was exported.",
        )


class WatercolorCleanupPlaceholderTransform(_PlaceholderSupport, Transform):
    id = "cleanup.watercolor_placeholder"
    name = "Watercolor Cleanup Placeholder"
    version = VERSION
    author = AUTHOR
    description = "Proves style-specific transform integration without editing images."
    tags = ("cleanup", "watercolor", "placeholder")
    capabilities = ("artifact_cleanup", "watercolor_cleanup")
    compatible_presets = ("watercolor_pencil_cleanup",)
    input_types = ("source_images",)
    output_types = ("transform_plan",)
    configurable_parameters = {
        "strength": {"type": "number", "default": 35},
    }
    requires = ("source_images",)
    produces = ("watercolor_cleanup_plan",)
    estimated_runtime = "instant"
    estimated_memory = 32 * 1024 * 1024
    estimated_gpu = 0
    estimated_quality_gain = 10

    def run(self, context: PluginContext) -> PluginExecutionResult:
        return self._write_placeholder(
            context,
            "watercolor_cleanup_plan",
            "No watercolor cleanup or image editing was performed.",
        )


class AnimeCleanupPlaceholderTransform(_PlaceholderSupport, Transform):
    id = "cleanup.anime_placeholder"
    name = "Anime Cleanup Placeholder"
    version = VERSION
    author = AUTHOR
    description = "Proves anime cleanup integration without editing images."
    tags = ("cleanup", "anime", "placeholder")
    capabilities = ("artifact_cleanup", "anime_lineart_cleanup")
    compatible_presets = ("anime_lineart_cleanup",)
    input_types = ("source_images",)
    output_types = ("transform_plan",)
    configurable_parameters = {
        "strength": {"type": "number", "default": 35},
    }
    requires = ("source_images",)
    produces = ("anime_cleanup_plan",)
    estimated_runtime = "instant"
    estimated_memory = 32 * 1024 * 1024
    estimated_gpu = 0
    estimated_quality_gain = 10

    def run(self, context: PluginContext) -> PluginExecutionResult:
        return self._write_placeholder(
            context,
            "anime_cleanup_plan",
            "No anime cleanup or image editing was performed.",
        )
