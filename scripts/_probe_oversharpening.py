"""
Oversharpening / halo artifact probe -- anthropomorph dataset.

Research-only script. Does not modify any production code, analyzer logic,
thresholds, or benchmarks.

Investigates whether oversharpening / edge-halo artifacts form a distinct,
measurable phenomenon in the anthropomorph dataset, separate from:
  - texture.high_microtexture (TextureAnalyzer)
  - artifact.crystalline_faceting (CrystallineFacetingAnalyzer)

New candidate signals measured per image:
  - edge_sharpness   : existing metric (Laplacian variance saturating at 1800)
  - laplacian_mean   : mean absolute Laplacian (more stable than variance alone)
  - halo_score       : dark/bright banding in a strip adjacent to strong edges
                       Methodology: at each Canny edge pixel, sample a 4px-wide
                       strip perpendicular to the gradient direction. Measure
                       the ratio of max-to-min brightness in that strip. High
                       ratio = visible halo / ringing.
  - ringing_score    : sign-alternation density of the Laplacian near edges.
                       True oversharpening produces alternating positive/negative
                       Laplacian lobes (overshoot then undershoot).
  - edge_hf_ratio    : fraction of total high-frequency energy concentrated at
                       edge pixels (vs distributed across surfaces). Pure
                       oversharpening concentrates HF energy AT edges;
                       crystalline faceting distributes it across surfaces.
  - edge_contrast_inflation : ratio of local contrast near edges to local
                       contrast far from edges. Oversharpening inflates edge
                       contrast without raising surface contrast.

Outputs (to benchmarks/results/probe_oversharpening/):
  - probe_oversharpening_data.json    Full per-image metric table
  - probe_oversharpening_report.txt   Ranked summary + group analysis
  - contact_sheet_top20_halo.png      Top 20 by halo_score
  - contact_sheet_top20_ringing.png   Top 20 by ringing_score
  - contact_sheet_clean_reference.png 20 cleanest images (low all signals)
  - contact_sheet_vs_crystalline.png  Co-detected: crystalline AND high halo
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
OUT_DIR = _ROOT / "benchmarks" / "results" / "probe_oversharpening"
OUT_DIR.mkdir(parents=True, exist_ok=True)

ANALYSIS_MAX = 512   # pixels (max dim before analysis, same as evaluate_texture)
THUMB_SIZE   = 220   # contact-sheet thumbnail size


# ---------------------------------------------------------------------------
# Oversharpening signal measurement
# ---------------------------------------------------------------------------

def _measure_oversharpening(path: Path) -> dict | None:
    """Compute candidate oversharpening/halo signals. Returns None on error."""
    try:
        img = Image.open(path).convert("RGB")
        img.thumbnail((ANALYSIS_MAX, ANALYSIS_MAX), Image.Resampling.LANCZOS)
        rgb = np.asarray(img, dtype=np.uint8)
    except Exception:
        return None

    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32)
    if min(gray.shape) < 8:
        return None

    # --- Laplacian ---
    lap = cv2.Laplacian(gray, cv2.CV_32F, ksize=3)
    lap_abs = np.abs(lap)
    laplacian_mean = float(np.mean(lap_abs))
    laplacian_var  = float(np.var(lap))
    # Saturating transform matching the existing edge_sharpness formula
    edge_sharpness = round(100.0 * (1.0 - math.exp(-max(0.0, laplacian_var) / 1800.0)), 2)

    # --- Edge map (Canny) ---
    gray_u8 = np.clip(gray, 0, 255).astype(np.uint8)
    # Sigma-1 smoothed before Canny to suppress noise-driven edges
    blurred_u8 = cv2.GaussianBlur(gray_u8, (0, 0), 1.0)
    edges = cv2.Canny(blurred_u8, threshold1=40, threshold2=100)  # binary edge mask
    edge_mask = edges > 0
    edge_pixel_count = int(np.sum(edge_mask))

    # --- Dilated edge zone (4 px ring around edges) ---
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    edge_zone = cv2.dilate(edges, kernel) > 0
    non_edge_zone = ~edge_zone

    # --- High-frequency energy map (pixel vs sigma-1 blur) ---
    blur1 = cv2.GaussianBlur(gray, (0, 0), 1.0)
    hf = np.abs(gray - blur1)

    hf_total = float(np.sum(hf))
    if edge_pixel_count > 0 and hf_total > 0.0:
        hf_at_edges  = float(np.sum(hf[edge_zone]))
        edge_hf_ratio = round(hf_at_edges / hf_total, 4)
    else:
        edge_hf_ratio = 0.0

    # --- Edge contrast inflation ---
    # Local contrast = block std-dev. Compare near-edge blocks vs far-from-edge blocks.
    block = max(8, min(gray.shape) // 16)
    near_contrasts = []
    far_contrasts  = []
    for y in range(0, gray.shape[0] - block, block):
        for x in range(0, gray.shape[1] - block, block):
            patch_g = gray[y:y+block, x:x+block]
            patch_e = edge_zone[y:y+block, x:x+block]
            c = float(np.std(patch_g))
            if patch_e.mean() > 0.25:
                near_contrasts.append(c)
            else:
                far_contrasts.append(c)
    if near_contrasts and far_contrasts:
        mean_near = statistics.mean(near_contrasts)
        mean_far  = statistics.mean(far_contrasts)
        edge_contrast_inflation = round(
            (mean_near - mean_far) / max(mean_far, 1.0) * 100.0, 2
        )
    else:
        edge_contrast_inflation = 0.0

    # --- Halo score ---
    # For each Canny edge pixel, sample a perpendicular strip of width 4px
    # on each side. A halo shows as: far_side darker than edge, near_side brighter
    # (or vice versa). Measure max-to-min ratio in the strip.
    halo_scores: list[float] = []
    if edge_pixel_count > 0:
        # Use Sobel gradient direction for perpendicular sampling
        sobel_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
        sobel_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
        h, w = gray.shape
        ys, xs = np.where(edge_mask)
        # Sample a subset to keep runtime manageable
        sample_step = max(1, len(ys) // 800)
        for ey, ex in zip(ys[::sample_step], xs[::sample_step]):
            gx = float(sobel_x[ey, ex])
            gy = float(sobel_y[ey, ex])
            mag = math.sqrt(gx*gx + gy*gy)
            if mag < 4.0:
                continue
            # Perpendicular direction (normal to edge)
            nx, ny = gx / mag, gy / mag
            # Sample 8 points: 4 on each side of edge, 1..4 px out
            samples: list[float] = []
            for d in range(-4, 5):
                if d == 0:
                    continue
                px = int(round(ex + nx * d))
                py = int(round(ey + ny * d))
                if 0 <= px < w and 0 <= py < h:
                    samples.append(float(gray[py, px]))
            if len(samples) >= 4:
                rng = max(samples) - min(samples)
                halo_scores.append(rng)
    halo_score = round(
        float(statistics.mean(halo_scores)) if halo_scores else 0.0, 2
    )

    # --- Ringing score ---
    # Near edge pixels: count sign alternations in Laplacian along gradient direction.
    # True ringing = positive lobe immediately followed by negative lobe.
    ringing_alternations = 0
    ringing_samples = 0
    if edge_pixel_count > 0:
        # Reuse the same edge pixel sample
        for ey, ex in zip(ys[::sample_step], xs[::sample_step]):
            gx = float(sobel_x[ey, ex])
            gy = float(sobel_y[ey, ex])
            mag = math.sqrt(gx*gx + gy*gy)
            if mag < 4.0:
                continue
            nx, ny = gx / mag, gy / mag
            signs = []
            for d in range(-5, 6):
                if d == 0:
                    continue
                px = int(round(ex + nx * d))
                py = int(round(ey + ny * d))
                if 0 <= px < w and 0 <= py < h:
                    v = float(lap[py, px])
                    if abs(v) > 2.0:
                        signs.append(1 if v > 0 else -1)
            # Count sign changes
            alts = sum(
                1 for i in range(len(signs) - 1) if signs[i] != signs[i+1]
            )
            ringing_alternations += alts
            ringing_samples += max(len(signs) - 1, 1)
    ringing_score = round(
        100.0 * ringing_alternations / ringing_samples
        if ringing_samples > 0 else 0.0,
        2,
    )

    return {
        "edge_sharpness":          edge_sharpness,
        "laplacian_mean":          round(laplacian_mean, 2),
        "laplacian_var":           round(laplacian_var, 2),
        "halo_score":              halo_score,
        "ringing_score":           ringing_score,
        "edge_hf_ratio":           edge_hf_ratio,
        "edge_contrast_inflation": edge_contrast_inflation,
        "edge_pixel_density":      round(float(np.mean(edge_mask)) * 100.0, 2),
    }


# ---------------------------------------------------------------------------
# Dataset scan
# ---------------------------------------------------------------------------

def _scan_dataset() -> list[dict]:
    discovery = discover_images(DATASET, recursive=False)
    images = sorted(discovery.images, key=lambda p: p.name.casefold())
    total = len(images)
    print(f"Scanning {total} images in {DATASET} ...")

    records = []
    for i, path in enumerate(images, 1):
        if i % 10 == 0 or i == total:
            print(f"  {i}/{total}", end="\r")
        existing = evaluate_texture(path)
        if existing.status != "analyzed":
            continue
        osh = _measure_oversharpening(path)
        if osh is None:
            continue
        records.append({
            "name":             path.name,
            "path":             str(path),
            # Existing signals
            "microtexture":     existing.microtexture_density_score,
            "edge_sharpness":   existing.edge_sharpness_score,
            "watercolor_smooth": existing.watercolor_smoothness_score,
            "pencil_grain":     existing.pencil_grain_score,
            "local_contrast":   existing.local_contrast_score,
            "highlight_speck":  existing.highlight_speck_score,
            # New oversharpening signals
            **osh,
        })
    print(f"\nMeasured {len(records)} images.")
    return records


# ---------------------------------------------------------------------------
# Cross-reference with inspection report
# ---------------------------------------------------------------------------

def _load_findings() -> tuple[set[str], set[str]]:
    """Return (texture_flagged, crystalline_flagged) sets of filenames."""
    texture     = set()
    crystalline = set()
    if not REPORT.exists():
        print(f"Warning: inspection report not found at {REPORT}")
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


# ---------------------------------------------------------------------------
# Contact sheet generation
# ---------------------------------------------------------------------------

def _make_contact_sheet(
    records: list[dict],
    title: str,
    filename: str,
    label_fn,
    cols: int = 5,
    max_items: int = 20,
) -> Path:
    items = records[:max_items]
    if not items:
        print(f"  No items for {filename}")
        return OUT_DIR / filename

    rows = math.ceil(len(items) / cols)
    pad = 6
    label_h = 38
    cell_w = THUMB_SIZE + 2 * pad
    cell_h = THUMB_SIZE + label_h + 2 * pad
    header_h = 48
    canvas_w = cols * cell_w
    canvas_h = header_h + rows * cell_h

    canvas = Image.new("RGB", (canvas_w, canvas_h), (18, 22, 30))
    draw = ImageDraw.Draw(canvas)
    try:
        font_sm = ImageFont.truetype("arial.ttf", 11)
        font_hd = ImageFont.truetype("arial.ttf", 16)
    except OSError:
        font_sm = ImageFont.load_default()
        font_hd = font_sm

    draw.text((10, 12), title, fill=(220, 230, 240), font=font_hd)

    for idx, rec in enumerate(items):
        col = idx % cols
        row = idx // cols
        x0 = col * cell_w + pad
        y0 = header_h + row * cell_h + pad

        # Thumbnail
        try:
            img = Image.open(rec["path"]).convert("RGB")
            img.thumbnail((THUMB_SIZE, THUMB_SIZE), Image.Resampling.LANCZOS)
            tw, th = img.size
            offset_x = (THUMB_SIZE - tw) // 2
            offset_y = (THUMB_SIZE - th) // 2
            canvas.paste(img, (x0 + offset_x, y0 + offset_y))
        except Exception:
            draw.rectangle([x0, y0, x0+THUMB_SIZE, y0+THUMB_SIZE], fill=(40, 45, 55))

        # Label
        label = label_fn(rec)
        draw.rectangle(
            [x0, y0 + THUMB_SIZE, x0 + THUMB_SIZE, y0 + THUMB_SIZE + label_h],
            fill=(28, 34, 46),
        )
        draw.text(
            (x0 + 4, y0 + THUMB_SIZE + 4),
            rec["name"][:24],
            fill=(190, 200, 215),
            font=font_sm,
        )
        draw.text(
            (x0 + 4, y0 + THUMB_SIZE + 18),
            label,
            fill=(160, 200, 160),
            font=font_sm,
        )

    out = OUT_DIR / filename
    canvas.save(out)
    print(f"  Saved {out.name}")
    return out


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------

def _write_report(
    records: list[dict],
    texture_flagged: set[str],
    crystalline_flagged: set[str],
    stats: dict,
) -> None:
    lines = []
    W = 80
    BAR  = "-" * W
    BAR2 = "=" * W

    def h(title):
        lines.append("")
        lines.append(BAR2)
        lines.append(f"  {title}")
        lines.append(BAR2)

    def s(title):
        lines.append("")
        lines.append(title)
        lines.append(BAR)

    lines.append("OVERSHARPENING / HALO ARTIFACT PROBE -- ANTHROPOMORPH DATASET")
    lines.append(f"Images scanned: {len(records)}")
    lines.append(f"Output: {OUT_DIR}")

    # --- Dataset statistics ---
    h("DATASET STATISTICS")
    metrics = [
        "edge_sharpness", "laplacian_mean", "halo_score",
        "ringing_score", "edge_hf_ratio", "edge_contrast_inflation",
        "edge_pixel_density",
    ]
    lines.append(f"  {'Metric':<30} {'mean':>7} {'stddev':>7} {'p10':>7} {'p90':>7} {'max':>7}")
    lines.append(f"  {'-'*30} {'-'*7} {'-'*7} {'-'*7} {'-'*7} {'-'*7}")
    for m in metrics:
        vals = sorted(r[m] for r in records)
        n    = len(vals)
        mean = statistics.mean(vals)
        sd   = statistics.pstdev(vals)
        p10  = vals[max(0, int(n * 0.10))]
        p90  = vals[min(n-1, int(n * 0.90))]
        mx   = vals[-1]
        lines.append(
            f"  {m:<30} {mean:>7.2f} {sd:>7.2f} {p10:>7.2f} {p90:>7.2f} {mx:>7.2f}"
        )

    # --- Top 20 by halo_score ---
    h("TOP 20 BY HALO_SCORE")
    top_halo = sorted(records, key=lambda r: r["halo_score"], reverse=True)[:20]
    lines.append(
        f"  {'filename':<35} {'halo':>6} {'ringing':>8} {'edge_sh':>8} "
        f"{'e_hf_r':>7} {'eci':>6} {'micro':>6} {'cryst':>6} {'tex':>5}"
    )
    lines.append(f"  {'-'*35} {'-'*6} {'-'*8} {'-'*8} {'-'*7} {'-'*6} {'-'*6} {'-'*6} {'-'*5}")
    for r in top_halo:
        c = "Y" if r["name"] in crystalline_flagged else "-"
        t = "Y" if r["name"] in texture_flagged else "-"
        lines.append(
            f"  {r['name']:<35} {r['halo_score']:>6.1f} {r['ringing_score']:>8.1f} "
            f"{r['edge_sharpness']:>8.1f} {r['edge_hf_ratio']:>7.3f} "
            f"{r['edge_contrast_inflation']:>6.1f} {r['microtexture']:>6.1f} "
            f"{c:>6} {t:>5}"
        )

    # --- Top 20 by ringing_score ---
    h("TOP 20 BY RINGING_SCORE")
    top_ring = sorted(records, key=lambda r: r["ringing_score"], reverse=True)[:20]
    lines.append(
        f"  {'filename':<35} {'ringing':>8} {'halo':>6} {'edge_sh':>8} "
        f"{'eci':>6} {'micro':>6} {'cryst':>6} {'tex':>5}"
    )
    lines.append(f"  {'-'*35} {'-'*8} {'-'*6} {'-'*8} {'-'*6} {'-'*6} {'-'*6} {'-'*5}")
    for r in top_ring:
        c = "Y" if r["name"] in crystalline_flagged else "-"
        t = "Y" if r["name"] in texture_flagged else "-"
        lines.append(
            f"  {r['name']:<35} {r['ringing_score']:>8.1f} {r['halo_score']:>6.1f} "
            f"{r['edge_sharpness']:>8.1f} {r['edge_contrast_inflation']:>6.1f} "
            f"{r['microtexture']:>6.1f} {c:>6} {t:>5}"
        )

    # --- Overlap with existing analyzers ---
    h("OVERLAP WITH EXISTING ANALYZERS")
    halo_top30 = {r["name"] for r in sorted(records, key=lambda r: r["halo_score"], reverse=True)[:30]}
    ring_top30 = {r["name"] for r in sorted(records, key=lambda r: r["ringing_score"], reverse=True)[:30]}
    union_top30 = halo_top30 | ring_top30

    lines.append(f"  Top-30 halo_score candidates:       {len(halo_top30)}")
    lines.append(f"  Top-30 ringing_score candidates:    {len(ring_top30)}")
    lines.append(f"  Union (halo OR ringing top-30):     {len(union_top30)}")
    lines.append(f"  Texture-flagged (TextureAnalyzer):  {len(texture_flagged)}")
    lines.append(f"  Crystalline-flagged:                {len(crystalline_flagged)}")
    lines.append("")
    lines.append(f"  Overlap halo_top30  AND texture:    {len(halo_top30 & texture_flagged)}")
    lines.append(f"  Overlap halo_top30  AND crystalline:{len(halo_top30 & crystalline_flagged)}")
    lines.append(f"  Overlap ring_top30  AND texture:    {len(ring_top30 & texture_flagged)}")
    lines.append(f"  Overlap ring_top30  AND crystalline:{len(ring_top30 & crystalline_flagged)}")
    overlap_new_only = union_top30 - texture_flagged - crystalline_flagged
    lines.append(f"  Candidates NOT flagged by either:   {len(overlap_new_only)}")
    lines.append("")
    if overlap_new_only:
        lines.append("  Images in union_top30 not caught by existing analyzers:")
        for name in sorted(overlap_new_only):
            r = next(x for x in records if x["name"] == name)
            lines.append(
                f"    {name:<35}  halo={r['halo_score']:.1f}  "
                f"ring={r['ringing_score']:.1f}  edge_sh={r['edge_sharpness']:.1f}"
            )

    # --- Correlation analysis ---
    h("SIGNAL CORRELATION (Pearson r with halo_score)")
    halo_vals = [r["halo_score"] for r in records]
    for m in ["ringing_score", "edge_sharpness", "laplacian_mean",
              "edge_hf_ratio", "edge_contrast_inflation",
              "microtexture", "pencil_grain", "watercolor_smooth"]:
        other = [r.get(m, r.get("watercolor_smooth", r.get("watercolor_smoothness", 0)))
                 for r in records]
        r_val = _pearson(halo_vals, other)
        lines.append(f"  halo_score vs {m:<30} r = {r_val:+.3f}")

    lines.append("")
    lines.append("Correlation with ringing_score:")
    ring_vals = [r["ringing_score"] for r in records]
    for m in ["halo_score", "edge_sharpness", "edge_hf_ratio",
              "edge_contrast_inflation", "microtexture", "pencil_grain"]:
        other = [r[m] for r in records]
        r_val = _pearson(ring_vals, other)
        lines.append(f"  ringing_score vs {m:<28} r = {r_val:+.3f}")

    # --- Per-image full table ---
    h("FULL PER-IMAGE TABLE (sorted by halo_score desc)")
    lines.append(
        f"  {'filename':<35} {'halo':>6} {'ring':>6} {'e_sh':>6} "
        f"{'lap_m':>6} {'e_hfr':>6} {'eci':>6} {'micro':>6} {'grain':>6} "
        f"{'cryst':>5} {'tex':>4}"
    )
    lines.append(
        f"  {'-'*35} {'-'*6} {'-'*6} {'-'*6} {'-'*6} "
        f"{'-'*6} {'-'*6} {'-'*6} {'-'*6} {'-'*5} {'-'*4}"
    )
    for r in sorted(records, key=lambda r: r["halo_score"], reverse=True):
        c = "Y" if r["name"] in crystalline_flagged else "-"
        t = "Y" if r["name"] in texture_flagged else "-"
        lines.append(
            f"  {r['name']:<35} {r['halo_score']:>6.1f} {r['ringing_score']:>6.1f} "
            f"{r['edge_sharpness']:>6.1f} {r['laplacian_mean']:>6.2f} "
            f"{r['edge_hf_ratio']:>6.3f} {r['edge_contrast_inflation']:>6.1f} "
            f"{r['microtexture']:>6.1f} {r['pencil_grain']:>6.1f} "
            f"{c:>5} {t:>4}"
        )

    out = OUT_DIR / "probe_oversharpening_report.txt"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  Saved {out.name}")


def _pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 2:
        return 0.0
    mx, my = statistics.mean(xs), statistics.mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dxs = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dys = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dxs < 1e-9 or dys < 1e-9:
        return 0.0
    return round(num / (dxs * dys), 4)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    print("=== Oversharpening / Halo Probe ===")
    print(f"Dataset: {DATASET}")
    print(f"Output:  {OUT_DIR}")
    print()

    records = _scan_dataset()
    if not records:
        print("ERROR: no records measured.")
        return 1

    texture_flagged, crystalline_flagged = _load_findings()

    # Save raw data
    json_path = OUT_DIR / "probe_oversharpening_data.json"
    json_path.write_text(json.dumps(records, indent=2), encoding="utf-8")
    print(f"  Saved {json_path.name}")

    # Compute global stats
    stats = {}

    # Contact sheets
    print("\nGenerating contact sheets...")

    top_halo = sorted(records, key=lambda r: r["halo_score"], reverse=True)
    _make_contact_sheet(
        top_halo, "Top 20: halo_score (perpendicular edge strip range)",
        "contact_sheet_top20_halo.png",
        lambda r: (
            f"halo={r['halo_score']:.1f}  ring={r['ringing_score']:.1f}  "
            f"esh={r['edge_sharpness']:.1f}"
        ),
    )

    top_ring = sorted(records, key=lambda r: r["ringing_score"], reverse=True)
    _make_contact_sheet(
        top_ring, "Top 20: ringing_score (Laplacian sign alternation near edges)",
        "contact_sheet_top20_ringing.png",
        lambda r: (
            f"ring={r['ringing_score']:.1f}  halo={r['halo_score']:.1f}  "
            f"esh={r['edge_sharpness']:.1f}"
        ),
    )

    # Clean reference: low halo AND low ringing AND low edge_sharpness
    def _clean_key(r):
        return r["halo_score"] + r["ringing_score"] + r["edge_sharpness"]
    clean_ref = sorted(records, key=_clean_key)
    _make_contact_sheet(
        clean_ref, "Clean reference: lowest combined halo+ringing+edge_sharpness",
        "contact_sheet_clean_reference.png",
        lambda r: (
            f"halo={r['halo_score']:.1f}  ring={r['ringing_score']:.1f}  "
            f"esh={r['edge_sharpness']:.1f}"
        ),
    )

    # Co-detected: high halo AND crystalline flagged
    co_detected = [
        r for r in top_halo if r["name"] in crystalline_flagged
    ]
    _make_contact_sheet(
        co_detected,
        "Co-detected: high halo_score AND crystalline_faceting flagged",
        "contact_sheet_vs_crystalline.png",
        lambda r: (
            f"halo={r['halo_score']:.1f}  grain={r['pencil_grain']:.1f}  "
            f"cryst=Y"
        ),
    )

    # Texture-only high-halo: flagged by TextureAnalyzer but not crystalline
    tex_only_halo = [
        r for r in top_halo if r["name"] in texture_flagged and r["name"] not in crystalline_flagged
    ]
    _make_contact_sheet(
        tex_only_halo[:20],
        "High halo_score + texture finding only (not crystalline)",
        "contact_sheet_texture_only_halo.png",
        lambda r: (
            f"halo={r['halo_score']:.1f}  micro={r['microtexture']:.1f}  tex=Y"
        ),
    )

    print("\nWriting report...")
    _write_report(records, texture_flagged, crystalline_flagged, stats)

    print("\nDone. Results in:", OUT_DIR)
    return 0


if __name__ == "__main__":
    sys.exit(main())
