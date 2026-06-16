"""Dataset Forge Inspect — v1 spine runner.

Wires the full v1 pipeline:
    Dataset → DatasetContext → TextureAnalyzer → Finding → Report

Entry point: `run_inspect(dataset_path, output_dir)`.

Does not implement cleanup, AI, plugins, UI, or any feature outside
the v1 vertical slice. All measurement logic lives in the modules it calls.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from pathlib import Path

from dataset_forge.analysis.metrics import extract_image_metrics
from dataset_forge.analysis.texture import evaluate_texture
from dataset_forge.analyzers.texture import TextureAnalyzer
from dataset_forge.context import (
    CONTEXT_SCHEMA_VERSION,
    AspectRatioStats,
    DatasetContext,
    FrequencyDistributions,
    ResolutionStats,
    TextureDistributions,
)
from dataset_forge.discovery import discover_images
from dataset_forge.finding import Finding
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
    image_count: int
    analyzed_count: int
    error_count: int
    total_findings: int
    images_with_findings: int
    images_clean: int
    severity_counts: dict[str, int]


# ---------------------------------------------------------------------------
# DatasetContext builder
# ---------------------------------------------------------------------------

def _build_context(image_paths: list[Path]) -> DatasetContext:
    """Measure all images and assemble a DatasetContext.

    Uses evaluate_texture() for microtexture measurements and
    extract_image_metrics() for resolution/aspect-ratio/hash data.
    Falls back gracefully when individual images cannot be opened.
    """
    widths: list[int] = []
    heights: list[int] = []
    aspects: list[float] = []
    microtextures: list[float] = []
    file_hashes: dict[str, list[Path]] = {}  # hash → paths
    error_count = 0

    for path in image_paths:
        # Resolution + hash (metrics module handles its own errors)
        try:
            m = extract_image_metrics(path)
            widths.append(m.width)
            heights.append(m.height)
            aspects.append(m.aspect_ratio)
            fh = m.file_hash
            file_hashes.setdefault(fh, []).append(path)
        except Exception:
            error_count += 1
            continue

        # Texture measurement (texture module handles its own errors)
        tex = evaluate_texture(path)
        if tex.status == "analyzed":
            microtextures.append(tex.microtexture_density_score)

    # Resolution stats
    if widths:
        res = ResolutionStats(
            mean_w=statistics.mean(widths),
            mean_h=statistics.mean(heights),
            stddev_w=statistics.pstdev(widths),
            stddev_h=statistics.pstdev(heights),
            min_w=min(widths),
            min_h=min(heights),
            max_w=max(widths),
            max_h=max(heights),
            sample_count=len(widths),
        )
        ar = AspectRatioStats(
            mean=statistics.mean(aspects),
            stddev=statistics.pstdev(aspects),
            min=min(aspects),
            max=max(aspects),
            sample_count=len(aspects),
        )
    else:
        res = ResolutionStats.empty()
        ar = AspectRatioStats.empty()

    # Texture distributions
    if microtextures:
        n = len(microtextures)
        sorted_mt = sorted(microtextures)
        tex_dist = TextureDistributions(
            mean=statistics.mean(microtextures),
            stddev=statistics.pstdev(microtextures),
            p10=sorted_mt[max(0, int(math.floor(n * 0.10)))],
            p90=sorted_mt[min(n - 1, int(math.floor(n * 0.90)))],
            sample_count=n,
        )
    else:
        tex_dist = TextureDistributions.empty()

    # Frequency distributions — not yet implemented; placeholder baseline
    freq_dist = FrequencyDistributions(
        dominant_freq_mean=0.0,
        dominant_freq_stddev=0.0,
        sample_count=0,
    )

    # Duplicate groups
    dup_groups = tuple(
        tuple(paths)
        for paths in file_hashes.values()
        if len(paths) > 1
    )
    all_hashes = frozenset(file_hashes.keys())

    return DatasetContext(
        schema_version=CONTEXT_SCHEMA_VERSION,
        analyzer_versions={"texture_analyzer": "v1"},
        image_paths=tuple(image_paths),
        image_count=len(image_paths),
        error_count=error_count,
        resolution_stats=res,
        aspect_ratio_stats=ar,
        texture_distributions=tex_dist,
        frequency_distributions=freq_dist,
        duplicate_hashes=all_hashes,
        duplicate_groups=dup_groups,
    )


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run_inspect(
    dataset_path: Path,
    output_dir: Path,
    *,
    recursive: bool = False,
    limit: int | None = None,
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

    # 2. Build context
    context = _build_context(image_paths)

    # 3. Analyze
    analyzer = TextureAnalyzer()
    findings: list[Finding] = []
    for path in image_paths:
        findings.extend(analyzer.analyze(path, context))

    # 4. Write reports
    json_path, txt_path = write_inspection_report(
        findings, context, output_dir, dataset_path=dataset_path
    )

    # 5. Summarize
    affected = {str(f.image_path) for f in findings}
    sev_counts: dict[str, int] = {}
    for f in findings:
        sev_counts[f.severity.name] = sev_counts.get(f.severity.name, 0) + 1

    return InspectResult(
        dataset_path=dataset_path,
        output_dir=output_dir,
        json_report=json_path,
        txt_report=txt_path,
        image_count=context.image_count,
        analyzed_count=context.analyzed_count,
        error_count=context.error_count,
        total_findings=len(findings),
        images_with_findings=len(affected),
        images_clean=context.image_count - len(affected),
        severity_counts=sev_counts,
    )
