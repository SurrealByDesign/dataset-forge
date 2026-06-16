from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Mapping

from PIL import Image

from dataset_forge.analysis.duplicates import assign_duplicate_references
from dataset_forge.analysis.metrics import extract_image_metrics
from dataset_forge.core.config import default_quality_config_path, load_quality_weights
from dataset_forge.core.manifest import MANIFEST_FIELDS, empty_manifest_row, write_manifest
from dataset_forge.execution.base import PipelineContext, PipelineStage, StageResult
from dataset_forge.execution.hashing import hash_file
from dataset_forge.execution.pipeline import Pipeline
from dataset_forge.execution.registry import stage_registry
from dataset_forge.evidence import evidence_from_rows, write_evidence
from dataset_forge.recommendations.engine import (
    Recommendation,
    assess_dataset_quality,
    write_health_report,
    write_recommendations,
)
from dataset_forge.reporting import build_dataset_report, write_dataset_report
from dataset_forge.review.gallery import generate_review_gallery

MANIFEST_POINTER = "manifest_latest.json"


@stage_registry.register
class ScanStage(PipelineStage):
    id = "scan"
    name = "Scan"
    description = "Discover supported source images and record immutable metadata."
    produces = ("source_index", "scan_manifest")
    estimated_runtime = "seconds to minutes"
    estimated_ram = 64 * 1024 * 1024
    estimated_disk_write = 2 * 1024 * 1024
    estimated_temp_storage = 1 * 1024 * 1024

    def expected_outputs(self, context: PipelineContext) -> Mapping[str, Path]:
        return {
            "source_index": context.output_path / "source_index.json",
            "scan_manifest": context.output_path / "manifest_v1.csv",
        }

    def run(self, context: PipelineContext) -> StageResult:
        outputs = self.expected_outputs(context)
        rows = [_scan_row(path, context) for path in context.source_files]
        _write_json(
            outputs["source_index"],
            {
                "input_path": str(context.input_path),
                "images": [
                    {
                        "path": str(path),
                        "relative_path": path.relative_to(context.input_path).as_posix(),
                        "sha256": context.source_file_hashes[
                            path.relative_to(context.input_path).as_posix()
                        ],
                    }
                    for path in context.source_files
                ],
            },
        )
        write_manifest(outputs["scan_manifest"], rows)
        _write_manifest_pointer(context.output_path, outputs["scan_manifest"], 1)
        return StageResult(outputs, {"images": len(rows)})


@stage_registry.register
class AnalysisStage(PipelineStage):
    id = "analysis"
    name = "Analyze"
    description = "Calculate image metrics and duplicate references."
    requires = ("source_index", "scan_manifest")
    produces = ("analysis_manifest", "dataset_report")
    estimated_runtime = "seconds to minutes"
    estimated_ram = 256 * 1024 * 1024
    estimated_disk_write = 4 * 1024 * 1024
    estimated_temp_storage = 8 * 1024 * 1024

    def expected_outputs(self, context: PipelineContext) -> Mapping[str, Path]:
        return {
            "analysis_manifest": context.output_path / "manifest_v2.csv",
            "dataset_report": context.output_path / "dataset_report.json",
        }

    def run(self, context: PipelineContext) -> StageResult:
        outputs = self.expected_outputs(context)
        rows = [_analysis_row(path, context) for path in context.source_files]
        exact, probable = assign_duplicate_references(rows)
        write_manifest(outputs["analysis_manifest"], rows)
        write_dataset_report(
            outputs["dataset_report"],
            build_dataset_report(rows, exact, probable),
        )
        _write_manifest_pointer(context.output_path, outputs["analysis_manifest"], 2)
        return StageResult(
            outputs,
            {
                "images": len(rows),
                "exact_duplicates": exact,
                "probable_duplicates": probable,
            },
        )


@stage_registry.register
class RecommendationStage(PipelineStage):
    id = "recommend"
    name = "Recommend"
    description = "Score dataset health and create advisory recommendations."
    requires = ("analysis_manifest", "dataset_report")
    produces = (
        "recommendation_manifest",
        "dataset_health",
        "recommendations",
        "evidence",
    )
    estimated_runtime = "seconds"
    estimated_ram = 128 * 1024 * 1024
    estimated_disk_write = 4 * 1024 * 1024
    estimated_temp_storage = 2 * 1024 * 1024

    def expected_outputs(self, context: PipelineContext) -> Mapping[str, Path]:
        return {
            "recommendation_manifest": context.output_path / "manifest_v3.csv",
            "dataset_health": context.output_path / "dataset_health.json",
            "recommendations": context.output_path / "recommendations.csv",
            "evidence": context.output_path / "evidence.json",
        }

    def run(self, context: PipelineContext) -> StageResult:
        outputs = self.expected_outputs(context)
        rows = _read_manifest(context.artifacts["analysis_manifest"])
        quality_config = self.config.get("quality_config")
        weights = load_quality_weights(Path(quality_config) if quality_config else None)
        report, recommendations, summary = assess_dataset_quality(rows, weights)
        write_manifest(outputs["recommendation_manifest"], rows)
        write_health_report(outputs["dataset_health"], report)
        write_recommendations(outputs["recommendations"], recommendations)
        evidence = evidence_from_rows(rows)
        evidence.dataset_metrics.update(
            {
                "dataset_health_score": report.get("dataset_health_score", 0),
                "average_artifact_score": report.get(
                    "average_artifact_score", 0
                ),
                "average_texture_score": report.get(
                    "average_texture_score", 0
                ),
                "component_scores": report.get("component_scores", {}),
            }
        )
        write_evidence(outputs["evidence"], evidence)
        _write_manifest_pointer(
            context.output_path,
            outputs["recommendation_manifest"],
            3,
        )
        return StageResult(
            outputs,
            {
                "dataset_health_score": summary.dataset_health_score,
                "images_requiring_cleanup": summary.images_requiring_cleanup,
            },
        )


@stage_registry.register
class ReviewStage(PipelineStage):
    id = "review"
    name = "Review"
    description = "Generate the offline visual review gallery."
    requires = (
        "recommendation_manifest",
        "dataset_health",
        "recommendations",
    )
    produces = ("review_gallery",)
    estimated_runtime = "seconds to minutes"
    estimated_ram = 256 * 1024 * 1024
    estimated_disk_write = 32 * 1024 * 1024
    estimated_temp_storage = 16 * 1024 * 1024

    def expected_outputs(self, context: PipelineContext) -> Mapping[str, Path]:
        return {
            "review_gallery": context.output_path / "review_gallery" / "index.html"
        }

    def run(self, context: PipelineContext) -> StageResult:
        rows = _read_manifest(context.artifacts["recommendation_manifest"])
        with context.artifacts["dataset_health"].open(encoding="utf-8") as handle:
            health = json.load(handle)
        recommendations = _read_recommendations(context.artifacts["recommendations"])
        thumbnail_size = int(self.config.get("thumbnail_size", 256))
        create_thumbnails = not bool(self.config.get("no_thumbnails", False))
        index = generate_review_gallery(
            context.output_path,
            rows,
            recommendations,
            health,
            thumbnail_size=thumbnail_size,
            create_thumbnails=create_thumbnails,
        )
        return StageResult(
            {"review_gallery": index},
            {
                "thumbnail_size": thumbnail_size,
                "create_thumbnails": create_thumbnails,
            },
        )


def build_default_pipeline(config: dict[str, Any] | None = None) -> Pipeline:
    pipeline_config = dict(config or {})
    configured_quality = pipeline_config.get("quality_config")
    quality_path = (
        Path(configured_quality).expanduser().resolve()
        if configured_quality
        else default_quality_config_path()
    )
    return Pipeline(
        "default",
        [
            ScanStage(),
            AnalysisStage(),
            RecommendationStage(
                {
                    "quality_config": str(quality_path),
                    "quality_config_hash": hash_file(quality_path),
                }
            ),
            ReviewStage(
                {
                    "thumbnail_size": pipeline_config.get("thumbnail_size", 256),
                    "no_thumbnails": pipeline_config.get("no_thumbnails", False),
                }
            ),
        ],
        description="Read-only scan, analysis, recommendation, and review pipeline.",
        config=pipeline_config,
    )


def _scan_row(path: Path, context: PipelineContext) -> dict[str, object]:
    row = empty_manifest_row()
    row.update(_common_row(path, context, "scanned"))
    try:
        with Image.open(path) as image:
            row["image_width"], row["image_height"] = image.size
    except (OSError, ValueError):
        row["status"] = "error"
    return row


def _analysis_row(path: Path, context: PipelineContext) -> dict[str, object]:
    row = empty_manifest_row()
    row.update(_common_row(path, context, "analyzed"))
    try:
        metrics = extract_image_metrics(path)
        row.update(metrics.to_dict())
        row["image_width"] = row.pop("width")
        row["image_height"] = row.pop("height")
    except (OSError, ValueError):
        row["status"] = "error"
    return row


def _common_row(
    path: Path,
    context: PipelineContext,
    status: str,
) -> dict[str, object]:
    return {
        "original_path": str(path),
        "filename": path.name,
        "extension": path.suffix.lower(),
        "file_size": path.stat().st_size,
        "status": status,
        "preset_name": context.preset.name if context.preset else "",
        "preset_description": context.preset.description if context.preset else "",
        "preset_source": str(context.preset.source) if context.preset else "",
    }


def _read_manifest(path: Path) -> list[dict[str, object]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _read_recommendations(path: Path) -> list[Recommendation]:
    with path.open(newline="", encoding="utf-8") as handle:
        return [Recommendation(**row) for row in csv.DictReader(handle)]


def _write_manifest_pointer(output_path: Path, manifest: Path, version: int) -> None:
    _write_json(
        output_path / MANIFEST_POINTER,
        {"version": version, "path": manifest.name},
    )


def _write_json(path: Path, data: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
        handle.write("\n")


__all__ = [
    "AnalysisStage",
    "RecommendationStage",
    "ReviewStage",
    "ScanStage",
    "build_default_pipeline",
]
