"""
Internal TextureAnalyzer threshold calibration evidence.

This script reports evidence only. It does not change analyzer thresholds,
confidence caps, benchmark schemas, reports, or public CLI behavior.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from _calibration_metrics import measure_texture
from dataset_forge.analyzers.texture import (
    _ABSOLUTE_FLOOR,
    _UNCALIBRATED_FP_RATE,
    _UNCALIBRATED_MAX_CONFIDENCE,
    _Z_MEDIUM,
)

TEXTURE_CATEGORY = "texture.high_microtexture"
GROUND_TRUTH_SCHEMA = "dataset-forge/ground-truth/v1"
DECISION_REVIEW_SCHEMA = "dataset-forge/decision-review/v1"
VALID_LABELS = {"ARTIFACT", "CLEAN", "UNCERTAIN"}


def load_json(path: Path) -> dict:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Unexpected JSON shape in {path}")
    return raw


def texture_findings_by_name(report: dict) -> dict[str, dict]:
    """Return report findings for TextureAnalyzer's public texture category only."""
    findings: dict[str, dict] = {}
    for finding in report.get("findings", []):
        if finding.get("category") != TEXTURE_CATEGORY:
            continue
        name = Path(finding.get("image_path", "")).name
        if name:
            findings[name] = finding
    return findings


def labels_from_ground_truth(ground_truth: dict) -> dict[str, str]:
    if ground_truth.get("schema") != GROUND_TRUTH_SCHEMA:
        raise ValueError(f"Unknown ground-truth schema: {ground_truth.get('schema')}")
    labels: dict[str, str] = {}
    for name, entry in ground_truth.get("labels", {}).items():
        label = entry.get("label")
        if label in VALID_LABELS:
            labels[name] = label
    return labels


def labels_from_decision_review(review: dict, report: dict) -> dict[str, str]:
    """Build texture-specific labels from decision_review.json.

    This is a fallback when ground_truth.json is unavailable. Non-texture
    findings, such as crystalline-only findings, are excluded from texture
    calibration groups.
    """
    if review.get("schema") != DECISION_REVIEW_SCHEMA:
        raise ValueError(f"Unknown decision-review schema: {review.get('schema')}")

    texture_findings = texture_findings_by_name(report)
    labels: dict[str, str] = {}
    for name, entry in review.get("reviews", {}).items():
        verdict = entry.get("review")
        category = entry.get("category")
        df_decision = entry.get("df_decision")

        if verdict == "UNSURE":
            labels[name] = "UNCERTAIN"
            continue

        has_texture_finding = name in texture_findings
        if df_decision == "FINDING" and not has_texture_finding and category != TEXTURE_CATEGORY:
            # Non-texture findings are evidence for other analyzers, not for
            # TextureAnalyzer threshold calibration, so exclude them entirely.
            continue

        if has_texture_finding:
            if verdict == "AGREE":
                labels[name] = "ARTIFACT"
            elif verdict == "DISAGREE":
                labels[name] = "CLEAN"
        else:
            if verdict == "AGREE":
                labels[name] = "CLEAN"
            elif verdict == "DISAGREE":
                labels[name] = "ARTIFACT"
    return labels


def choose_label_source(
    dataset_path: Path,
    report: dict,
    ground_truth_path: Path | None,
    review_path: Path | None,
) -> tuple[str, dict[str, str]]:
    default_ground_truth = dataset_path / "ground_truth.json"
    if ground_truth_path is None and default_ground_truth.exists():
        ground_truth_path = default_ground_truth

    if ground_truth_path is not None and ground_truth_path.exists():
        return "ground_truth", labels_from_ground_truth(load_json(ground_truth_path))

    if review_path is not None and review_path.exists():
        return "decision_review_fallback", labels_from_decision_review(
            load_json(review_path),
            report,
        )

    raise ValueError("No ground_truth.json or decision_review.json label source found.")


def find_image(dataset_path: Path, filename: str) -> Path | None:
    candidates = list(dataset_path.rglob(filename))
    return candidates[0] if candidates else None


def build_samples(
    dataset_path: Path,
    labels: dict[str, str],
    report: dict,
) -> list[dict]:
    texture_dist = report.get("context", {}).get("texture_distributions", {})
    mean = float(texture_dist.get("mean") or 0.0)
    stddev = float(texture_dist.get("stddev") or 0.0)

    samples: list[dict] = []
    for filename, label in labels.items():
        image_path = find_image(dataset_path, filename)
        if image_path is None:
            continue
        tex = measure_texture(image_path)
        if tex.status != "analyzed":
            continue
        micro = tex.microtexture_density_score
        z_score = (micro - mean) / stddev if stddev else None
        samples.append({
            "filename": filename,
            "label": label,
            "micro": round(micro, 2),
            "z": round(z_score, 3) if z_score is not None else None,
        })
    return samples


def threshold_values(start: float = 0.5, stop: float = 3.0, step: float = 0.5) -> list[float]:
    values: list[float] = []
    current = start
    while current <= stop + 1e-9:
        values.append(round(current, 3))
        current += step
    return values


def evaluate_threshold(
    samples: Iterable[dict],
    z_threshold: float,
    *,
    absolute_floor: float = _ABSOLUTE_FLOOR,
) -> dict:
    counts = {"tp": 0, "fp": 0, "fn": 0, "tn": 0, "uncertain": 0, "skipped": 0}

    for sample in samples:
        label = sample.get("label")
        z_score = sample.get("z")
        micro = sample.get("micro")

        if label == "UNCERTAIN":
            counts["uncertain"] += 1
            continue
        if label not in {"ARTIFACT", "CLEAN"} or z_score is None or micro is None:
            counts["skipped"] += 1
            continue

        predicted = micro >= absolute_floor and z_score >= z_threshold
        if predicted and label == "ARTIFACT":
            counts["tp"] += 1
        elif predicted and label == "CLEAN":
            counts["fp"] += 1
        elif not predicted and label == "ARTIFACT":
            counts["fn"] += 1
        else:
            counts["tn"] += 1

    tp = counts["tp"]
    fp = counts["fp"]
    fn = counts["fn"]
    tn = counts["tn"]
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision is not None and recall is not None and precision + recall
        else None
    )
    fp_rate = fp / (fp + tn) if fp + tn else None

    return {
        "threshold": z_threshold,
        **counts,
        "precision": round(precision, 4) if precision is not None else None,
        "recall": round(recall, 4) if recall is not None else None,
        "f1": round(f1, 4) if f1 is not None else None,
        "fp_rate": round(fp_rate, 4) if fp_rate is not None else None,
    }


def sweep_thresholds(samples: list[dict], thresholds: Iterable[float]) -> list[dict]:
    return [evaluate_threshold(samples, threshold) for threshold in thresholds]


def current_threshold_summary(samples: list[dict]) -> dict:
    result = evaluate_threshold(samples, _Z_MEDIUM)
    measured_fp_rate = result["fp_rate"]
    precision = result["precision"]

    if measured_fp_rate is None:
        fp_assessment = "unknown"
    elif _UNCALIBRATED_FP_RATE >= measured_fp_rate:
        fp_assessment = "conservative"
    else:
        fp_assessment = "optimistic"

    if precision is None:
        confidence_assessment = "unknown"
    elif _UNCALIBRATED_MAX_CONFIDENCE <= precision:
        confidence_assessment = "conservative"
    else:
        confidence_assessment = "optimistic"

    return {
        **result,
        "configured_fp_rate": _UNCALIBRATED_FP_RATE,
        "confidence_cap": _UNCALIBRATED_MAX_CONFIDENCE,
        "fp_rate_assessment": fp_assessment,
        "confidence_cap_assessment": confidence_assessment,
    }


def _fmt(value: float | int | None, decimals: int = 3) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, int):
        return str(value)
    return f"{value:.{decimals}f}"


def render_report(
    label_source: str,
    samples: list[dict],
    sweep: list[dict],
    current: dict,
) -> str:
    lines = [
        "Dataset Forge Texture Threshold Calibration",
        "=" * 52,
        f"Label source: {label_source}",
    ]
    if label_source == "decision_review_fallback":
        lines.append(
            "Caveat: decision_review fallback is category-filtered but less reliable than ground_truth.json."
        )
    lines.extend([
        f"Samples measured: {len(samples)}",
        "",
        "Threshold sweep",
        "-" * 52,
        "z     TP  FP  FN  TN  precision  recall  f1    fp_rate",
    ])
    for row in sweep:
        lines.append(
            f"{row['threshold']:<4.1f}  {row['tp']:>2}  {row['fp']:>2}  "
            f"{row['fn']:>2}  {row['tn']:>2}  {_fmt(row['precision']):>9}  "
            f"{_fmt(row['recall']):>6}  {_fmt(row['f1']):>5}  {_fmt(row['fp_rate']):>7}"
        )
    lines.extend([
        "",
        "Current TextureAnalyzer threshold",
        "-" * 52,
        f"z threshold: {_Z_MEDIUM:.1f}",
        f"TP/FP/FN/TN: {current['tp']}/{current['fp']}/{current['fn']}/{current['tn']}",
        f"Measured FP rate: {_fmt(current['fp_rate'])}",
        f"Configured FP rate: {_fmt(current['configured_fp_rate'])} ({current['fp_rate_assessment']})",
        f"Confidence cap: {_fmt(current['confidence_cap'])} ({current['confidence_cap_assessment']})",
        "",
        "Evidence only. No threshold or analyzer changes were made.",
    ])
    return "\n".join(lines) + "\n"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Internal texture threshold calibration evidence report."
    )
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--ground-truth", type=Path, default=None)
    parser.add_argument("--review", type=Path, default=None)
    parser.add_argument("--threshold-min", type=float, default=0.5)
    parser.add_argument("--threshold-max", type=float, default=3.0)
    parser.add_argument("--threshold-step", type=float, default=0.5)
    parser.add_argument("--json-output", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    dataset_path = args.dataset.expanduser().resolve()
    report_path = args.report.expanduser().resolve()
    ground_truth_path = args.ground_truth.expanduser().resolve() if args.ground_truth else None
    review_path = args.review.expanduser().resolve() if args.review else None

    if not dataset_path.is_dir():
        print(f"ERROR: dataset not found: {dataset_path}", file=sys.stderr)
        sys.exit(1)
    if not report_path.exists():
        print(f"ERROR: report not found: {report_path}", file=sys.stderr)
        sys.exit(1)

    report = load_json(report_path)
    label_source, labels = choose_label_source(
        dataset_path,
        report,
        ground_truth_path,
        review_path,
    )
    samples = build_samples(dataset_path, labels, report)
    thresholds = threshold_values(
        args.threshold_min,
        args.threshold_max,
        args.threshold_step,
    )
    sweep = sweep_thresholds(samples, thresholds)
    current = current_threshold_summary(samples)

    print(render_report(label_source, samples, sweep, current), end="")

    if args.json_output:
        out = args.json_output.expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps({
                "label_source": label_source,
                "samples": samples,
                "sweep": sweep,
                "current_threshold": current,
            }, indent=2) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
