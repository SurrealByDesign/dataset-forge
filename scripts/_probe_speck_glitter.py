"""
Speck / glitter artifact probe — anthropomorph dataset.

Research-only script. Does not modify any production code, analyzer logic,
thresholds, or benchmarks.

Investigates whether speck/glitter artifacts form a distinct, measurable
phenomenon in the anthropomorph dataset, separate from:
  - texture.high_microtexture (TextureAnalyzer)
  - artifact.crystalline_faceting (CrystallineFacetingAnalyzer)

The existing signal:
  highlight_speck_score = _score(100 * (1 - exp(-ratio / 0.004)))
  where ratio = fraction of pixels that are (>=242 grey) AND (>=28 above local blur)

New signals measured:
  speck_raw_ratio      Raw pixel fraction before saturating transform
                       (recovers the signal that the transform compresses)
  speck_count          Absolute number of speck pixels (not normalised)
  speck_component_count  Connected components in the isolated-bright mask
                       Glitter = many small scattered components
                       Specular highlight = few large components
  speck_mean_comp_size Mean size (pixels) per component
  speck_size_cv        Coefficient of variation of component sizes
                       Glitter is uniform (low CV); specular is variable (high CV)
  speck_scatter_index  Mean distance of component centroids from image centre,
                       normalised by image diagonal. High = specks everywhere.
  speck_brightness_excess Mean (pixel - local_blur) at speck pixels
                       How isolated / anomalous each speck is relative to surroundings

Outputs (benchmarks/results/probe_speck_glitter/):
  probe_speck_data.json           Per-image full metric table
  probe_speck_report.txt          Statistics, ranked tables, Cohen d analysis
  contact_sheet_top20_speck.png   Top 20 by highlight_speck_score
  contact_sheet_top20_components.png  Top 20 by speck_component_count
  contact_sheet_low_speck.png     20 lowest highlight_speck_score (clean reference)
  contact_sheet_speck_only.png    High speck, NOT flagged by either existing analyzer
"""

from __future__ import annotations

import json
import math
import statistics
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))

from dataset_forge.analysis.texture import evaluate_texture
from dataset_forge.discovery import discover_images

DATASET = Path("C:/Users/someo/Desktop/ANTHROPOMORPHS")
REPORT  = DATASET / "inspect_output" / "inspection_report.json"
REVIEW  = DATASET / "decision_review.json"
OUT_DIR = _ROOT / "benchmarks" / "results" / "probe_speck_glitter"
OUT_DIR.mkdir(parents=True, exist_ok=True)

ANALYSIS_MAX = 512
THUMB_SIZE   = 220
SPECK_BRIGHT  = 242.0   # must match _highlight_speck in texture.py
SPECK_DELTA   = 28.0    # must match _highlight_speck in texture.py
SPECK_BLUR_SIG = 1.2    # must match _highlight_speck in texture.py


# ---------------------------------------------------------------------------
# New speck signals
# ---------------------------------------------------------------------------

def _measure_speck(path: Path, existing: object) -> dict | None:
    """Extend existing evaluate_texture result with new speck signals."""
    try:
        img = Image.open(path).convert("RGB")
        img.thumbnail((ANALYSIS_MAX, ANALYSIS_MAX), Image.Resampling.LANCZOS)
        rgb = np.asarray(img, dtype=np.uint8)
    except Exception:
        return None

    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32)
    h, w = gray.shape
    if min(h, w) < 8:
        return None

    # Reproduce the exact speck mask from _highlight_speck
    local_mean = cv2.GaussianBlur(gray, (0, 0), SPECK_BLUR_SIG)
    speck_mask = (gray >= SPECK_BRIGHT) & ((gray - local_mean) >= SPECK_DELTA)
    speck_mask_u8 = speck_mask.astype(np.uint8) * 255

    total_pixels = h * w
    speck_count  = int(np.sum(speck_mask))
    speck_raw_ratio = speck_count / total_pixels

    # --- Connected component analysis ---
    num_labels, labels, stats_cc, centroids = cv2.connectedComponentsWithStats(
        speck_mask_u8, connectivity=8
    )
    # Label 0 = background; labels 1..num_labels-1 are components
    comp_sizes     = [int(stats_cc[i, cv2.CC_STAT_AREA]) for i in range(1, num_labels)]
    comp_centroids = [(float(centroids[i, 0]), float(centroids[i, 1]))
                      for i in range(1, num_labels)]

    speck_component_count = len(comp_sizes)

    if comp_sizes:
        speck_mean_comp_size = statistics.mean(comp_sizes)
        if speck_component_count > 1:
            mean_s = statistics.mean(comp_sizes)
            speck_size_cv = (
                statistics.pstdev(comp_sizes) / mean_s if mean_s > 0 else 0.0
            )
        else:
            speck_size_cv = 0.0

        # Scatter index: mean distance of component centroids from image centre
        # normalised by half-diagonal
        cx, cy   = w / 2.0, h / 2.0
        diagonal = math.sqrt(cx**2 + cy**2)  # half-diagonal
        if diagonal > 0:
            dists = [
                math.sqrt((px - cx) ** 2 + (py - cy) ** 2) / diagonal
                for px, py in comp_centroids
            ]
            speck_scatter_index = statistics.mean(dists)
        else:
            speck_scatter_index = 0.0
    else:
        speck_mean_comp_size  = 0.0
        speck_size_cv         = 0.0
        speck_scatter_index   = 0.0

    # --- Brightness excess at speck pixels ---
    if speck_count > 0:
        excess = (gray - local_mean)[speck_mask]
        speck_brightness_excess = float(np.mean(excess))
    else:
        speck_brightness_excess = 0.0

    return {
        "speck_raw_ratio":          round(speck_raw_ratio * 1000, 4),  # per-mille
        "speck_count":              speck_count,
        "speck_component_count":    speck_component_count,
        "speck_mean_comp_size":     round(speck_mean_comp_size, 2),
        "speck_size_cv":            round(speck_size_cv, 4),
        "speck_scatter_index":      round(speck_scatter_index, 4),
        "speck_brightness_excess":  round(speck_brightness_excess, 2),
    }


# ---------------------------------------------------------------------------
# Dataset scan
# ---------------------------------------------------------------------------

def _scan() -> list[dict]:
    discovery = discover_images(DATASET, recursive=False)
    images = sorted(discovery.images, key=lambda p: p.name.casefold())
    total = len(images)
    print(f"Scanning {total} images ...")

    records = []
    for i, path in enumerate(images, 1):
        if i % 10 == 0 or i == total:
            print(f"  {i}/{total}", end="\r")
        ex = evaluate_texture(path)
        if ex.status != "analyzed":
            continue
        new = _measure_speck(path, ex)
        if new is None:
            continue
        records.append({
            "name":                path.name,
            "path":                str(path),
            # Existing signals from evaluate_texture
            "highlight_speck":     ex.highlight_speck_score,
            "microtexture":        ex.microtexture_density_score,
            "pencil_grain":        ex.pencil_grain_score,
            "watercolor_smooth":   ex.watercolor_smoothness_score,
            "edge_sharpness":      ex.edge_sharpness_score,
            "local_contrast":      ex.local_contrast_score,
            # New speck signals
            **new,
        })
    print(f"\nMeasured {len(records)} images.")
    return records


# ---------------------------------------------------------------------------
# Load existing findings and review labels
# ---------------------------------------------------------------------------

def _load_findings() -> tuple[set[str], set[str]]:
    texture, crystalline = set(), set()
    if not REPORT.exists():
        return texture, crystalline
    data = json.loads(REPORT.read_text("utf-8"))
    for f in data.get("findings", []):
        name = Path(f["image_path"]).name
        cat  = f.get("category", "")
        if cat == "texture.high_microtexture":
            texture.add(name)
        elif cat == "artifact.crystalline_faceting":
            crystalline.add(name)
    return texture, crystalline


def _load_review_labels() -> dict[str, str]:
    """Return name -> 'AGREE'|'DISAGREE'|'UNSURE' from decision_review.json."""
    if not REVIEW.exists():
        return {}
    data = json.loads(REVIEW.read_text("utf-8"))
    return {name: rv.get("review", "") for name, rv in data.get("reviews", {}).items()}


# ---------------------------------------------------------------------------
# Cohen's d
# ---------------------------------------------------------------------------

def _cohen_d(group_a: list[float], group_b: list[float]) -> float:
    if len(group_a) < 2 or len(group_b) < 2:
        return 0.0
    ma, mb = statistics.mean(group_a), statistics.mean(group_b)
    sa = statistics.variance(group_a)
    sb = statistics.variance(group_b)
    na, nb = len(group_a), len(group_b)
    pooled = math.sqrt(((na - 1) * sa + (nb - 1) * sb) / (na + nb - 2))
    return (ma - mb) / pooled if pooled > 0 else 0.0


# ---------------------------------------------------------------------------
# Contact sheet
# ---------------------------------------------------------------------------

def _make_contact_sheet(
    records: list[dict],
    title: str,
    filename: str,
    label_fn,
    cols: int = 5,
    max_items: int = 20,
) -> None:
    items = records[:max_items]
    if not items:
        print(f"  (skipped — no items for {filename})")
        return

    rows = math.ceil(len(items) / cols)
    pad  = 6
    lh   = 44
    cw   = THUMB_SIZE + 2 * pad
    ch   = THUMB_SIZE + lh + 2 * pad
    hdr  = 52

    canvas = Image.new("RGB", (cols * cw, hdr + rows * ch), (18, 22, 30))
    draw   = ImageDraw.Draw(canvas)
    try:
        fsm = ImageFont.truetype("arial.ttf", 11)
        fhd = ImageFont.truetype("arial.ttf", 15)
    except OSError:
        fsm = fhd = ImageFont.load_default()

    draw.text((10, 14), title, fill=(220, 230, 240), font=fhd)

    for idx, rec in enumerate(items):
        col = idx % cols
        row = idx // cols
        x0  = col * cw + pad
        y0  = hdr + row * ch + pad

        try:
            img = Image.open(rec["path"]).convert("RGB")
            img.thumbnail((THUMB_SIZE, THUMB_SIZE), Image.Resampling.LANCZOS)
            tw, th = img.size
            canvas.paste(img, (x0 + (THUMB_SIZE - tw) // 2, y0 + (THUMB_SIZE - th) // 2))
        except Exception:
            draw.rectangle([x0, y0, x0 + THUMB_SIZE, y0 + THUMB_SIZE], fill=(40, 45, 55))

        draw.rectangle(
            [x0, y0 + THUMB_SIZE, x0 + THUMB_SIZE, y0 + THUMB_SIZE + lh],
            fill=(28, 34, 46),
        )
        draw.text((x0 + 4, y0 + THUMB_SIZE + 4),
                  rec["name"][:26], fill=(190, 200, 215), font=fsm)
        for li, line in enumerate(label_fn(rec).split("\n")):
            draw.text((x0 + 4, y0 + THUMB_SIZE + 18 + li * 13),
                      line, fill=(160, 200, 160), font=fsm)

    out = OUT_DIR / filename
    canvas.save(out)
    print(f"  Saved {out.name}")


# ---------------------------------------------------------------------------
# Pearson r
# ---------------------------------------------------------------------------

def _pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 2:
        return 0.0
    mx, my = statistics.mean(xs), statistics.mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx  = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy  = math.sqrt(sum((y - my) ** 2 for y in ys))
    return round(num / (dx * dy), 4) if dx > 1e-9 and dy > 1e-9 else 0.0


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def _write_report(
    records: list[dict],
    tex: set[str],
    cryst: set[str],
    labels: dict[str, str],
) -> None:
    W   = 90
    BAR = "-" * W
    B2  = "=" * W
    lines: list[str] = []

    def h(t): lines.extend(["", B2, f"  {t}", B2])
    def s(t): lines.extend(["", t, BAR])

    lines.append("SPECK / GLITTER ARTIFACT PROBE -- ANTHROPOMORPH DATASET")
    lines.append(f"Images scanned: {len(records)}")
    lines.append(f"TextureAnalyzer findings:     {len(tex)}")
    lines.append(f"Crystalline findings:         {len(cryst)}")
    lines.append(f"Decision-reviewed images:     {len(labels)}")

    # ---------------------------------------------------------------- stats
    h("DATASET STATISTICS")
    metrics_order = [
        "highlight_speck", "speck_raw_ratio", "speck_count",
        "speck_component_count", "speck_mean_comp_size", "speck_size_cv",
        "speck_scatter_index", "speck_brightness_excess",
        "microtexture", "pencil_grain", "watercolor_smooth",
    ]
    lines.append(
        f"  {'Metric':<28} {'mean':>8} {'stddev':>8} {'p10':>8} "
        f"{'p50':>8} {'p90':>8} {'max':>8}"
    )
    lines.append(f"  {'-'*28} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*8}")
    for m in metrics_order:
        vals = sorted(r[m] for r in records)
        n    = len(vals)
        lines.append(
            f"  {m:<28} {statistics.mean(vals):>8.2f} "
            f"{statistics.pstdev(vals):>8.2f} "
            f"{vals[max(0,int(n*0.10))]:>8.2f} "
            f"{vals[n//2]:>8.2f} "
            f"{vals[min(n-1,int(n*0.90))]:>8.2f} "
            f"{vals[-1]:>8.2f}"
        )

    # ------------------------------------------------ raw ratio distribution
    h("HIGHLIGHT_SPECK RAW RATIO DISTRIBUTION (speck_raw_ratio, per-mille)")
    lines.append("  (This is the ratio BEFORE the saturating transform.)")
    lines.append("  Saturating scale = 0.4 per-mille (score ~63). 1.0 per-mille = score ~92.")
    by_raw = sorted(records, key=lambda r: r["speck_raw_ratio"], reverse=True)
    lines.append("")
    lines.append(
        f"  {'filename':<40} {'raw(pm)':>8} {'speck_sc':>9} "
        f"{'comp_ct':>8} {'scatter':>8} {'micro':>7} {'cryst':>6} {'tex':>4}"
    )
    lines.append(f"  {'-'*40} {'-'*8} {'-'*9} {'-'*8} {'-'*8} {'-'*7} {'-'*6} {'-'*4}")
    for r in by_raw:
        c = "Y" if r["name"] in cryst else "-"
        t = "Y" if r["name"] in tex   else "-"
        lines.append(
            f"  {r['name']:<40} {r['speck_raw_ratio']:>8.3f} "
            f"{r['highlight_speck']:>9.1f} {r['speck_component_count']:>8d} "
            f"{r['speck_scatter_index']:>8.3f} {r['microtexture']:>7.1f} "
            f"{c:>6} {t:>4}"
        )

    # ---------------------------------------- top 20 by component count
    h("TOP 20 BY SPECK_COMPONENT_COUNT")
    top_comp = sorted(records, key=lambda r: r["speck_component_count"], reverse=True)
    lines.append(
        f"  {'filename':<40} {'comp_ct':>8} {'raw(pm)':>8} {'speck_sc':>9} "
        f"{'mean_sz':>8} {'size_cv':>8} {'scatter':>8} {'micro':>7} {'cryst':>6} {'tex':>4}"
    )
    lines.append(
        f"  {'-'*40} {'-'*8} {'-'*8} {'-'*9} "
        f"{'-'*8} {'-'*8} {'-'*8} {'-'*7} {'-'*6} {'-'*4}"
    )
    for r in top_comp[:20]:
        c = "Y" if r["name"] in cryst else "-"
        t = "Y" if r["name"] in tex   else "-"
        lines.append(
            f"  {r['name']:<40} {r['speck_component_count']:>8d} "
            f"{r['speck_raw_ratio']:>8.3f} {r['highlight_speck']:>9.1f} "
            f"{r['speck_mean_comp_size']:>8.2f} {r['speck_size_cv']:>8.3f} "
            f"{r['speck_scatter_index']:>8.3f} {r['microtexture']:>7.1f} "
            f"{c:>6} {t:>4}"
        )

    # ------------------------------------ overlap with existing analyzers
    h("OVERLAP WITH EXISTING ANALYZERS")
    speck_thresh_candidates = [r for r in records if r["highlight_speck"] >= 30]
    lines.append(f"  highlight_speck >= 30:   {len(speck_thresh_candidates)} images")
    lines.append(f"  highlight_speck >= 50:   {sum(1 for r in records if r['highlight_speck'] >= 50)}")
    lines.append(f"  highlight_speck >= 70:   {sum(1 for r in records if r['highlight_speck'] >= 70)}")
    lines.append(f"  highlight_speck >= 80:   {sum(1 for r in records if r['highlight_speck'] >= 80)}")
    lines.append("")

    top30_speck = {r["name"] for r in sorted(records, key=lambda r: r["highlight_speck"], reverse=True)[:30]}
    lines.append(f"  Top-30 by highlight_speck: {len(top30_speck)}")
    lines.append(f"  ... AND crystalline-flagged: {len(top30_speck & cryst)}")
    lines.append(f"  ... AND texture-flagged:     {len(top30_speck & tex)}")
    speck_only = top30_speck - cryst - tex
    lines.append(f"  ... NOT caught by either:    {len(speck_only)}")
    if speck_only:
        lines.append("")
        lines.append("  Speck-top30 images not caught by TextureAnalyzer or Crystalline:")
        for name in sorted(speck_only):
            r = next(x for x in records if x["name"] == name)
            lines.append(
                f"    {name:<40} speck={r['highlight_speck']:.1f}  "
                f"raw={r['speck_raw_ratio']:.3f}pm  comp={r['speck_component_count']}  "
                f"micro={r['microtexture']:.1f}  grain={r['pencil_grain']:.1f}"
            )

    # ------------------------------------ Cohen's d vs review labels
    h("COHEN'S D ANALYSIS (confirmed artifact vs confirmed clean)")
    # 'DISAGREE' with DF = DF said clean but reviewer says artifact
    # 'AGREE' in texture set = DF said finding, reviewer agreed = confirmed artifact
    agreed_artifact = [r for r in records
                       if r["name"] in tex and labels.get(r["name"]) == "AGREE"]
    agreed_clean    = [r for r in records
                       if labels.get(r["name"]) == "AGREE" and r["name"] not in tex
                       and r["name"] not in cryst]

    lines.append(f"  Confirmed artifact (texture finding + AGREE): n={len(agreed_artifact)}")
    lines.append(f"  Confirmed clean (AGREE, no findings):         n={len(agreed_clean)}")
    lines.append("")

    if len(agreed_artifact) >= 2 and len(agreed_clean) >= 2:
        for m in ["highlight_speck", "speck_raw_ratio", "speck_component_count",
                  "speck_scatter_index", "speck_brightness_excess", "microtexture"]:
            a_vals = [r[m] for r in agreed_artifact]
            c_vals = [r[m] for r in agreed_clean]
            d = _cohen_d(a_vals, c_vals)
            lines.append(
                f"  {m:<30}  d = {d:+.3f}  "
                f"(artifact mean={statistics.mean(a_vals):.2f}, "
                f"clean mean={statistics.mean(c_vals):.2f})"
            )
    else:
        lines.append("  Insufficient labeled samples for Cohen's d (need n>=2 in each group).")

    # ------------------------------------ correlation matrix
    h("PEARSON CORRELATION (highlight_speck vs other signals)")
    speck_vals = [r["highlight_speck"] for r in records]
    for m in ["speck_raw_ratio", "speck_component_count", "speck_mean_comp_size",
              "speck_size_cv", "speck_scatter_index", "speck_brightness_excess",
              "microtexture", "pencil_grain", "watercolor_smooth", "edge_sharpness",
              "local_contrast"]:
        other = [r[m] for r in records]
        lines.append(
            f"  highlight_speck vs {m:<28}  r = {_pearson(speck_vals, other):+.4f}"
        )
    lines.append("")
    lines.append("  Pearson correlation of new signals vs microtexture:")
    micro_vals = [r["microtexture"] for r in records]
    for m in ["highlight_speck", "speck_raw_ratio", "speck_component_count",
              "speck_scatter_index"]:
        other = [r[m] for r in records]
        lines.append(
            f"  microtexture vs {m:<30}  r = {_pearson(micro_vals, other):+.4f}"
        )

    # --------------------------------- speck score vs vtp clean ref
    h("CLEAN REFERENCE CHECK")
    for name in ["vtp4jc1040s51.jpg", "monalisa.jpg", "candycornjason.jpg"]:
        r = next((x for x in records if x["name"] == name), None)
        if r:
            c = "cryst" if r["name"] in cryst else ""
            t = "tex"   if r["name"] in tex   else ""
            flag = ",".join(filter(None, [c, t])) or "none"
            lines.append(
                f"  {name}: speck={r['highlight_speck']:.1f}  raw={r['speck_raw_ratio']:.3f}pm  "
                f"comp={r['speck_component_count']}  scatter={r['speck_scatter_index']:.3f}  "
                f"micro={r['microtexture']:.1f}  flags={flag}"
            )

    # ------------------------------------ per-image full table
    h("FULL TABLE (sorted by highlight_speck desc)")
    lines.append(
        f"  {'filename':<40} {'speck':>6} {'raw':>6} {'comp':>5} "
        f"{'sz':>5} {'cv':>5} {'scat':>5} {'bex':>5} "
        f"{'micro':>6} {'grain':>6} {'cryst':>6} {'tex':>4}"
    )
    lines.append(
        f"  {'-'*40} {'-'*6} {'-'*6} {'-'*5} "
        f"{'-'*5} {'-'*5} {'-'*5} {'-'*5} "
        f"{'-'*6} {'-'*6} {'-'*6} {'-'*4}"
    )
    for r in sorted(records, key=lambda r: r["highlight_speck"], reverse=True):
        c = "Y" if r["name"] in cryst else "-"
        t = "Y" if r["name"] in tex   else "-"
        lines.append(
            f"  {r['name']:<40} {r['highlight_speck']:>6.1f} "
            f"{r['speck_raw_ratio']:>6.3f} {r['speck_component_count']:>5d} "
            f"{r['speck_mean_comp_size']:>5.1f} {r['speck_size_cv']:>5.3f} "
            f"{r['speck_scatter_index']:>5.3f} {r['speck_brightness_excess']:>5.1f} "
            f"{r['microtexture']:>6.1f} {r['pencil_grain']:>6.1f} "
            f"{c:>6} {t:>4}"
        )

    out = OUT_DIR / "probe_speck_report.txt"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  Saved {out.name}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    print("=== Speck / Glitter Artifact Probe ===")
    print(f"Dataset: {DATASET}")
    print(f"Output:  {OUT_DIR}")
    print()

    records = _scan()
    if not records:
        print("ERROR: no records.")
        return 1

    tex, cryst = _load_findings()
    labels     = _load_review_labels()

    # Save raw JSON
    json_out = OUT_DIR / "probe_speck_data.json"
    json_out.write_text(json.dumps(records, indent=2), encoding="utf-8")
    print(f"  Saved {json_out.name}")

    print("\nGenerating contact sheets...")

    by_speck = sorted(records, key=lambda r: r["highlight_speck"], reverse=True)
    _make_contact_sheet(
        by_speck, "Top 20: highlight_speck_score",
        "contact_sheet_top20_speck.png",
        lambda r: (
            f"speck={r['highlight_speck']:.1f}  raw={r['speck_raw_ratio']:.3f}pm\n"
            f"comp={r['speck_component_count']}  micro={r['microtexture']:.1f}"
        ),
    )

    by_comp = sorted(records, key=lambda r: r["speck_component_count"], reverse=True)
    _make_contact_sheet(
        by_comp, "Top 20: speck_component_count (most isolated bright components)",
        "contact_sheet_top20_components.png",
        lambda r: (
            f"comp={r['speck_component_count']}  speck={r['highlight_speck']:.1f}\n"
            f"raw={r['speck_raw_ratio']:.3f}pm  micro={r['microtexture']:.1f}"
        ),
    )

    low_speck = sorted(records, key=lambda r: r["highlight_speck"])
    _make_contact_sheet(
        low_speck, "Lowest 20: highlight_speck_score (clean reference)",
        "contact_sheet_low_speck.png",
        lambda r: (
            f"speck={r['highlight_speck']:.1f}  micro={r['microtexture']:.1f}\n"
            f"grain={r['pencil_grain']:.1f}"
        ),
    )

    # Speck-only: top-30 speck, not caught by either existing analyzer
    top30_speck = sorted(records, key=lambda r: r["highlight_speck"], reverse=True)[:30]
    speck_only  = [r for r in top30_speck if r["name"] not in cryst and r["name"] not in tex]
    _make_contact_sheet(
        speck_only, "Speck-only candidates (top-30 speck, not crystalline, not texture)",
        "contact_sheet_speck_only.png",
        lambda r: (
            f"speck={r['highlight_speck']:.1f}  raw={r['speck_raw_ratio']:.3f}pm\n"
            f"comp={r['speck_component_count']}  micro={r['microtexture']:.1f}"
        ),
    )

    # Co-detected with texture (microtexture + speck together)
    tex_and_speck = [r for r in by_speck if r["name"] in tex]
    _make_contact_sheet(
        tex_and_speck, "Texture-flagged images, ranked by highlight_speck_score",
        "contact_sheet_tex_speck.png",
        lambda r: (
            f"speck={r['highlight_speck']:.1f}  micro={r['microtexture']:.1f}\n"
            f"comp={r['speck_component_count']}  grain={r['pencil_grain']:.1f}"
        ),
    )

    print("\nWriting report...")
    _write_report(records, tex, cryst, labels)

    print(f"\nDone. Results in: {OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
