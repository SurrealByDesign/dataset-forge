from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from dataset_forge.cleanup.profiles import CleanupProfile, load_cleanup_profile
from dataset_forge.cleanup.traditional import (
    generate_comparison_sheet,
    process_traditional_cleanup,
)
from dataset_forge.plugins.sdk import PluginContext, PluginExecutionResult, Transform

AUTHOR = "Dataset Forge"
VERSION = "0.1.0"


class TraditionalCleanupTransform(Transform):
    """Deterministic cleanup chain with profile-gated real operations."""

    id = "cleanup.traditional_cleanup"
    name = "Traditional Cleanup"
    version = "0.2.0"
    author = AUTHOR
    description = (
        "Deterministic cleanup operation chain driven by a cleanup profile. "
        "Profiles with acceptance checks can execute conservative pixel cleanup."
    )
    tags = ("cleanup", "traditional", "deterministic")
    capabilities = ("artifact_cleanup", "traditional_cleanup")
    compatible_presets = (
        "watercolor_pencil_cleanup",
        "anime_lineart_cleanup",
        "general_artifact_cleanup",
        "general_ai_artifact_cleanup",
        "photoreal_cleanup",
    )
    input_types = ("source_images",)
    output_types = ("image", "json_report")
    configurable_parameters = {
        "profile": {"type": "string", "default": "watercolor_light"},
    }
    requires = ("source_images",)
    produces = ("traditional_cleanup_plan",)
    estimated_runtime = "instant"
    estimated_memory = 32 * 1024 * 1024
    estimated_gpu = 0
    estimated_quality_gain = 0

    def run(self, context: PluginContext) -> PluginExecutionResult:
        profile_name = str(self.config.get("profile", "watercolor_light"))
        profile = load_cleanup_profile(profile_name)

        output_dir = context.output_path / "precleanup"
        output_dir.mkdir(parents=True, exist_ok=True)

        artifacts: dict[str, Path] = {}
        accepted = 0
        rejected = 0
        for source in context.source_files:
            target = _unique_path(output_dir, source.name)
            if profile.acceptance_checks:
                result = process_traditional_cleanup(source, target, profile)
                metadata_path = result["metadata_path"]
                if result["accepted"]:
                    artifacts[source.name] = target
                    accepted += 1
                else:
                    rejected += 1
            else:
                shutil.copy2(source, target)
                metadata_path = write_traditional_cleanup_sidecar(
                    source, target, profile
                )
                artifacts[source.name] = target
            artifacts[f"{source.name}.metadata"] = metadata_path
        comparison_sheet = None
        if profile.acceptance_checks:
            comparison_sheet = generate_comparison_sheet(output_dir)
            artifacts["comparison_sheet"] = comparison_sheet

        return PluginExecutionResult(
            plugin_id=self.id,
            status="success",
            artifacts=artifacts,
            details={
                "placeholder": not bool(profile.acceptance_checks),
                "profile": profile.name,
                "requested_operations": [op.to_dict() for op in profile.operations],
                "source_images_modified": False,
                "accepted": accepted,
                "rejected": rejected,
                "comparison_sheet": str(comparison_sheet) if comparison_sheet else None,
            },
        )


def write_traditional_cleanup_sidecar(
    source: Path, target: Path, profile: CleanupProfile
) -> Path:
    """Write the TraditionalCleanupTransform metadata sidecar for ``target``."""

    metadata_path = target.with_name(target.name + ".json")
    metadata = {
        "plugin_id": TraditionalCleanupTransform.id,
        "profile": profile.name,
        "requested_operations": [op.to_dict() for op in profile.operations],
        "parameters": {op.name: dict(op.parameters) for op in profile.operations},
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_hash": _sha256(source),
        "output_hash": _sha256(target),
        "placeholder": True,
    }
    metadata_path.write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    return metadata_path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _unique_path(directory: Path, filename: str) -> Path:
    candidate = directory / filename
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    counter = 2
    while True:
        candidate = directory / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1
