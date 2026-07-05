"""Dataset Forge Inspect — v1 spine runner.

Wires the full v1 pipeline:
    Dataset → DatasetContext → TextureAnalyzer → Finding → Report

Entry point: `run_inspect(dataset_path, output_dir)`.

Does not implement cleanup, AI, plugins, UI, or any feature outside
the v1 vertical slice. All measurement logic lives in the modules it calls.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dataset_forge.analyzers.registry import create_analyzers
from dataset_forge.context import DatasetContext
from dataset_forge.context_builder import build_dataset_context
from dataset_forge.discovery import discover_images
from dataset_forge.finding import Finding
from dataset_forge.inspect_gallery import write_inspection_gallery
from dataset_forge.measurements import ImageMeasurements
from dataset_forge.recommendation_summary import (
    build_recommendation_summary,
    write_recommendation_summary_files,
)
from dataset_forge.report import write_inspection_report


# ---------------------------------------------------------------------------
# Result object returned to the caller (and eventually the CLI)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class InspectResult:
    dataset_path: Path
    output_dir: Path
    json_report: Path
    txt_report: Path
    recommendation_json: Path
    recommendation_markdown: Path
    image_count: int
    analyzed_count: int
    error_count: int
    total_findings: int
    images_with_findings: int
    images_clean: int
    severity_counts: dict[str, int]
    ready_for_training_count: int
    needs_review_count: int
    priority_review_count: int
    gallery_path: Path | None = None


# ---------------------------------------------------------------------------
# DatasetContext builder
# ---------------------------------------------------------------------------

def _build_context(
    image_paths: list[Path],
) -> tuple[DatasetContext, dict[str, dict], dict[Path, ImageMeasurements]]:
    """Measure all images and assemble a DatasetContext.

    Uses measure_image() for shared analyzer measurements and
    extract_image_metrics() for resolution/aspect-ratio/hash data.
    Falls back gracefully when individual images cannot be opened.

    Returns (context, image_scores) where image_scores maps str(path) →
    raw metric dict for every successfully measured image. These scores
    are captured here for free — no extra image reads needed downstream.
    """
    result = build_dataset_context(image_paths)
    return result.context, result.image_scores, result.measurements_by_path


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run_inspect(
    dataset_path: Path,
    output_dir: Path,
    *,
    recursive: bool = False,
    limit: int | None = None,
    gallery: bool = False,
) -> InspectResult:
    """Run the full v1 inspect pipeline on a dataset folder.

    1. Discover images.
    2. Build DatasetContext (measure texture/resolution distributions).
    3. Run TextureAnalyzer on every image.
    4. Write JSON + TXT reports.
    5. Return InspectResult for the CLI to display.
    """
    dataset_path = dataset_path.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()

    if not dataset_path.is_dir():
        raise ValueError(f"Dataset path is not a directory: {dataset_path}")

    # 1. Discover
    discovery = discover_images(
        dataset_path,
        recursive=recursive,
        limit=limit,
        excluded_root=output_dir,
    )
    image_paths = discovery.images

    # 2. Build context — also returns per-image raw scores at no extra I/O cost
    context, image_scores, measurements_by_path = _build_context(image_paths)

    # 3. Analyze — run all registered analyzers
    analyzers = create_analyzers()
    findings: list[Finding] = []
    for path in image_paths:
        measurements = measurements_by_path.get(path)
        for analyzer in analyzers:
            findings.extend(analyzer.analyze(path, context, measurements=measurements))

    # 4. Write reports
    json_path, txt_path = write_inspection_report(
        findings, context, output_dir,
        dataset_path=dataset_path,
        image_scores=image_scores,
    )

    # 5. Write additive Recommendation Summary sidecars
    recommendation_summary = build_recommendation_summary(findings, context)
    recommendation_json, recommendation_markdown = write_recommendation_summary_files(
        recommendation_summary,
        output_dir,
    )

    # 6. Optionally write gallery PNG
    gallery_path: Path | None = None
    if gallery and image_scores:
        gallery_path = write_inspection_gallery(
            findings, context,
            output_dir / "inspection_gallery.png",
            image_scores,
        )

    # 7. Summarize
    affected = {str(f.image_path) for f in findings}
    sev_counts: dict[str, int] = {}
    for f in findings:
        sev_counts[f.severity.name] = sev_counts.get(f.severity.name, 0) + 1

    return InspectResult(
        dataset_path=dataset_path,
        output_dir=output_dir,
        json_report=json_path,
        txt_report=txt_path,
        recommendation_json=recommendation_json,
        recommendation_markdown=recommendation_markdown,
        image_count=context.image_count,
        analyzed_count=context.analyzed_count,
        error_count=context.error_count,
        total_findings=len(findings),
        images_with_findings=len(affected),
        images_clean=context.image_count - len(affected),
        severity_counts=sev_counts,
        ready_for_training_count=recommendation_summary.ready_for_training_count,
        needs_review_count=recommendation_summary.needs_review_count,
        priority_review_count=recommendation_summary.priority_review_count,
        gallery_path=gallery_path,
    )
