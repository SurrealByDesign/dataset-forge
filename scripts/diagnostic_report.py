"""
Diagnostic investigation: which metric best separates missed detections
from the genuinely clean population?

Reads decision_review.json and inspection_report.json, groups images into:
  A — Agreed FINDING  (analyzer flagged, human AGREE)
  B — Missed CLEAN    (analyzer clean, human DISAGREE) ← target group
  C — Agreed CLEAN    (analyzer clean, human AGREE)

Re-runs evaluate_texture on every image to get the full 7-metric profile,
then computes per-group distributions and Cohen's d between B and C for each
metric to identify the strongest discriminating signal.

This script is read-only. It does not change any analyzer, threshold, finding,
or core contract.

Usage
-----
    python scripts/diagnostic_report.py \\
        --dataset  "C:/path/to/ANTHROPOMORPHS" \\
        --report   "C:/path/to/inspect_output/inspection_report.json" \\
        --review   "C:/path/to/decision_review.json"

    Add --output to write the raw data to diagnostic_data.json.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from dataset_forge.analysis.texture import evaluate_texture

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

METRICS = [
    ("microtexture_density_score",  "Microtexture density"),
    ("local_contrast_score",        "Local contrast"),
    ("edge_sharpness_score",        "Edge sharpness"),
    ("highlight_speck_score",       "Highlight speck"),
    ("texture_consistency_score",   "Texture consistency"),
    ("watercolor_smoothness_score", "Watercolor smoothness"),
    ("pencil_grain_score",          "Pencil grain"),
]

_BAR  = "-" * 68
_BAR2 = "=" * 68


# ---------------------------------------------------------------------------
# Grouping
# ---------------------------------------------------------------------------

def _build_findings_index(report: dict) -> dict[str, dict]:
    index: dict[str, dict] = {}
    for f in report.get("findings", []):
        name = Path(f.get("image_path", "")).name
        if name:
            index[name] = f
    return index


def group_images(
    dataset_path: Path,
    findings_index: dict[str, dict],
    reviews: dict[str, dict],
) -> tuple[list[Path], list[Path], list[Path]]:
    """Return (agreed_finding, missed_clean, agreed_clean) path lists."""
    agreed_finding: list[Path] = []
    missed_clean:   list[Path] = []
    agreed_clean:   list[Path] = []

    for name, rv in reviews.items():
        verdict  = rv.get("review", "")
        is_finding = name in findings_index

        candidates = list(dataset_path.rglob(name))
        if not candidates:
            continue
        path = candidates[0]

        if is_finding and verdict == "AGREE":
            agreed_finding.append(path)
        elif not is_finding and verdict == "DISAGREE":
            missed_clean.append(path)
        elif not is_finding and verdict == "AGREE":
            agreed_clean.append(path)
        # UNSURE excluded from all groups — ambiguous signal

    return agreed_finding, missed_clean, agreed_clean


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def _stats(values: list[float]) -> dict:
    if not values:
        return {"n": 0, "mean": None, "median": None, "stddev": None,
                "min": None, "max": None, "p25": None, "p75": None}
    n = len(values)
    s = sorted(values)
    mean = sum(s) / n
    variance = sum((v - mean) ** 2 for v in s) / n
    stddev = math.sqrt(variance)
    median = s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2
    p25 = s[max(0, int(n * 0.25))]
    p75 = s[min(n - 1, int(n * 0.75))]
    return {
        "n": n,
        "mean":   round(mean, 2),
        "median": round(median, 2),
        "stddev": round(stddev, 2),
        "min":    round(s[0], 2),
        "max":    round(s[-1], 2),
        "p25":    round(p25, 2),
        "p75":    round(p75, 2),
    }


def cohens_d(group_b: list[float], group_c: list[float]) -> float | None:
    """Effect size: how much does group B differ from group C?

    Positive = metric is higher in missed-CLEAN than agreed-CLEAN.
    |d| ≥ 0.8 is conventionally large, ≥ 0.5 medium, ≥ 0.2 small.
    """
    if len(group_b) < 2 or len(group_c) < 2:
        return None
    mean_b = sum(group_b) / len(group_b)
    mean_c = sum(group_c) / len(group_c)
    var_b = sum((v - mean_b) ** 2 for v in group_b) / len(group_b)
    var_c = sum((v - mean_c) ** 2 for v in group_c) / len(group_c)
    pooled = math.sqrt((var_b + var_c) / 2)
    if pooled < 1e-9:
        return None
    return round((mean_b - mean_c) / pooled, 3)


# ---------------------------------------------------------------------------
# Score collection
# ---------------------------------------------------------------------------

def collect_scores(paths: list[Path]) -> list[dict]:
    """Run evaluate_texture on every path and return a list of score dicts."""
    results = []
    for path in paths:
        tex = evaluate_texture(path)
        if tex.status != "analyzed":
            continue
        results.append({
            "filename": path.name,
            **{key: getattr(tex, key) for key, _ in METRICS},
        })
    return results


# ---------------------------------------------------------------------------
# Report printing
# ---------------------------------------------------------------------------

def _fmt(v: float | None, w: int = 6) -> str:
    return f"{v:{w}.1f}" if v is not None else f"{'n/a':>{w}}"


def _fmt_d(d: float | None) -> str:
    if d is None:
        return "   n/a"
    sign = "+" if d >= 0 else ""
    return f"{sign}{d:+.2f}"


def print_report(
    agreed_finding_scores: list[dict],
    missed_scores:         list[dict],
    agreed_clean_scores:   list[dict],
) -> None:
    groups = [
        ("A  Agreed FINDING", agreed_finding_scores),
        ("B  Missed CLEAN   ", missed_scores),
        ("C  Agreed CLEAN   ", agreed_clean_scores),
    ]

    print()
    print(_BAR2)
    print("  Dataset Forge — Diagnostic Report")
    print("  Metric distributions by review group")
    print(_BAR2)
    print()
    print(f"  Group A  Agreed FINDING : {len(agreed_finding_scores):3d} images")
    print(f"  Group B  Missed CLEAN   : {len(missed_scores):3d} images  (target — false negatives)")
    print(f"  Group C  Agreed CLEAN   : {len(agreed_clean_scores):3d} images")
    print(f"  UNSURE excluded from all groups.")

    # --- Per-metric distribution table ---
    for key, label in METRICS:
        a_vals = [r[key] for r in agreed_finding_scores]
        b_vals = [r[key] for r in missed_scores]
        c_vals = [r[key] for r in agreed_clean_scores]
        a = _stats(a_vals)
        b = _stats(b_vals)
        c = _stats(c_vals)
        d = cohens_d(b_vals, c_vals)

        print()
        print(f"  {label.upper()}")
        print(_BAR)
        print(f"  {'Group':<22} {'n':>3}  {'mean':>6}  {'median':>6}  "
              f"{'stddev':>6}  {'min':>6}  {'max':>6}")
        print(f"  {'-'*22} {'---':>3}  {'------':>6}  {'------':>6}  "
              f"{'------':>6}  {'------':>6}  {'------':>6}")
        for name, st in [("A Agreed FINDING", a), ("B Missed CLEAN", b), ("C Agreed CLEAN", c)]:
            print(f"  {name:<22} {st['n']:>3}  "
                  f"{_fmt(st['mean'])}  {_fmt(st['median'])}  "
                  f"{_fmt(st['stddev'])}  {_fmt(st['min'])}  {_fmt(st['max'])}")
        strength = "LARGE" if d and abs(d) >= 0.8 else \
                   "medium" if d and abs(d) >= 0.5 else \
                   "small" if d and abs(d) >= 0.2 else "negligible"
        direction = "(B > C — missed have MORE)" if d and d > 0 else \
                    "(B < C — missed have LESS)" if d and d < 0 else ""
        print(f"  Cohen's d (B vs C): {_fmt_d(d)}  [{strength}]  {direction}")

    # --- Summary ranking ---
    print()
    print(_BAR2)
    print("  DISCRIMINATING POWER RANKING  (B=missed vs C=clean, |d| desc)")
    print(_BAR)
    print(f"  {'Metric':<30} {'Cohen d':>8}  {'Magnitude':>10}  Direction")
    print(f"  {'-'*30} {'-------':>8}  {'----------':>10}  ---------")

    ranked = []
    for key, label in METRICS:
        b_vals = [r[key] for r in missed_scores]
        c_vals = [r[key] for r in agreed_clean_scores]
        d = cohens_d(b_vals, c_vals)
        ranked.append((label, d))

    ranked.sort(key=lambda x: abs(x[1] or 0), reverse=True)
    for label, d in ranked:
        if d is None:
            continue
        mag = "LARGE" if abs(d) >= 0.8 else "medium" if abs(d) >= 0.5 else "small"
        direction = "B > C" if d > 0 else "B < C"
        print(f"  {label:<30} {_fmt_d(d):>8}  {mag:>10}  {direction}")

    # --- Per-image table for missed detections ---
    print()
    print(_BAR2)
    print("  PER-IMAGE DETAIL — GROUP B (MISSED CLEAN)")
    print(_BAR)
    cols = ["micro", "contrast", "sharpness", "speck", "consist", "smooth", "grain"]
    print(f"  {'filename':<40} {'micro':>6} {'contr':>6} {'sharp':>6} "
          f"{'speck':>6} {'cons':>6} {'smth':>6} {'grain':>6}")
    print(f"  {'-'*40} {'------':>6} {'------':>6} {'------':>6} "
          f"{'------':>6} {'------':>6} {'------':>6} {'------':>6}")
    for r in sorted(missed_scores, key=lambda x: -x["microtexture_density_score"]):
        print(
            f"  {r['filename']:<40} "
            f"{_fmt(r['microtexture_density_score'])} "
            f"{_fmt(r['local_contrast_score'])} "
            f"{_fmt(r['edge_sharpness_score'])} "
            f"{_fmt(r['highlight_speck_score'])} "
            f"{_fmt(r['texture_consistency_score'])} "
            f"{_fmt(r['watercolor_smoothness_score'])} "
            f"{_fmt(r['pencil_grain_score'])}"
        )

    print()
    print(_BAR2)
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Diagnostic: which metric best identifies missed detections?"
    )
    p.add_argument("--dataset", type=Path, required=True,
                   help="Path to the image dataset folder.")
    p.add_argument("--report",  type=Path, required=True,
                   help="Path to inspection_report.json.")
    p.add_argument("--review",  type=Path, required=True,
                   help="Path to decision_review.json.")
    p.add_argument("--output",  type=Path, default=None,
                   help="Optional: write raw scores to diagnostic_data.json.")
    return p.parse_args()


def main() -> None:
    args = _parse_args()

    dataset_path = args.dataset.expanduser().resolve()
    report_path  = args.report.expanduser().resolve()
    review_path  = args.review.expanduser().resolve()

    for label, path in [("Dataset", dataset_path), ("Report", report_path),
                        ("Review", review_path)]:
        if label == "Dataset" and not path.is_dir():
            print(f"ERROR: {label} not found: {path}", file=sys.stderr); sys.exit(1)
        elif label != "Dataset" and not path.exists():
            print(f"ERROR: {label} not found: {path}", file=sys.stderr); sys.exit(1)

    report = json.loads(report_path.read_text(encoding="utf-8"))
    review = json.loads(review_path.read_text(encoding="utf-8"))
    findings_index = _build_findings_index(report)
    reviews = review.get("reviews", {})

    print(f"\n  Grouping images from decision_review.json ...", flush=True)
    agreed_finding, missed_clean, agreed_clean = group_images(
        dataset_path, findings_index, reviews
    )

    print(f"  Running evaluate_texture on {len(agreed_finding)} agreed-finding images ...", flush=True)
    af_scores = collect_scores(agreed_finding)
    print(f"  Running evaluate_texture on {len(missed_clean)} missed-clean images ...", flush=True)
    mc_scores = collect_scores(missed_clean)
    print(f"  Running evaluate_texture on {len(agreed_clean)} agreed-clean images ...", flush=True)
    ac_scores = collect_scores(agreed_clean)

    print_report(af_scores, mc_scores, ac_scores)

    if args.output:
        out = args.output.expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "agreed_finding": af_scores,
            "missed_clean":   mc_scores,
            "agreed_clean":   ac_scores,
        }
        out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                       encoding="utf-8")
        print(f"  Raw data written: {out}\n")


if __name__ == "__main__":
    main()
