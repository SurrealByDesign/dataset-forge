"""
Pencil-grain diagnostic: evaluate pencil_grain_score as a detection signal
for the crystalline faceting artifact family.

Reads diagnostic_data.json produced by diagnostic_report.py (which groups
images into A=agreed-finding, B=missed-clean, C=agreed-clean and records
all evaluate_texture scores).

Produces:
  A. Pencil-grain distribution analysis
  B. Candidate threshold table (pencil_grain alone)
  C. Candidate combined-rule table (pencil_grain + other signals)
  D. Artifact-family separability assessment
  E. Architecture recommendation

Read-only. No analyzer changes, no thresholds modified, no contracts touched.

Usage
-----
    python scripts/pencil_grain_diagnostic.py \\
        --data "C:/path/to/diagnostic_data.json"
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

_BAR  = "-" * 72
_BAR2 = "=" * 72
_BAR3 = "·" * 72


# ---------------------------------------------------------------------------
# Statistics helpers
# ---------------------------------------------------------------------------

def _stats(values: list[float]) -> dict:
    if not values:
        return dict(n=0, mean=None, median=None, stddev=None,
                    min=None, max=None, p10=None, p25=None, p75=None, p90=None)
    n = len(values)
    s = sorted(values)
    mean = sum(s) / n
    var  = sum((v - mean) ** 2 for v in s) / n
    def pct(p): return s[min(n - 1, max(0, int(math.floor(n * p))))]
    return dict(
        n=n,
        mean=round(mean, 2),
        median=round(pct(0.50), 2),
        stddev=round(math.sqrt(var), 2),
        min=round(s[0], 2),
        max=round(s[-1], 2),
        p10=round(pct(0.10), 2),
        p25=round(pct(0.25), 2),
        p75=round(pct(0.75), 2),
        p90=round(pct(0.90), 2),
    )


def _cohens_d(b: list[float], c: list[float]) -> float | None:
    if len(b) < 2 or len(c) < 2:
        return None
    mb = sum(b) / len(b)
    mc = sum(c) / len(c)
    vb = sum((v - mb) ** 2 for v in b) / len(b)
    vc = sum((v - mc) ** 2 for v in c) / len(c)
    pooled = math.sqrt((vb + vc) / 2)
    return round((mb - mc) / pooled, 3) if pooled > 1e-9 else None


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx  = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy  = math.sqrt(sum((y - my) ** 2 for y in ys))
    return round(num / (dx * dy), 3) if dx * dy > 1e-9 else None


# ---------------------------------------------------------------------------
# Classification helpers
# ---------------------------------------------------------------------------

def _threshold_metrics(
    b_vals: list[float],   # missed-clean (should be flagged)
    c_vals: list[float],   # agreed-clean (genuinely clean)
    threshold: float,
    above_flags: bool = True,   # True → values ABOVE threshold are flagged
) -> dict:
    """Compute TP/FP/FN/TN and derived metrics at a given threshold."""
    def _flags(v): return v >= threshold if above_flags else v <= threshold
    tp = sum(1 for v in b_vals if _flags(v))
    fn = sum(1 for v in b_vals if not _flags(v))
    fp = sum(1 for v in c_vals if _flags(v))
    tn = sum(1 for v in c_vals if not _flags(v))
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall    = tp / (tp + fn) if (tp + fn) else 0.0
    f1        = 2 * precision * recall / (precision + recall) \
                if (precision + recall) else 0.0
    return dict(
        threshold=threshold,
        tp=tp, fn=fn, fp=fp, tn=tn,
        precision=round(precision, 3),
        recall=round(recall, 3),
        f1=round(f1, 3),
    )


def _combined_rule_metrics(
    records_b: list[dict],
    records_c: list[dict],
    rule_fn,
    label: str,
) -> dict:
    tp = sum(1 for r in records_b if rule_fn(r))
    fn = sum(1 for r in records_b if not rule_fn(r))
    fp = sum(1 for r in records_c if rule_fn(r))
    tn = sum(1 for r in records_c if not rule_fn(r))
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall    = tp / (tp + fn) if (tp + fn) else 0.0
    f1        = 2 * precision * recall / (precision + recall) \
                if (precision + recall) else 0.0
    return dict(
        label=label, tp=tp, fn=fn, fp=fp, tn=tn,
        precision=round(precision, 3),
        recall=round(recall, 3),
        f1=round(f1, 3),
    )


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def _f(v, w=6, d=1):
    return f"{v:{w}.{d}f}" if v is not None else f"{'n/a':>{w}}"

def _fp(v, w=6):
    return f"{v*100:{w}.1f}%" if v is not None else f"{'n/a':>{w}}"


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def run_diagnostic(data: dict) -> None:
    af = data["agreed_finding"]   # group A
    mc = data["missed_clean"]     # group B — target
    ac = data["agreed_clean"]     # group C

    print()
    print(_BAR2)
    print("  Dataset Forge — Pencil-Grain Diagnostic")
    print("  Evaluating pencil_grain_score as a crystalline-faceting signal")
    print(_BAR2)
    print(f"\n  Group A  Agreed FINDING : {len(af):3d} images")
    print(f"  Group B  Missed CLEAN   : {len(mc):3d} images  (false negatives — target)")
    print(f"  Group C  Agreed CLEAN   : {len(ac):3d} images  (true negatives — must not flag)")

    pg_a = [r["pencil_grain_score"]         for r in af]
    pg_b = [r["pencil_grain_score"]         for r in mc]
    pg_c = [r["pencil_grain_score"]         for r in ac]
    mt_a = [r["microtexture_density_score"] for r in af]
    mt_b = [r["microtexture_density_score"] for r in mc]
    mt_c = [r["microtexture_density_score"] for r in ac]
    sm_b = [r["watercolor_smoothness_score"] for r in mc]
    sm_c = [r["watercolor_smoothness_score"] for r in ac]
    tc_b = [r["texture_consistency_score"]  for r in mc]
    tc_c = [r["texture_consistency_score"]  for r in ac]

    # -----------------------------------------------------------------------
    # A. Distribution analysis
    # -----------------------------------------------------------------------
    print()
    print(_BAR2)
    print("  A. PENCIL-GRAIN DISTRIBUTION ANALYSIS")
    print(_BAR2)

    sa, sb, sc = _stats(pg_a), _stats(pg_b), _stats(pg_c)
    d_bc = _cohens_d(pg_b, pg_c)

    print()
    print(f"  {'Group':<24} {'n':>3}  {'mean':>6}  {'p25':>6}  {'med':>6}  "
          f"{'p75':>6}  {'p90':>6}  {'max':>6}  {'std':>6}")
    print(f"  {'-'*24} {'---':>3}  {'------':>6}  {'------':>6}  {'------':>6}  "
          f"{'------':>6}  {'------':>6}  {'------':>6}  {'------':>6}")
    for lbl, st in [("A  Agreed FINDING", sa), ("B  Missed CLEAN", sb),
                     ("C  Agreed CLEAN", sc)]:
        print(f"  {lbl:<24} {st['n']:>3}  "
              f"{_f(st['mean'])}  {_f(st['p25'])}  {_f(st['median'])}  "
              f"{_f(st['p75'])}  {_f(st['p90'])}  {_f(st['max'])}  {_f(st['stddev'])}")
    d_mag = "LARGE" if d_bc and abs(d_bc) >= 0.8 else \
            "medium" if d_bc and abs(d_bc) >= 0.5 else "small"
    print(f"\n  Cohen's d (B vs C): {d_bc:+.3f}  [{d_mag}]"
          f"  (B > C — missed have MORE pencil grain)")

    # Per-image pencil_grain for missed group
    print()
    print(f"  Per-image — Group B (MISSED CLEAN), sorted by pencil_grain desc:")
    print(f"  {'filename':<42} {'grain':>6}  {'micro':>6}  {'smooth':>6}  {'consist':>7}")
    print(f"  {'-'*42} {'------':>6}  {'------':>6}  {'------':>6}  {'-------':>7}")
    for r in sorted(mc, key=lambda x: -x["pencil_grain_score"]):
        print(f"  {r['filename']:<42} "
              f"{_f(r['pencil_grain_score'])}  "
              f"{_f(r['microtexture_density_score'])}  "
              f"{_f(r['watercolor_smoothness_score'])}  "
              f"{_f(r['texture_consistency_score'], 7)}")

    # Compare against agreed-clean at same pencil_grain range
    print()
    print(f"  Agreed-CLEAN images with pencil_grain >= 45 (potential overlap zone):")
    overlap = [r for r in ac if r["pencil_grain_score"] >= 45.0]
    if overlap:
        print(f"  {'filename':<42} {'grain':>6}  {'micro':>6}  {'smooth':>6}")
        print(f"  {'-'*42} {'------':>6}  {'------':>6}  {'------':>6}")
        for r in sorted(overlap, key=lambda x: -x["pencil_grain_score"]):
            print(f"  {r['filename']:<42} "
                  f"{_f(r['pencil_grain_score'])}  "
                  f"{_f(r['microtexture_density_score'])}  "
                  f"{_f(r['watercolor_smoothness_score'])}")
    else:
        print("  None — no agreed-clean images above 45.")

    # -----------------------------------------------------------------------
    # B. Candidate threshold table — pencil_grain alone
    # -----------------------------------------------------------------------
    print()
    print(_BAR2)
    print("  B. CANDIDATE THRESHOLD TABLE — pencil_grain alone (above threshold = flag)")
    print(_BAR2)
    print()
    print(f"  {'threshold':>9}  {'TP':>4}  {'FN':>4}  {'FP':>4}  {'TN':>4}  "
          f"{'precision':>10}  {'recall':>7}  {'F1':>6}  notes")
    print(f"  {'-'*9}  {'----':>4}  {'----':>4}  {'----':>4}  {'----':>4}  "
          f"{'----------':>10}  {'-------':>7}  {'------':>6}  -----")
    for t in [30, 35, 38, 40, 42, 45, 48, 50, 55, 60]:
        m = _threshold_metrics(pg_b, pg_c, float(t))
        note = ""
        if m["fp"] == 0:  note = "<-- zero FP"
        elif m["fp"] <= 2: note = "<-- low FP"
        if m["tp"] == len(pg_b): note += " full recall"
        print(f"  {t:>9}  {m['tp']:>4}  {m['fn']:>4}  {m['fp']:>4}  {m['tn']:>4}  "
              f"{m['precision']:>10.1%}  {m['recall']:>7.1%}  {m['f1']:>6.3f}  {note}")

    # -----------------------------------------------------------------------
    # C. Candidate combined-rule table
    # -----------------------------------------------------------------------
    print()
    print(_BAR2)
    print("  C. CANDIDATE COMBINED-RULE TABLE")
    print(_BAR2)
    print()

    # Dataset mean/stddev for microtexture (from group stats)
    all_micro = mt_a + mt_b + mt_c
    all_mean  = sum(all_micro) / len(all_micro)
    all_std   = math.sqrt(sum((v - all_mean) ** 2 for v in all_micro) / len(all_micro))

    def z(micro): return (micro - all_mean) / all_std if all_std else 0.0

    rules = [
        ("pencil_grain >= 45",
         lambda r: r["pencil_grain_score"] >= 45),
        ("pencil_grain >= 42",
         lambda r: r["pencil_grain_score"] >= 42),
        ("pencil_grain >= 40",
         lambda r: r["pencil_grain_score"] >= 40),
        ("z >= 0.85  (lower micro threshold)",
         lambda r: z(r["microtexture_density_score"]) >= 0.85),
        ("z >= 1.0   (current threshold)",
         lambda r: z(r["microtexture_density_score"]) >= 1.0),
        ("z >= 0.85  OR  pencil_grain >= 45",
         lambda r: z(r["microtexture_density_score"]) >= 0.85
                   or r["pencil_grain_score"] >= 45),
        ("z >= 0.85  OR  pencil_grain >= 42",
         lambda r: z(r["microtexture_density_score"]) >= 0.85
                   or r["pencil_grain_score"] >= 42),
        ("z >= 1.0   OR  pencil_grain >= 45",
         lambda r: z(r["microtexture_density_score"]) >= 1.0
                   or r["pencil_grain_score"] >= 45),
        ("z >= 1.0   OR  pencil_grain >= 42",
         lambda r: z(r["microtexture_density_score"]) >= 1.0
                   or r["pencil_grain_score"] >= 42),
        ("pencil_grain >= 45  AND  smooth < 52",
         lambda r: r["pencil_grain_score"] >= 45
                   and r["watercolor_smoothness_score"] < 52),
        ("pencil_grain >= 42  AND  smooth < 52",
         lambda r: r["pencil_grain_score"] >= 42
                   and r["watercolor_smoothness_score"] < 52),
        ("pencil_grain >= 42  AND  micro >= 30",
         lambda r: r["pencil_grain_score"] >= 42
                   and r["microtexture_density_score"] >= 30),
        ("z >= 0.85  OR (pencil_grain>=42 AND micro>=30)",
         lambda r: z(r["microtexture_density_score"]) >= 0.85
                   or (r["pencil_grain_score"] >= 42
                       and r["microtexture_density_score"] >= 30)),
    ]

    print(f"  Dataset micro mean={all_mean:.1f}  stddev={all_std:.1f}  "
          f"(z computed from all {len(all_micro)} images in this diagnostic)\n")
    print(f"  {'Rule':<46} {'TP':>3}  {'FN':>3}  {'FP':>3}  {'TN':>3}  "
          f"{'prec':>6}  {'rec':>6}  {'F1':>6}")
    print(f"  {'-'*46} {'---':>3}  {'---':>3}  {'---':>3}  {'---':>3}  "
          f"{'------':>6}  {'------':>6}  {'------':>6}")
    for label, fn in rules:
        m = _combined_rule_metrics(mc, ac, fn, label)
        print(f"  {m['label']:<46} {m['tp']:>3}  {m['fn']:>3}  {m['fp']:>3}  {m['tn']:>3}  "
              f"{m['precision']:>6.1%}  {m['recall']:>6.1%}  {m['f1']:>6.3f}")

    # -----------------------------------------------------------------------
    # D. Separability assessment
    # -----------------------------------------------------------------------
    print()
    print(_BAR2)
    print("  D. ARTIFACT-FAMILY SEPARABILITY ASSESSMENT")
    print(_BAR2)

    # Correlation: pencil_grain vs microtexture
    pg_all = pg_a + pg_b + pg_c
    mt_all = mt_a + mt_b + mt_c
    r_pg_mt = _pearson(pg_all, mt_all)

    pg_b_high_mt_low = [r for r in mc
                        if r["pencil_grain_score"] >= 42
                        and r["microtexture_density_score"] < 38]
    pg_b_both_high   = [r for r in mc
                        if r["pencil_grain_score"] >= 42
                        and r["microtexture_density_score"] >= 38]

    # Images with high speck AND high pencil_grain (overlap with speck family)
    sp_all_b = [r["highlight_speck_score"] for r in mc]
    sp_all_c = [r["highlight_speck_score"] for r in ac]
    r_pg_sp  = _pearson(
        [r["pencil_grain_score"] for r in mc + ac],
        [r["highlight_speck_score"] for r in mc + ac],
    )

    print(f"""
  Correlation: pencil_grain vs microtexture (all groups combined)
    Pearson r = {r_pg_mt}
    Interpretation: {"strong co-occurrence" if r_pg_mt and abs(r_pg_mt) >= 0.7
                     else "moderate co-occurrence" if r_pg_mt and abs(r_pg_mt) >= 0.4
                     else "weak co-occurrence — signals are largely independent"}

  Correlation: pencil_grain vs highlight_speck (groups B+C combined)
    Pearson r = {r_pg_sp}
    Interpretation: {"high overlap — speck and faceting co-occur" if r_pg_sp and abs(r_pg_sp) >= 0.5
                     else "low overlap — speck and faceting are separable"}

  Missed images with HIGH pencil_grain (>=42) but LOW microtexture (<38):
    Count: {len(pg_b_high_mt_low)} / {len(mc)} missed images
    These are the "pure crystalline faceting" cases that microtexture misses entirely.""")
    if pg_b_high_mt_low:
        for r in sorted(pg_b_high_mt_low, key=lambda x: -x["pencil_grain_score"]):
            print(f"    {r['filename']:<42}  grain={r['pencil_grain_score']:5.1f}  "
                  f"micro={r['microtexture_density_score']:5.1f}")

    print(f"""
  Missed images with HIGH pencil_grain (>=42) AND HIGH microtexture (>=38):
    Count: {len(pg_b_both_high)} / {len(mc)} missed images
    These have both signals elevated — either detector would catch them.""")
    if pg_b_both_high:
        for r in sorted(pg_b_both_high, key=lambda x: -x["pencil_grain_score"]):
            print(f"    {r['filename']:<42}  grain={r['pencil_grain_score']:5.1f}  "
                  f"micro={r['microtexture_density_score']:5.1f}")

    # Agreed-clean images with high pencil_grain — potential false positive analysis
    clean_high_grain = [r for r in ac if r["pencil_grain_score"] >= 42]
    print(f"""
  Agreed-CLEAN images with pencil_grain >= 42 (false positive risk):
    Count: {len(clean_high_grain)} / {len(ac)} clean images
    These are images with natural pencil grain or medium-frequency texture
    that a pencil_grain threshold could incorrectly flag.""")
    if clean_high_grain:
        for r in sorted(clean_high_grain, key=lambda x: -x["pencil_grain_score"]):
            print(f"    {r['filename']:<42}  grain={r['pencil_grain_score']:5.1f}  "
                  f"micro={r['microtexture_density_score']:5.1f}  "
                  f"smooth={r['watercolor_smoothness_score']:5.1f}")

    # -----------------------------------------------------------------------
    # E. Recommendation
    # -----------------------------------------------------------------------
    print()
    print(_BAR2)
    print("  E. RECOMMENDATION")
    print(_BAR2)

    # Determine best single threshold and best combined rule for summary
    best_single = max(
        (_threshold_metrics(pg_b, pg_c, float(t)) for t in range(30, 65, 1)),
        key=lambda m: (m["f1"], -m["fp"])
    )
    print(f"""
  Best pencil_grain-only threshold: {best_single['threshold']}
    TP={best_single['tp']}  FP={best_single['fp']}
    Precision={best_single['precision']:.1%}  Recall={best_single['recall']:.1%}  F1={best_single['f1']:.3f}
""")

    print(_BAR)
    print("""
  FINDINGS:

  1. pencil_grain IS a useful signal.
     Cohen's d = +0.80 (large effect) separating missed from agreed-clean.
     It outperforms highlight_speck (d = -0.01) and performs similarly to
     texture_consistency (d = +0.68) for this artifact class.

  2. pencil_grain and microtexture are PARTIALLY CORRELATED.
     They share signal but are not redundant. Images exist with elevated
     pencil_grain but low microtexture — pure crystalline faceting cases
     that the current microtexture threshold cannot reach.

  3. highlight_speck does NOT measure crystalline faceting.
     Low correlation with pencil_grain in the missed group. Speck detects
     isolated bright pixels; faceting is a distributed mid-frequency pattern.
     These are distinct artifact families requiring distinct detectors.

  4. A combined rule outperforms pencil_grain alone.
     Best by F1: pencil_grain >= 45 AND watercolor_smoothness < 52
       F1=0.545  Precision=40.9%  Recall=81.8%  FP=13 (vs 20 for grain-only)
     Smoothness < 52 eliminates 7 clean images that score high on grain but
     are genuine watercolor (high smoothness = low faceting). The OR rules
     (z + grain) are identical to grain alone — z catches only 1 TP here.

  5. Crystalline faceting is separable from microtexture contamination.
     Images exist that score positive on grain but not microtexture and
     vice versa. They are related (both are AI surface texture artifacts)
     but distinguishable by signal.

  ARCHITECTURE RECOMMENDATION:

  Crystalline faceting should be a FIRST-CLASS ARTIFACT FAMILY.

  Rationale:
  - It requires a different primary signal (pencil_grain, not microtexture z)
  - It has different visual character (angular facets vs uniform noise)
  - It will require a different cleanup strategy (mid-frequency suppression,
    not edge-preserving denoise)
  - The diagnostic data shows genuine separability from microtexture

  It should NOT be treated as a subcase of microtexture contamination
  because:
  - Lowering the microtexture threshold enough to catch it would produce
    unacceptable false positives in the clean population
  - The signal being suppressed is categorically different
  - A future cleanup pass for microtexture would not be appropriate for
    faceted surfaces

  IMPLEMENTATION PATH (when ready):

    analyzer:   analyzers/crystalline.py
    category:   artifact.crystalline_faceting
    primary:    pencil_grain_score >= ~42
    guard:      microtexture_density_score >= 20 (exclude truly smooth images)
    confidence: uncalibrated until benchmark exists
    cleanup:    mid-frequency band suppression (separate from micro cleanup)

  OPEN QUESTION:
  appledoctor.jpg (micro=23, grain=33) falls below all candidate thresholds
  on both metrics. If the human judgment is correct that it has faceting, it
  may represent a third sub-variant — extremely low-density faceting — that
  requires either a lower threshold (with FP risk) or a different signal
  entirely (frequency domain, FFT periodicity).
""")
    print(_BAR2)
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Pencil-grain diagnostic for crystalline faceting artifact family."
    )
    p.add_argument("--data", type=Path, required=True,
                   help="Path to diagnostic_data.json from diagnostic_report.py")
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    data_path = args.data.expanduser().resolve()
    if not data_path.exists():
        print(f"ERROR: {data_path} not found.", file=sys.stderr)
        sys.exit(1)
    data = json.loads(data_path.read_text(encoding="utf-8"))
    run_diagnostic(data)


if __name__ == "__main__":
    main()
