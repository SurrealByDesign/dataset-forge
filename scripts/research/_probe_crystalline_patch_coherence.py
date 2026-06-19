"""
Crystalline patch-coherence probe -- Candidate 1.

Research-only script. Does not modify production analyzer code, measurement
code, benchmark schemas, reports, CLI behavior, or thresholds.

Candidate 1 measures whether crystalline true positives differ from the
Cluster-C false-positive population by the spatial coherence of elevated
high-frequency patches:
  - high-frequency map
  - elevated-amplitude mask
  - connected components
  - patch-area statistics

Outputs:
  - TP vs Cluster-C FP comparison
  - Cohen's d
  - Pearson correlation against grain, smoothness, and microtexture
  - evidence-only verdict: ADOPT, DEFER, or INCONCLUSIVE
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np
from PIL import Image

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT / "src"))

from dataset_forge.measurements import measure_image

DATASET = Path("C:/Users/someo/Desktop/ANTHROPOMORPHS")
REPORT = DATASET / "inspect_output" / "inspection_report.json"
REVIEW = DATASET / "decision_review.json"
OUT_DIR = _ROOT / "benchmarks" / "results" / "probe_crystalline_patch_coherence"

ANALYSIS_MAX = 512
TEXTURE_CATEGORY = "texture.high_microtexture"
CRYSTALLINE_CATEGORY = "artifact.crystalline_faceting"


def _load_json(path: Path) -> dict:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Unexpected JSON shape in {path}")
    return raw


def _image_index(dataset_path: Path) -> dict[str, Path]:
    exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
    return {
        path.name: path
        for path in dataset_path.rglob("*")
        if path.is_file() and path.suffix.lower() in exts
    }


def _finding_sets(report: dict) -> tuple[set[str], dict[str, dict]]:
    texture: set[str] = set()
    crystalline: dict[str, dict] = {}
    for finding in report.get("findings", []):
        name = Path(finding.get("image_path", "")).name
        category = finding.get("category", "")
        if not name:
            continue
        if category == TEXTURE_CATEGORY:
            texture.add(name)
        elif category == CRYSTALLINE_CATEGORY:
            crystalline[name] = finding.get("evidence", {})
    return texture, crystalline


def _assign_cluster(row: dict) -> str:
    grain = row["grain"]
    smooth = row["smoothness"]
    if smooth < 38:
        return "D"
    if grain >= 55:
        return "A"
    if grain >= 50 and smooth < 45:
        return "B"
    return "C"


def _percentile(values: Iterable[float], q: float) -> float:
    vals = list(values)
    if not vals:
        return 0.0
    return float(np.percentile(np.asarray(vals, dtype=np.float32), q))


def _cohen_d(group_a: list[float], group_b: list[float]) -> float | None:
    if len(group_a) < 2 or len(group_b) < 2:
        return None
    ma = statistics.mean(group_a)
    mb = statistics.mean(group_b)
    va = statistics.variance(group_a)
    vb = statistics.variance(group_b)
    na = len(group_a)
    nb = len(group_b)
    pooled = math.sqrt(((na - 1) * va + (nb - 1) * vb) / (na + nb - 2))
    if pooled <= 1e-9:
        return 0.0
    return (ma - mb) / pooled


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 2 or len(xs) != len(ys):
        return None
    mx = statistics.mean(xs)
    my = statistics.mean(ys)
    numerator = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx <= 1e-9 or dy <= 1e-9:
        return 0.0
    return numerator / (dx * dy)


def _fmt(value: float | None, digits: int = 3) -> str:
    if value is None:
        return "n/a"
    return f"{value:.{digits}f}"


def measure_patch_coherence(path: Path) -> dict | None:
    """Measure Candidate 1 patch-area statistics for one image."""
    try:
        img = Image.open(path).convert("RGB")
        img.thumbnail((ANALYSIS_MAX, ANALYSIS_MAX), Image.Resampling.LANCZOS)
        rgb = np.asarray(img, dtype=np.uint8)
    except Exception:
        return None

    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32)
    if min(gray.shape) < 8:
        return None

    blur = cv2.GaussianBlur(gray, (0, 0), 1.2)
    hf_map = np.abs(gray - blur)

    nonzero = hf_map[hf_map > 0.0]
    threshold = max(
        _percentile(nonzero, 90.0),
        float(np.mean(hf_map) + 1.5 * np.std(hf_map)),
        3.0,
    )
    elevated_mask = hf_map >= threshold
    mask_u8 = elevated_mask.astype(np.uint8)

    num_labels, _, stats, _ = cv2.connectedComponentsWithStats(mask_u8, connectivity=8)
    areas = [
        int(stats[i, cv2.CC_STAT_AREA])
        for i in range(1, num_labels)
        if int(stats[i, cv2.CC_STAT_AREA]) > 0
    ]
    patch_areas = [area for area in areas if area >= 12]

    pixels = int(gray.shape[0] * gray.shape[1])
    elevated_area = int(sum(areas))
    coherent_area = int(sum(patch_areas))
    largest_patch = max(patch_areas) if patch_areas else 0
    patch_area_p90 = _percentile(patch_areas, 90.0)
    patch_area_mean = statistics.mean(patch_areas) if patch_areas else 0.0
    patch_area_median = statistics.median(patch_areas) if patch_areas else 0.0
    patch_area_cv = (
        statistics.pstdev(patch_areas) / patch_area_mean
        if len(patch_areas) > 1 and patch_area_mean > 0
        else 0.0
    )
    elevated_area_ratio = elevated_area / pixels if pixels else 0.0
    coherent_area_ratio = coherent_area / pixels if pixels else 0.0
    coherent_fraction = coherent_area / elevated_area if elevated_area else 0.0

    patch_area_score = 100.0 * (1.0 - math.exp(-patch_area_p90 / 64.0))
    patch_coherence_score = patch_area_score * coherent_fraction

    return {
        "hf_mean": round(float(np.mean(hf_map)), 4),
        "hf_p90": round(_percentile(hf_map.ravel(), 90.0), 4),
        "hf_threshold": round(threshold, 4),
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
        "patch_coherence_score": round(float(patch_coherence_score), 4),
    }


def build_records(dataset_path: Path, report: dict, review: dict) -> list[dict]:
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

        candidate = measure_patch_coherence(image_path)
        if candidate is None:
            continue
        rows.append({**base, **candidate})

    return rows


def _group_stats(records: list[dict], group: str, metric: str) -> dict:
    vals = [float(r[metric]) for r in records if r["group"] == group]
    return {
        "n": len(vals),
        "mean": statistics.mean(vals) if vals else None,
        "median": statistics.median(vals) if vals else None,
        "min": min(vals) if vals else None,
        "max": max(vals) if vals else None,
    }


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
    metric = "patch_coherence_score"
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
        "Dataset Forge Crystalline Patch-Coherence Probe",
        "=" * 58,
        "Candidate: high-frequency map -> elevated-amplitude mask -> connected components -> patch-area statistics",
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
        "Patch-Area Statistics Summary",
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
        description="Research-only crystalline patch-coherence probe."
    )
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--report", type=Path, default=REPORT)
    parser.add_argument("--review", type=Path, default=REVIEW)
    parser.add_argument("--output-dir", type=Path, default=OUT_DIR)
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

    output_dir.mkdir(parents=True, exist_ok=True)
    report = _load_json(report_path)
    review = _load_json(review_path)
    records = build_records(dataset_path, report, review)

    data_path = output_dir / "probe_crystalline_patch_coherence_data.json"
    report_out = output_dir / "probe_crystalline_patch_coherence_report.txt"
    data_path.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    report_text = render_report(records)
    report_out.write_text(report_text, encoding="utf-8")

    print(report_text, end="")
    print(f"\nWrote: {data_path}")
    print(f"Wrote: {report_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
