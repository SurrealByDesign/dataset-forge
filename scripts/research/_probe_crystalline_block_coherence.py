"""
Crystalline block-coherence probe -- Candidate 4.

Research-only script. Does not modify production analyzer code, measurement
code, benchmark schemas, reports, CLI behavior, thresholds, or calibration
status.

Candidate 4 is a sanity check for Candidate 1. It asks whether Candidate 1's
failure came from full-resolution connected components, or from the broader
contiguous-region-size hypothesis itself.

It reuses Candidate 1's population-selection logic and high-frequency map, but
changes the granularity:
  - block-pool the high-frequency map into coarse blocks
  - apply the same threshold-rule shape on the coarse grid
  - run connected components on the coarse binary mask
  - compute block-level patch statistics
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT / "src"))

from dataset_forge.measurements import measure_image
from _probe_crystalline_patch_coherence import (
    ANALYSIS_MAX,
    DATASET,
    REPORT,
    REVIEW,
    _assign_cluster,
    _cohen_d,
    _finding_sets,
    _fmt,
    _group_stats,
    _image_index,
    _load_json,
    _pearson,
    _percentile,
)

OUT_DIR = _ROOT / "benchmarks" / "results" / "probe_crystalline_block_coherence"
BLOCK_SIZE = 16


def _block_pool_mean(hf_map: np.ndarray, block_size: int) -> np.ndarray:
    h, w = hf_map.shape
    block_h = h // block_size
    block_w = w // block_size
    if block_h == 0 or block_w == 0:
        return np.empty((0, 0), dtype=np.float32)

    cropped = hf_map[: block_h * block_size, : block_w * block_size]
    blocks = cropped.reshape(block_h, block_size, block_w, block_size)
    return blocks.mean(axis=(1, 3)).astype(np.float32)


def measure_block_coherence(path: Path, block_size: int = BLOCK_SIZE) -> dict | None:
    """Measure Candidate 4 block-level patch statistics for one image."""
    try:
        img = Image.open(path).convert("RGB")
        img.thumbnail((ANALYSIS_MAX, ANALYSIS_MAX), Image.Resampling.LANCZOS)
        rgb = np.asarray(img, dtype=np.uint8)
    except Exception:
        return None

    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32)
    if min(gray.shape) < block_size * 2:
        return None

    # Same high-frequency map as Candidate 1. Only the connected-component
    # granularity changes below.
    blur = cv2.GaussianBlur(gray, (0, 0), 1.2)
    hf_map = np.abs(gray - blur)
    block_hf = _block_pool_mean(hf_map, block_size)
    if block_hf.size == 0:
        return None

    nonzero = block_hf[block_hf > 0.0]
    threshold = max(
        _percentile(nonzero, 90.0),
        float(np.mean(block_hf) + 1.5 * np.std(block_hf)),
        3.0,
    )
    elevated_mask = block_hf >= threshold
    mask_u8 = elevated_mask.astype(np.uint8)

    num_labels, _, stats, _ = cv2.connectedComponentsWithStats(mask_u8, connectivity=8)
    areas = [
        int(stats[i, cv2.CC_STAT_AREA])
        for i in range(1, num_labels)
        if int(stats[i, cv2.CC_STAT_AREA]) > 0
    ]
    patch_areas = [area for area in areas if area >= 2]

    total_blocks = int(block_hf.shape[0] * block_hf.shape[1])
    elevated_blocks = int(sum(areas))
    coherent_blocks = int(sum(patch_areas))
    largest_patch = max(patch_areas) if patch_areas else 0
    patch_area_p90 = _percentile(patch_areas, 90.0)
    patch_area_mean = statistics.mean(patch_areas) if patch_areas else 0.0
    patch_area_median = statistics.median(patch_areas) if patch_areas else 0.0
    patch_area_cv = (
        statistics.pstdev(patch_areas) / patch_area_mean
        if len(patch_areas) > 1 and patch_area_mean > 0
        else 0.0
    )
    elevated_area_ratio = elevated_blocks / total_blocks if total_blocks else 0.0
    coherent_area_ratio = coherent_blocks / total_blocks if total_blocks else 0.0
    coherent_fraction = coherent_blocks / elevated_blocks if elevated_blocks else 0.0

    patch_area_score = 100.0 * (1.0 - math.exp(-patch_area_p90 / 4.0))
    block_coherence_score = patch_area_score * coherent_fraction

    return {
        "block_size": block_size,
        "grid_height": int(block_hf.shape[0]),
        "grid_width": int(block_hf.shape[1]),
        "hf_mean": round(float(np.mean(hf_map)), 4),
        "hf_p90": round(_percentile(hf_map.ravel(), 90.0), 4),
        "block_hf_mean": round(float(np.mean(block_hf)), 4),
        "block_hf_p90": round(_percentile(block_hf.ravel(), 90.0), 4),
        "block_hf_threshold": round(threshold, 4),
        "elevated_area_ratio": round(elevated_area_ratio, 6),
        "component_count": len(areas),
        "patch_count": len(patch_areas),
        "patch_area_mean": round(float(patch_area_mean), 4),
        "patch_area_median": round(float(patch_area_median), 4),
        "patch_area_p90": round(float(patch_area_p90), 4),
        "patch_area_max": largest_patch,
        "patch_area_cv": round(float(patch_area_cv), 4),
        "coherent_area_ratio": round(coherent_area_ratio, 6),
        "coherent_fraction": round(coherent_fraction, 6),
        "block_coherence_score": round(float(block_coherence_score), 4),
    }


def build_records(
    dataset_path: Path,
    report: dict,
    review: dict,
    block_size: int = BLOCK_SIZE,
) -> list[dict]:
    texture, crystalline = _finding_sets(report)
    images = _image_index(dataset_path)
    rows: list[dict] = []

    for name, rv in review.get("reviews", {}).items():
        if name not in crystalline or name in texture:
            continue
        image_path = images.get(name)
        if image_path is None:
            continue

        measurements = measure_image(image_path)
        texture_result = measurements.texture
        if texture_result.status != "analyzed":
            continue

        base = {
            "name": name,
            "path": str(image_path),
            "review": rv.get("review", ""),
            "grain": texture_result.pencil_grain_score,
            "smoothness": texture_result.watercolor_smoothness_score,
            "microtexture": texture_result.microtexture_density_score,
        }
        base["cluster"] = _assign_cluster(base)

        if base["review"] == "DISAGREE":
            base["group"] = "TP"
        elif base["review"] == "AGREE" and base["cluster"] == "C":
            base["group"] = "Cluster-C FP"
        else:
            base["group"] = "Other crystalline-only"

        candidate = measure_block_coherence(image_path, block_size)
        if candidate is None:
            continue
        rows.append({**base, **candidate})

    return rows


def verdict_for(d_value: float | None, correlations: dict[str, float | None]) -> str:
    if d_value is None:
        return "INCONCLUSIVE"
    max_existing_corr = max(
        (abs(v) for v in correlations.values() if v is not None),
        default=0.0,
    )
    if d_value >= 0.8 and max_existing_corr <= 0.7:
        return "ADOPT"
    if abs(d_value) < 0.35:
        return "DEFER"
    return "INCONCLUSIVE"


def render_report(records: list[dict]) -> str:
    metric = "block_coherence_score"
    tp = [r for r in records if r["group"] == "TP"]
    cluster_c_fp = [r for r in records if r["group"] == "Cluster-C FP"]
    tp_values = [float(r[metric]) for r in tp]
    fp_values = [float(r[metric]) for r in cluster_c_fp]
    d_value = _cohen_d(tp_values, fp_values)

    candidate_values = [float(r[metric]) for r in records]
    correlations = {
        "grain": _pearson(candidate_values, [float(r["grain"]) for r in records]),
        "smoothness": _pearson(candidate_values, [float(r["smoothness"]) for r in records]),
        "microtexture": _pearson(candidate_values, [float(r["microtexture"]) for r in records]),
    }
    verdict = verdict_for(d_value, correlations)

    lines = [
        "Dataset Forge Crystalline Block-Coherence Probe",
        "=" * 58,
        "Candidate 4: Candidate 1 high-frequency map, block-pooled before connected components",
        "",
        "Scope: evidence only; no analyzer, measurement, CLI, or benchmark changes.",
        "",
        "Population",
        "-" * 58,
        f"Measured crystalline-only reviewed images: {len(records)}",
        f"TP group:         {len(tp)} reviewer DISAGREE crystalline-only findings",
        f"Cluster-C FP:     {len(cluster_c_fp)} reviewer AGREE crystalline-only threshold-fringe findings",
        "",
        "TP vs Cluster-C FP Comparison",
        "-" * 58,
    ]

    for group in ["TP", "Cluster-C FP"]:
        stats = _group_stats(records, group, metric)
        lines.append(
            f"{group:<14} n={stats['n']:>2}  mean={_fmt(stats['mean'])}  "
            f"median={_fmt(stats['median'])}  min={_fmt(stats['min'])}  max={_fmt(stats['max'])}"
        )
    lines.extend([
        f"Cohen's d ({metric}, TP - Cluster-C FP): {_fmt(d_value)}",
        "",
        "Pearson Correlation",
        "-" * 58,
    ])
    for name, value in correlations.items():
        lines.append(f"{metric} vs {name:<12} r = {_fmt(value, 4)}")

    lines.extend([
        "",
        "Block-Level Patch Statistics Summary",
        "-" * 58,
    ])
    for metric_name in [
        "elevated_area_ratio",
        "component_count",
        "patch_count",
        "patch_area_mean",
        "patch_area_p90",
        "patch_area_max",
        "coherent_fraction",
        "coherent_area_ratio",
    ]:
        tp_stats = _group_stats(records, "TP", metric_name)
        fp_stats = _group_stats(records, "Cluster-C FP", metric_name)
        lines.append(
            f"{metric_name:<22} TP mean={_fmt(tp_stats['mean'])}  "
            f"Cluster-C FP mean={_fmt(fp_stats['mean'])}"
        )

    lines.extend([
        "",
        "Verdict",
        "-" * 58,
        verdict,
        "",
        "Verdict rule: ADOPT requires d >= 0.8 and no strong correlation "
        "(|r| <= 0.7) with grain, smoothness, or microtexture. DEFER applies "
        "when |d| < 0.35. Otherwise the evidence is INCONCLUSIVE.",
        "",
        "Full Table",
        "-" * 58,
        (
            f"{'group':<20} {'cluster':<7} {'score':>8} {'grain':>7} "
            f"{'smooth':>7} {'micro':>7} {'patch_p90':>9} {'patches':>7}  name"
        ),
    ])
    for row in sorted(records, key=lambda r: (r["group"], -r[metric], r["name"])):
        lines.append(
            f"{row['group']:<20} {row['cluster']:<7} {row[metric]:>8.3f} "
            f"{row['grain']:>7.1f} {row['smoothness']:>7.1f} "
            f"{row['microtexture']:>7.1f} {row['patch_area_p90']:>9.1f} "
            f"{row['patch_count']:>7}  {row['name']}"
        )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Research-only crystalline block-coherence probe."
    )
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--report", type=Path, default=REPORT)
    parser.add_argument("--review", type=Path, default=REVIEW)
    parser.add_argument("--output-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--block-size", type=int, default=BLOCK_SIZE)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dataset_path = args.dataset.expanduser().resolve()
    report_path = args.report.expanduser().resolve()
    review_path = args.review.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()

    if not dataset_path.is_dir():
        print(f"ERROR: dataset not found: {dataset_path}", file=sys.stderr)
        return 1
    if not report_path.exists():
        print(f"ERROR: report not found: {report_path}", file=sys.stderr)
        return 1
    if not review_path.exists():
        print(f"ERROR: review not found: {review_path}", file=sys.stderr)
        return 1
    if args.block_size <= 0:
        print("ERROR: --block-size must be positive", file=sys.stderr)
        return 1

    output_dir.mkdir(parents=True, exist_ok=True)
    report = _load_json(report_path)
    review = _load_json(review_path)
    records = build_records(dataset_path, report, review, args.block_size)

    data_path = output_dir / "probe_crystalline_block_coherence_data.json"
    report_out = output_dir / "probe_crystalline_block_coherence_report.txt"
    data_path.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    report_text = render_report(records)
    report_out.write_text(report_text, encoding="utf-8")

    print(report_text, end="")
    print(f"\nWrote: {data_path}")
    print(f"Wrote: {report_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
