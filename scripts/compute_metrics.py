"""
Compute calibration metrics from an inspection report and decision review.

Reads:
  inspection_report.json  — Dataset Forge analyzer output
  decision_review.json    — human AGREE/DISAGREE/UNSURE judgments

Outputs to terminal:
  1. Human agreement summary
  2. Finding review summary  (images flagged by analyzer)
  3. Clean review summary    (images not flagged)
  4. Missed-detection report (DISAGREE on CLEAN, sorted by strongest signal)
  5. False-positive report   (DISAGREE on FINDING)
  6. Threshold diagnostics   (z-score distribution of disagreements)

Optionally writes metrics_report.json with --output.

Does not change analyzer logic, thresholds, or any core contract.

Usage
-----
    python scripts/compute_metrics.py \\
        --report  "C:/path/to/inspect_output/inspection_report.json" \\
        --review  "C:/path/to/decision_review.json"

    python scripts/compute_metrics.py \\
        --report  inspection_report.json \\
        --review  decision_review.json \\
        --output  metrics_report.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_BAR  = "-" * 62
_BAR2 = "=" * 62


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_report(path: Path) -> dict:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Unexpected shape in {path}")
    return raw


def load_review(path: Path) -> dict:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Unexpected shape in {path}")
    if raw.get("schema") != "dataset-forge/decision-review/v1":
        raise ValueError(f"Unknown review schema in {path}: {raw.get('schema')}")
    return raw


def build_findings_index(report: dict) -> dict[str, dict]:
    """filename → finding entry for every flagged image."""
    index: dict[str, dict] = {}
    for f in report.get("findings", []):
        name = Path(f.get("image_path", "")).name
        if name:
            index[name] = f
    return index


def enrich_with_live_scores(
    entries: list[dict],
    dataset_path: Path,
    dist_mean: float,
    dist_stddev: float,
) -> None:
    """Re-run evaluate_texture on entries that have no metrics.

    Mutates entries in-place. Called only when --dataset is provided.
    Uses the existing evaluate_texture function — no analyzer logic changes.
    Z-score is computed with the same formula as TextureAnalyzer, using
    the dataset mean/stddev already stored in the report context.
    """
    try:
        from _calibration_metrics import measure_texture
    except ImportError as e:
        print(f"  Warning: could not import shared measurement helper: {e}", file=sys.stderr)
        return

    for entry in entries:
        if entry.get("micro") is not None:
            continue   # already has metrics from the report
        candidates = list(dataset_path.rglob(entry["filename"]))
        if not candidates:
            continue
        tex = measure_texture(candidates[0])
        if tex.status == "analyzed":
            micro = tex.microtexture_density_score
            entry["micro"]  = round(micro, 2)
            entry["smooth"] = round(tex.watercolor_smoothness_score, 2)
            entry["speck"]  = round(tex.highlight_speck_score, 2)
            if dist_stddev:
                entry["z"] = round((micro - dist_mean) / dist_stddev, 3)


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------

def compute_metrics(
    report: dict,
    review: dict,
    dataset_path: Path | None = None,
) -> dict:
    """Derive all calibration metrics from the two input dicts.

    Returns a plain dict that can be printed or serialised to JSON.
    Does not read files, write files, or touch any core contract.
    """
    findings_index = build_findings_index(report)
    reviews: dict[str, dict] = review.get("reviews", {})

    # Partition reviews into four buckets
    finding_agree:    list[dict] = []
    finding_disagree: list[dict] = []
    finding_unsure:   list[dict] = []
    clean_agree:      list[dict] = []
    clean_disagree:   list[dict] = []
    clean_unsure:     list[dict] = []

    for name, rv in reviews.items():
        verdict = rv.get("review", "")
        finding = findings_index.get(name)
        is_finding = finding is not None

        ev = finding.get("evidence", {}) if finding else {}
        # Prefer metrics from the report finding; fall back to review-stored values
        # (review stores metrics at label-time for images not in findings).
        entry = {
            "filename":    name,
            "review":      verdict,
            "df_decision": "FINDING" if is_finding else "CLEAN",
            "severity":    finding.get("severity") if finding else rv.get("severity"),
            "micro":       ev.get("microtexture_density") or rv.get("micro"),
            "z":           ev.get("z_score")              or rv.get("z"),
            "smooth":      ev.get("watercolor_smoothness") or rv.get("smooth"),
            "speck":       ev.get("highlight_speck")       or rv.get("speck"),
        }

        if is_finding:
            if verdict == "AGREE":     finding_agree.append(entry)
            elif verdict == "DISAGREE": finding_disagree.append(entry)
            else:                       finding_unsure.append(entry)
        else:
            if verdict == "AGREE":     clean_agree.append(entry)
            elif verdict == "DISAGREE": clean_disagree.append(entry)
            else:                       clean_unsure.append(entry)

    total        = len(reviews)
    total_agree  = len(finding_agree)  + len(clean_agree)
    total_dis    = len(finding_disagree) + len(clean_disagree)
    total_unsure = len(finding_unsure) + len(clean_unsure)

    # Enrich missed detections with live scores if dataset path provided
    tex_ctx = report.get("context", {}).get("texture_distributions", {})
    dist_mean   = tex_ctx.get("mean",   0.0)
    dist_stddev = tex_ctx.get("stddev", 0.0)

    if dataset_path is not None:
        enrich_with_live_scores(
            clean_disagree, dataset_path, dist_mean, dist_stddev
        )

    # Sort missed detections by strongest signal (z-score desc, then micro desc)
    def _sort_key(e: dict) -> tuple:
        return (-(e["z"] or 0.0), -(e["micro"] or 0.0))

    missed    = sorted(clean_disagree,   key=_sort_key)
    false_pos = sorted(finding_disagree, key=_sort_key)

    # Precision / recall (treating UNSURE as neither TP nor FP)
    flagged   = len(finding_agree) + len(finding_disagree) + len(finding_unsure)
    precision = len(finding_agree) / flagged if flagged else None

    # Missed detections as a share of clean images
    clean_total  = len(clean_agree) + len(clean_disagree) + len(clean_unsure)
    missed_rate  = len(clean_disagree) / clean_total if clean_total else None

    # z-score distribution of all disagreements
    disagreement_z = [
        e["z"] for e in (missed + false_pos) if e["z"] is not None
    ]
    z_stats: dict | None = None
    if disagreement_z:
        z_sorted = sorted(disagreement_z)
        n = len(z_sorted)
        z_stats = {
            "count": n,
            "min":   round(z_sorted[0], 3),
            "max":   round(z_sorted[-1], 3),
            "mean":  round(sum(z_sorted) / n, 3),
            "median": round(z_sorted[n // 2], 3),
        }

    return {
        "summary": {
            "total_reviewed":       total,
            "agree":                total_agree,
            "disagree":             total_dis,
            "unsure":               total_unsure,
            "agreement_pct":        round(total_agree / total * 100, 1) if total else 0.0,
        },
        "finding_review": {
            "findings_reviewed":    flagged,
            "finding_agree":        len(finding_agree),
            "finding_disagree":     len(finding_disagree),
            "finding_unsure":       len(finding_unsure),
            "precision":            round(precision * 100, 1) if precision is not None else None,
        },
        "clean_review": {
            "clean_reviewed":       clean_total,
            "clean_agree":          len(clean_agree),
            "clean_disagree":       len(clean_disagree),
            "clean_unsure":         len(clean_unsure),
            "missed_detection_pct": round(missed_rate * 100, 1) if missed_rate is not None else None,
        },
        "missed_detections": missed,
        "false_positives":   false_pos,
        "threshold_diagnostics": {
            "z_score_stats_of_disagreements": z_stats,
            "note": (
                "z-scores shown are from disagreed images only. "
                "Missed detections (CLEAN/DISAGREE) have no z-score from the report "
                "because the analyzer did not flag them — the z shown is None."
            ),
        },
    }


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def _fmt(v: float | None, decimals: int = 1) -> str:
    return f"{v:.{decimals}f}" if v is not None else "n/a"


def _fmt_pct(v: float | None) -> str:
    return f"{v:.1f}%" if v is not None else "n/a"


def print_metrics(metrics: dict) -> None:
    s   = metrics["summary"]
    fr  = metrics["finding_review"]
    cr  = metrics["clean_review"]
    md  = metrics["missed_detections"]
    fp  = metrics["false_positives"]
    td  = metrics["threshold_diagnostics"]

    print()
    print(_BAR2)
    print("  Dataset Forge — Calibration Metrics")
    print(_BAR2)

    # 1. Agreement summary
    print()
    print("  HUMAN AGREEMENT SUMMARY")
    print(_BAR)
    print(f"  Total reviewed   : {s['total_reviewed']}")
    print(f"  AGREE            : {s['agree']}")
    print(f"  DISAGREE         : {s['disagree']}")
    print(f"  UNSURE           : {s['unsure']}")
    print(f"  Agreement rate   : {_fmt_pct(s['agreement_pct'])}")

    # 2. Finding review
    print()
    print("  FINDING REVIEW  (images flagged by analyzer)")
    print(_BAR)
    print(f"  Findings reviewed: {fr['findings_reviewed']}")
    print(f"  AGREE            : {fr['finding_agree']}")
    print(f"  DISAGREE         : {fr['finding_disagree']}")
    print(f"  UNSURE           : {fr['finding_unsure']}")
    print(f"  Precision        : {_fmt_pct(fr['precision'])}")

    # 3. Clean review
    print()
    print("  CLEAN REVIEW  (images not flagged by analyzer)")
    print(_BAR)
    print(f"  Clean reviewed   : {cr['clean_reviewed']}")
    print(f"  AGREE            : {cr['clean_agree']}")
    print(f"  DISAGREE         : {cr['clean_disagree']}  <- missed detections")
    print(f"  UNSURE           : {cr['clean_unsure']}")
    print(f"  Missed det. rate : {_fmt_pct(cr['missed_detection_pct'])}")

    # 4. Missed detections
    print()
    print("  MISSED DETECTIONS  (DISAGREE on CLEAN — sorted by z-score)")
    print(_BAR)
    if md:
        print(f"  {'filename':<35} {'micro':>6}  {'z':>6}  {'smooth':>6}  {'speck':>5}")
        print(f"  {'-'*35} {'------':>6}  {'------':>6}  {'------':>6}  {'-----':>5}")
        for e in md:
            print(
                f"  {e['filename']:<35} "
                f"{_fmt(e['micro']):>6}  "
                f"{_fmt(e['z'], 2):>6}  "
                f"{_fmt(e['smooth']):>6}  "
                f"{_fmt(e['speck']):>5}"
            )
    else:
        print("  None — analyzer agreed with all clean decisions.")

    # 5. False positives
    print()
    print("  FALSE POSITIVES  (DISAGREE on FINDING)")
    print(_BAR)
    if fp:
        print(f"  {'filename':<35} {'sev':>8}  {'micro':>6}  {'z':>6}")
        print(f"  {'-'*35} {'--------':>8}  {'------':>6}  {'------':>6}")
        for e in fp:
            print(
                f"  {e['filename']:<35} "
                f"{(e['severity'] or 'none'):>8}  "
                f"{_fmt(e['micro']):>6}  "
                f"{_fmt(e['z'], 2):>6}"
            )
    else:
        print("  None — no flagged images were disagreed with.")

    # 6. Threshold diagnostics
    print()
    print("  THRESHOLD DIAGNOSTICS  (z-score distribution of disagreements)")
    print(_BAR)
    zs = td.get("z_score_stats_of_disagreements")
    if zs:
        print(f"  Disagreed images with z-score : {zs['count']}")
        print(f"  z min    : {zs['min']}")
        print(f"  z max    : {zs['max']}")
        print(f"  z mean   : {zs['mean']}")
        print(f"  z median : {zs['median']}")
    else:
        print("  No z-score data available for disagreed images.")
        print(f"  Note: {td['note']}")

    print()
    print(_BAR2)
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Compute calibration metrics from inspection report + decision review."
    )
    p.add_argument("--report", type=Path, required=True,
                   help="Path to inspection_report.json")
    p.add_argument("--review", type=Path, required=True,
                   help="Path to decision_review.json")
    p.add_argument("--output", type=Path, default=None,
                   help="Optional: write metrics_report.json to this path.")
    p.add_argument("--dataset", type=Path, default=None,
                   help="Optional: dataset folder. When provided, re-runs "
                        "shared measurement helper on missed detections to fill in "
                        "metrics not stored in the report.")
    return p.parse_args()


def main() -> None:
    args = _parse_args()

    report_path = args.report.expanduser().resolve()
    review_path = args.review.expanduser().resolve()

    if not report_path.exists():
        print(f"ERROR: report not found: {report_path}", file=sys.stderr)
        sys.exit(1)
    if not review_path.exists():
        print(f"ERROR: review not found: {review_path}", file=sys.stderr)
        sys.exit(1)

    report = load_report(report_path)
    review = load_review(review_path)

    dataset_path = args.dataset.expanduser().resolve() if args.dataset else None
    if dataset_path and not dataset_path.is_dir():
        print(f"ERROR: dataset not found: {dataset_path}", file=sys.stderr)
        sys.exit(1)

    metrics = compute_metrics(report, review, dataset_path=dataset_path)
    print_metrics(metrics)

    if args.output:
        out = args.output.expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(metrics, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"  Metrics written: {out}")
        print()


if __name__ == "__main__":
    main()
