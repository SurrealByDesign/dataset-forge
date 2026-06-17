"""
Characterize the 24 crystalline false positives.

Reads decision_review.json + inspection_report.json.
Produces:
  1. Contact sheet PNG (24 images, sorted by pencil_grain descending)
  2. Ranked metrics table
  3. Cluster analysis
  4. Recommendation

Read-only analysis. No production code changes.
"""

from __future__ import annotations

import json
import math
import statistics
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("PIL not available -- install Pillow to generate contact sheet.")
    Image = None

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

DATASET = Path("C:/Users/someo/Desktop/ANTHROPOMORPHS")
REVIEW  = DATASET / "decision_review.json"
REPORT  = DATASET / "inspect_output/inspection_report.json"
OUT_DIR = DATASET / "inspect_output"
OUT_DIR.mkdir(exist_ok=True)

BAR  = "-" * 80
BAR2 = "=" * 80

# ---------------------------------------------------------------------------
# 1. Load data and identify the 24 FP images
# ---------------------------------------------------------------------------

reviews  = json.loads(REVIEW.read_text("utf-8"))["reviews"]
findings = json.loads(REPORT.read_text("utf-8"))["findings"]

texture     = set()
crystalline = {}   # name -> evidence dict
for f in findings:
    name = Path(f["image_path"]).name
    cat  = f.get("category", "")
    if cat == "texture.high_microtexture":
        texture.add(name)
    if cat == "artifact.crystalline_faceting":
        crystalline[name] = f.get("evidence", {})

fps = []
for name, rv in reviews.items():
    if rv.get("review") == "AGREE" and name in crystalline and name not in texture:
        ev = crystalline[name]
        fps.append({
            "name":   name,
            "grain":  ev.get("pencil_grain_score", 0.0),
            "smooth": ev.get("watercolor_smoothness_score", 0.0),
            "micro":  ev.get("microtexture_density_score", 0.0),
            "path":   DATASET / name,
        })

fps.sort(key=lambda x: x["grain"], reverse=True)
assert len(fps) == 24, f"Expected 24 FP images, got {len(fps)}"


# ---------------------------------------------------------------------------
# 2. Cluster assignment
#
# Based on grain/smooth distribution:
#
#   Cluster A -- "Strong signal, probably detectable artifact"
#     grain >= 55 -- well above threshold; high confidence the signal is real
#
#   Cluster B -- "Borderline faceting or style-induced"
#     grain 50-55, smooth < 45 -- significant signal, but smoothness suggests
#     artistic texture (hatching, fur, scale) rather than flat-facet shading
#
#   Cluster C -- "Threshold fringe"
#     grain 45-50 OR (50-55 AND smooth >= 45) -- just over threshold;
#     small threshold change would remove these
#
#   Cluster D -- "Possible different texture family"
#     very low smooth (< 38) regardless of grain -- the watercolor_smoothness
#     signal is so low that the image may belong to a different texture type
#     (e.g., heavy crosshatch, porcupine spine density, dense scale texture)
#     -- these may be a second artifact family partially captured
# ---------------------------------------------------------------------------

def assign_cluster(r: dict) -> tuple[str, str]:
    grain, smooth = r["grain"], r["smooth"]
    # D first -- extreme smoothness outliers are a distinct pattern
    if smooth < 38:
        return "D", "Extreme low-smooth outlier -- possible alt texture family"
    if grain >= 60:
        return "A", "Very strong grain signal (>=60) -- likely real artifact"
    if grain >= 55:
        return "A", "Strong grain signal (55-60) -- probably real artifact"
    if grain >= 50 and smooth < 45:
        return "B", "Moderate grain, very low smoothness -- style or alt family"
    if grain >= 50:
        return "C", "Moderate grain, moderate smoothness -- threshold fringe"
    # grain 45-50
    return "C", "Near-threshold grain (45-50) -- threshold fringe"

for r in fps:
    r["cluster"], r["cluster_note"] = assign_cluster(r)


# ---------------------------------------------------------------------------
# 3. Print ranking table
# ---------------------------------------------------------------------------

print()
print(BAR2)
print("  Crystalline False Positive Characterization")
print("  24 images: crystalline flagged, reviewer AGREE (DF correctly clean)")
print(BAR2)

print(f"\n{'#':<3} {'name':<55} {'grain':>6} {'smooth':>7} {'micro':>6}  {'cl':>2}")
print(BAR)
for i, r in enumerate(fps, 1):
    print(f"{i:<3} {r['name']:<55} {r['grain']:>6.1f} {r['smooth']:>7.1f} "
          f"{r['micro']:>6.1f}  {r['cluster']:>2}")


# ---------------------------------------------------------------------------
# 4. Cluster breakdown
# ---------------------------------------------------------------------------

clusters = {"A": [], "B": [], "C": [], "D": []}
for r in fps:
    clusters[r["cluster"]].append(r)

print()
print(BAR)
print("  CLUSTER SUMMARY")
print(BAR)

cluster_defs = {
    "A": ("Strong grain signal (grain >= 55)", "Real artifact, severity disagreement"),
    "B": ("Moderate grain, very low smoothness (smooth < 45)", "Style-induced or alt texture family"),
    "C": ("Near-threshold grain (45-55, smooth >= 45)", "Threshold fringe -- lift grain threshold"),
    "D": ("Extreme low-smoothness outlier (smooth < 38)", "Different texture family captured"),
}

for cl, (desc, hypothesis) in cluster_defs.items():
    group = clusters[cl]
    if not group:
        continue
    grains  = [r["grain"]  for r in group]
    smooths = [r["smooth"] for r in group]
    micros  = [r["micro"]  for r in group]
    print(f"""
  Cluster {cl}: {desc}
  Count  : {len(group)}
  Hypothesis: {hypothesis}
  grain  : {min(grains):.1f} - {max(grains):.1f}  (mean {statistics.mean(grains):.1f})
  smooth : {min(smooths):.1f} - {max(smooths):.1f}  (mean {statistics.mean(smooths):.1f})
  micro  : {min(micros):.1f} - {max(micros):.1f}  (mean {statistics.mean(micros):.1f})
  Images :""")
    for r in sorted(group, key=lambda x: x["grain"], reverse=True):
        print(f"    grain={r['grain']:.1f}  smooth={r['smooth']:.1f}  micro={r['micro']:.1f}  {r['name']}")


# ---------------------------------------------------------------------------
# 5. Threshold impact analysis
# ---------------------------------------------------------------------------

print()
print(BAR)
print("  THRESHOLD IMPACT ANALYSIS")
print(BAR)
print()

thresholds = [46, 48, 50, 52, 55, 58, 60]
for t in thresholds:
    removed   = [r for r in fps if r["grain"] < t]
    remaining = [r for r in fps if r["grain"] >= t]
    print(f"  grain >= {t:2d}  -->  removes {len(removed):2d} FP  ({len(remaining):2d} FP remain)")

print()
print("  NOTE: Threshold lift must be evaluated against TP recall impact.")
print("  Currently 11 TP images are caught by crystalline-only. Their grain")
print("  values must be checked before any threshold is changed.")
print()

# Show TP images for reference
tps_only = []
for name, rv in reviews.items():
    if rv.get("review") == "DISAGREE" and name in crystalline and name not in texture:
        ev = crystalline[name]
        tps_only.append({
            "name":   name,
            "grain":  ev.get("pencil_grain_score", 0.0),
            "smooth": ev.get("watercolor_smoothness_score", 0.0),
            "micro":  ev.get("microtexture_density_score", 0.0),
        })
tps_only.sort(key=lambda x: x["grain"])

print(f"  {'TP name':<55} {'grain':>6} {'smooth':>7} {'micro':>6}")
print("  " + "-" * 76)
for r in tps_only:
    print(f"  {r['name']:<55} {r['grain']:>6.1f} {r['smooth']:>7.1f} {r['micro']:>6.1f}")

print()
tp_grains = [r["grain"] for r in tps_only]
print(f"  TP grain range: {min(tp_grains):.1f} - {max(tp_grains):.1f}  (min TP grain determines safe threshold ceiling)")

for t in thresholds:
    tps_lost = sum(1 for g in tp_grains if g < t)
    fps_removed = sum(1 for r in fps if r["grain"] < t)
    print(f"  grain >= {t:2d}  -->  loses {tps_lost} TP,  removes {fps_removed} FP")

print()
tp_grains_sorted = sorted(tp_grains)
print(f"  Min TP grain = {min(tp_grains):.2f}  Max TP grain = {max(tp_grains):.2f}")
print(f"  Min FP grain = {min(r['grain'] for r in fps):.2f}  Max FP grain = {max(r['grain'] for r in fps):.2f}")
print()
print("  INTERLEAVE ANALYSIS (grain range 45-60):")
thresholds_fine = [46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 58, 60]
for t in thresholds_fine:
    tps_lost = sum(1 for g in tp_grains if g < t)
    fps_removed = sum(1 for r in fps if r["grain"] < t)
    tp_keep = len(tp_grains) - tps_lost
    fp_keep = len(fps) - fps_removed
    prec = tp_keep / (tp_keep + fp_keep) if (tp_keep + fp_keep) else 0
    recall = tp_keep / 13
    print(f"  grain>={t:2d}: loses {tps_lost} TP, removes {fps_removed:2d} FP | "
          f"recall={recall:.0%} cryst-only-prec={tp_keep}/{tp_keep+fp_keep}={prec:.0%}")
print()
print("  CONCLUSION: TP and FP populations interleave. No threshold lift is safe.")
print("  Precision barely changes while recall falls sharply. Threshold adjustment")
print("  is not the solution. A fourth discriminating signal is required.")
# Keep safe_ceil for backward compat with recommendation section
safe_ceil = min(tp_grains)
fps_at_safe = sum(1 for r in fps if r["grain"] < int(safe_ceil))


# ---------------------------------------------------------------------------
# 6. Recommendation
# ---------------------------------------------------------------------------

print()
print(BAR)
print("  RECOMMENDATION")
print(BAR)

n_a = len(clusters["A"])
n_b = len(clusters["B"])
n_c = len(clusters["C"])
n_d = len(clusters["D"])

print(f"""
  The 24 FP images split across four distinct patterns:

  KEY FINDING: Threshold adjustment cannot solve this problem.
    TP and FP grain values are DEEPLY INTERLEAVED in the 45-55 range:
      FP grain: 45.3 - 64.7 (18 of 24 FPs fall in grain 45-55)
      TP grain: 45.96 - 67.6 (8 of 11 TPs fall in grain 45-55)
    No threshold lift produces a meaningful precision gain without severe recall loss.
    At any integer threshold:
      grain>=46: loses 1 TP, removes only 3 FP  (precision 32.3%, recall 76.9%)
      grain>=52: loses 6 TP, removes 12 FP       (precision 29.4%, recall 38.5%)
      grain>=55: loses 8 TP, removes 18 FP       (precision 33.3%, recall 23.1%)
    Threshold adjustment is counterproductive. Do not raise the threshold.

  Cluster C ({n_c} images) -- SIGNAL GAP (not a threshold issue)
    These images sit in the grain 45-55 range with moderate smoothness.
    The problem is that 8 confirmed TPs (actual missed artifacts) also sit
    in grain 45-55 with similar smoothness. The three signals (grain, smooth,
    micro) have no discriminating power in this overlap zone.
    A FOURTH SIGNAL is required to separate these. Candidates:
    (a) Spatial coherence: crystalline faceting produces spatially coherent
        polygon-shaped patches; clean fine texture is spatially incoherent.
        Measurable via local orientation histogram or patch regularity.
    (b) Frequency-domain directionality: faceting produces directional mid-
        frequency energy; random micro-texture does not.
    (c) Edge profile: polygon faceting creates hard micro-edges; natural
        grain creates soft micro-edges. Local edge sharpness distribution
        may discriminate.

  Cluster A ({n_a} images) -- SEVERITY ISSUE
    These have grain >= 55, strongly above threshold. The signal is real.
    But the reviewer called them clean. This is a severity disagreement:
    the faceting exists at a level the reviewer considers within-range for
    this watercolor/pencil style. The finding is not wrong; the MEDIUM
    severity label overstates the urgency. These should be LOW severity.

  Cluster B ({n_b} images) -- SEVERITY ISSUE (borderline)
    Moderate grain (51-52), very low smoothness (41-43). Probably genuine
    light faceting that the reviewer tolerates. Same conclusion as Cluster A:
    correct finding, overstated severity.

  Cluster D ({n_d} images) -- FAMILY DEFINITION ISSUE
    Anomalously low watercolor_smoothness (<34) combined with very high micro
    (48-50) and moderate-high grain (53-55). The extremely low smoothness
    suggests dense, high-frequency, non-faceted subject texture: porcupine
    spines (witchkingporcupine.jpg), scale/wetsuit texture (cthulhudiver.jpg).
    These images are NOT faceted in the crystalline polygon sense. They are
    captured because the three-signal rule overlaps with dense subject texture.
    A smoothness floor would not help -- confirmed TPs include images with
    similarly low smoothness (mouse-king-nutcracker: smooth=37.5, bananapunk: 39.1).
    These require:
    (a) A subject-texture signal to distinguish dense-regular vs faceted-surface, OR
    (b) A separate artifact family definition with its own detection rule.

  SUMMARY OF ISSUES:
    Signal gap (no threshold fix) : {n_c} images (Cluster C) -- fourth signal needed
    Severity overstatement        : {n_a + n_b} images (Clusters A+B) -- LOW not MEDIUM
    Family definition mismatch    : {n_d} images (Cluster D) -- dense texture =/= faceting

  RECOMMENDED ACTIONS (in order of priority):
    1. Do NOT raise the grain threshold. The populations interleave.
       Any threshold lift trades recall for no meaningful precision gain.
    2. Design a fourth discriminating signal (spatial coherence, directional
       frequency content, or micro-edge profile) targeting Cluster C.
       This is the primary unblocking step for the 15-image FP group.
    3. Consider a severity split: grain 45-55 with clean smoothness
       emits LOW severity; grain >= 55 emits MEDIUM severity.
       This correctly characterizes Clusters A and B as tolerable faceting
       rather than suppressing the finding entirely.
    4. Investigate Cluster D (cthulhudiver, witchkingporcupine) visually.
       If these are subject-texture FPs, define an exclusion rule based on
       micro-texture density combined with subject-pattern regularity.
""")


# ---------------------------------------------------------------------------
# 7. Contact sheet
# ---------------------------------------------------------------------------

if Image is None:
    print("  [Contact sheet skipped -- PIL not available]")
    print()
    print(BAR2)
    print()
    sys.exit(0)

print(BAR)
print("  GENERATING CONTACT SHEET")
print(BAR)

THUMB_W, THUMB_H = 300, 300
HEADER_H = 60
COLS = 6
ROWS = math.ceil(len(fps) / COLS)
PAD  = 6
BG   = (30, 30, 30)
HEADER_BG = (20, 20, 20)

# Cluster colors (border)
CLUSTER_COLORS = {
    "A": (220, 80,  80),   # red-ish
    "B": (220, 160, 60),   # amber
    "C": (80,  140, 220),  # blue
    "D": (160, 80,  220),  # purple
}

sheet_w = COLS * (THUMB_W + PAD) + PAD
sheet_h = ROWS * (THUMB_H + HEADER_H + PAD) + PAD + 80  # legend at bottom

sheet = Image.new("RGB", (sheet_w, sheet_h), BG)
draw  = ImageDraw.Draw(sheet)

try:
    font_sm = ImageFont.truetype("C:/Windows/Fonts/consola.ttf", 12)
    font_lg = ImageFont.truetype("C:/Windows/Fonts/consola.ttf", 14)
    font_ti = ImageFont.truetype("C:/Windows/Fonts/consolab.ttf", 16)
except Exception:
    font_sm = ImageFont.load_default()
    font_lg = font_sm
    font_ti = font_sm

def place(idx: int, r: dict):
    col  = idx % COLS
    row  = idx // COLS
    x0   = PAD + col * (THUMB_W + PAD)
    y0   = PAD + row * (THUMB_H + HEADER_H + PAD)

    color = CLUSTER_COLORS[r["cluster"]]
    # Border
    draw.rectangle([x0-2, y0-2, x0+THUMB_W+1, y0+THUMB_H+HEADER_H+1], outline=color, width=3)

    # Header
    draw.rectangle([x0, y0, x0+THUMB_W, y0+HEADER_H], fill=HEADER_BG)
    short = r["name"] if len(r["name"]) <= 28 else r["name"][:25] + "..."
    draw.text((x0+4, y0+4),  f"{idx+1:02d}. {short}", font=font_sm, fill=(220, 220, 220))
    draw.text((x0+4, y0+18), f"gr={r['grain']:.1f}  sm={r['smooth']:.1f}  mi={r['micro']:.1f}",
              font=font_sm, fill=(180, 220, 180))
    draw.text((x0+4, y0+34), f"Cluster {r['cluster']}: {r['cluster_note'][:35]}",
              font=font_sm, fill=color)

    # Thumbnail
    img_y = y0 + HEADER_H
    try:
        img = Image.open(r["path"]).convert("RGB")
        img.thumbnail((THUMB_W, THUMB_H))
        paste_x = x0 + (THUMB_W - img.width) // 2
        paste_y = img_y + (THUMB_H - img.height) // 2
        sheet.paste(img, (paste_x, paste_y))
    except Exception as e:
        draw.rectangle([x0, img_y, x0+THUMB_W, img_y+THUMB_H], fill=(60, 40, 40))
        draw.text((x0+8, img_y+THUMB_H//2), f"[{e}]", font=font_sm, fill=(200, 80, 80))

for i, r in enumerate(fps):
    place(i, r)

# Legend
legend_y = sheet_h - 75
draw.rectangle([PAD, legend_y, sheet_w-PAD, sheet_h-PAD], fill=HEADER_BG)
draw.text((PAD+8, legend_y+6),  "LEGEND:", font=font_ti, fill=(240, 240, 240))
draw.text((PAD+8, legend_y+26), "  Cluster A (red)    -- Strong grain signal (>=55): real artifact, severity disagreement", font=font_sm, fill=CLUSTER_COLORS["A"])
draw.text((PAD+8, legend_y+40), "  Cluster B (amber)  -- Moderate grain, low smooth: borderline / style-induced", font=font_sm, fill=CLUSTER_COLORS["B"])
draw.text((PAD+8, legend_y+54), "  Cluster C (blue)   -- Near-threshold grain (45-55, sm>=45): threshold fringe", font=font_sm, fill=CLUSTER_COLORS["C"])
draw.text((PAD+430, legend_y+40), "  Cluster D (purple) -- Extreme low-smooth (<38): possible alt texture family", font=font_sm, fill=CLUSTER_COLORS["D"])

out_path = OUT_DIR / "crystalline_fp_characterization.png"
sheet.save(out_path)
print(f"\n  Contact sheet written to:\n  {out_path}")
print()
print(BAR2)
print()
