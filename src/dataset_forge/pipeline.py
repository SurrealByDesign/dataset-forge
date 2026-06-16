from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from dataset_forge.analysis.duplicates import assign_duplicate_references
from dataset_forge.analysis.metrics import extract_image_metrics
from dataset_forge.core.config import load_quality_weights
from dataset_forge.core.logging import close_logger, create_file_logger
from dataset_forge.core.manifest import empty_manifest_row, write_manifest
from dataset_forge.core.paths import discover_images, resolve_directory
from dataset_forge.evidence import evidence_from_rows, write_evidence
from dataset_forge.presets import Preset
from dataset_forge.recommendations.engine import (
    HealthSummary,
    assess_dataset_quality,
    write_health_report,
    write_recommendations,
)
from dataset_forge.review.gallery import generate_review_gallery
from dataset_forge.reporting import build_dataset_report, write_dataset_report
from dataset_forge.execution import (
    Pipeline,
    PipelineContext,
    PipelineDependencyError,
    PipelineExecutionError,
    PipelineRunSummary,
    PipelineStage,
    StageResult,
)

__all__ = [
    "Pipeline",
    "PipelineContext",
    "PipelineDependencyError",
    "PipelineExecutionError",
    "PipelineOptions",
    "PipelineRunSummary",
    "PipelineStage",
    "PipelineSummary",
    "StageResult",
    "run_pipeline",
]


@dataclass(frozen=True)
class PipelineOptions:
    input_path: Path
    output_path: Path
    recursive: bool = False
    limit: int | None = None
    dry_run: bool = False
    analyze: bool = False
    health_report: bool = False
    quality_config: Path | None = None
    review_gallery: bool = False
    thumbnail_size: int = 256
    no_thumbnails: bool = False
    preset: Preset | None = None


@dataclass(frozen=True)
class PipelineSummary:
    images_found: int
    images_processed: int
    skipped_files: int
    errors: int
    estimated_bytes: int = 0
    health: HealthSummary | None = None


def run_pipeline(options: PipelineOptions) -> PipelineSummary:
    input_path = resolve_directory(options.input_path)
    output_path = resolve_directory(options.output_path)
    _validate_options(options, input_path, output_path)
    analyze = options.analyze or options.health_report or options.review_gallery
    assess_health = options.health_report or options.review_gallery
    quality_weights = (
        load_quality_weights(options.quality_config)
        if assess_health
        else None
    )

    discovery = discover_images(
        input_path,
        recursive=options.recursive,
        limit=options.limit,
        excluded_root=output_path,
    )
    _print_plan(options, output_path, discovery.images)

    if options.dry_run:
        return PipelineSummary(
            images_found=len(discovery.images),
            images_processed=0,
            skipped_files=discovery.skipped_files,
            errors=0,
        )

    output_path.mkdir(parents=True, exist_ok=True)
    logger = create_file_logger(output_path)
    logger.info(
        "Read-only scan started: input=%s recursive=%s analyze=%s "
        "health_report=%s review_gallery=%s",
        input_path,
        options.recursive,
        analyze,
        assess_health,
        options.review_gallery,
    )
    if options.preset:
        logger.info(
            "Preset selected: name=%s source=%s",
            options.preset.name,
            options.preset.source,
        )
    else:
        logger.info("Preset selected: none")

    rows: list[dict[str, object]] = []
    processed = 0
    errors = 0
    for source in discovery.images:
        row = _inspect_image(source, options.preset, analyze)
        if row["status"] == "error":
            errors += 1
            logger.error("Could not inspect image: %s", source)
        else:
            processed += 1
            logger.info("Analyzed %s" if analyze else "Scanned %s", source)
        rows.append(row)

    duplicate_count = 0
    probable_duplicate_count = 0
    if analyze:
        duplicate_count, probable_duplicate_count = assign_duplicate_references(rows)
        logger.info(
            "Duplicates detected: exact=%s probable=%s",
            duplicate_count,
            probable_duplicate_count,
        )

    health_summary = None
    health_report = None
    recommendations = None
    if assess_health and quality_weights:
        health_report, recommendations, health_summary = assess_dataset_quality(
            rows,
            quality_weights,
        )

    manifest_path = output_path / "manifest.csv"
    write_manifest(manifest_path, rows)
    logger.info("Manifest written: %s", manifest_path)

    if analyze:
        report_path = output_path / "dataset_report.json"
        report = build_dataset_report(rows, duplicate_count, probable_duplicate_count)
        write_dataset_report(report_path, report)
        logger.info("Dataset report written: %s", report_path)
        evidence = evidence_from_rows(rows)
        if health_report is not None:
            evidence.dataset_metrics.update(
                {
                    "dataset_health_score": health_report.get(
                        "dataset_health_score", 0
                    ),
                    "average_artifact_score": health_report.get(
                        "average_artifact_score", 0
                    ),
                    "average_texture_score": health_report.get(
                        "average_texture_score", 0
                    ),
                }
            )
        evidence_path = output_path / "evidence.json"
        write_evidence(evidence_path, evidence)
        logger.info("Unified evidence written: %s", evidence_path)

    if health_report is not None and recommendations is not None:
        health_path = output_path / "dataset_health.json"
        recommendations_path = output_path / "recommendations.csv"
        write_health_report(health_path, health_report)
        write_recommendations(recommendations_path, recommendations)
        logger.info("Dataset health report written: %s", health_path)
        logger.info("Image recommendations written: %s", recommendations_path)

    if (
        options.review_gallery
        and health_report is not None
        and recommendations is not None
    ):
        gallery_index = generate_review_gallery(
            output_path,
            rows,
            recommendations,
            health_report,
            thumbnail_size=options.thumbnail_size,
            create_thumbnails=not options.no_thumbnails,
        )
        logger.info("Review gallery written: %s", gallery_index)

    close_logger(logger)
    return PipelineSummary(
        images_found=len(discovery.images),
        images_processed=processed,
        skipped_files=discovery.skipped_files,
        errors=errors,
        health=health_summary,
    )


def _validate_options(options: PipelineOptions, input_path: Path, output_path: Path) -> None:
    if not input_path.is_dir():
        raise ValueError(f"Input folder does not exist or is not a directory: {input_path}")
    if input_path == output_path:
        raise ValueError("Input and output folders must be different.")
    if options.limit is not None and options.limit < 1:
        raise ValueError("--limit must be at least 1.")
    if options.thumbnail_size < 1:
        raise ValueError("--thumbnail-size must be at least 1.")


def _inspect_image(
    path: Path,
    preset: Preset | None,
    analyze: bool,
) -> dict[str, object]:
    row = empty_manifest_row()
    row.update(
        {
            "original_path": str(path),
            "filename": path.name,
            "extension": path.suffix.lower(),
            "file_size": path.stat().st_size,
            "status": "analyzed" if analyze else "scanned",
            "preset_name": preset.name if preset else "",
            "preset_description": preset.description if preset else "",
            "preset_source": str(preset.source) if preset else "",
        }
    )
    try:
        if analyze:
            metrics = extract_image_metrics(path)
            row.update(metrics.to_dict())
            row["image_width"] = row.pop("width")
            row["image_height"] = row.pop("height")
        else:
            with Image.open(path) as image:
                row["image_width"], row["image_height"] = image.size
    except (OSError, ValueError):
        row["status"] = "error"
    return row


def _print_plan(
    options: PipelineOptions,
    output_path: Path,
    images: list[Path],
) -> None:
    mode = "DRY RUN" if options.dry_run else "PLAN"
    analyze = options.analyze or options.health_report or options.review_gallery
    action = "analyze" if analyze else "scan"
    print(f"{mode}: {action} {len(images)} supported image(s)")
    print("Source images are read-only and will not be copied or modified.")
    if options.preset:
        print(f"Selected preset: {options.preset.name} ({options.preset.source})")
    else:
        print("Selected preset: none")
    if options.dry_run:
        print(f"Would write manifest: {output_path / 'manifest.csv'}")
        print(f"Would write log under: {output_path / 'logs'}")
        if analyze:
            print(f"Would write dataset report: {output_path / 'dataset_report.json'}")
        if options.health_report or options.review_gallery:
            print(f"Would write health report: {output_path / 'dataset_health.json'}")
            print(
                f"Would write recommendations: "
                f"{output_path / 'recommendations.csv'}"
            )
        if options.review_gallery:
            print(
                f"Would write review gallery: "
                f"{output_path / 'review_gallery' / 'index.html'}"
            )
            if not options.no_thumbnails:
                print(
                    f"Would write thumbnails under: "
                    f"{output_path / 'review_gallery' / 'thumbnails'}"
                )
