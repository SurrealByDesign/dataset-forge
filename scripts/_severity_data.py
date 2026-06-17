"""
Dump the full crystalline-flagged population with reviewer verdicts.
Used to explore severity model boundaries.
"""
import json, statistics
from pathlib import Path

DATASET = Path("C:/Users/someo/Desktop/ANTHROPOMORPHS")
reviews  = json.loads((DATASET / "decision_review.json").read_text("utf-8"))["reviews"]
findings = json.loads((DATASET / "inspect_output/inspection_report.json").read_text("utf-8"))["findings"]

texture     = set()
crystalline = {}
for f in findings:
    name = Path(f["image_path"]).name
    cat  = f.get("category", "")
    if cat == "texture.high_microtexture":
        texture.add(name)
    if cat == "artifact.crystalline_faceting":
        crystalline[name] = f.get("evidence", {})

rows = []
for name, rv in reviews.items():
    if name not in crystalline:
        continue
    ev = crystalline[name]
    rows.append({
        "name":     name,
        "grain":    ev.get("pencil_grain_score", 0.0),
        "smooth":   ev.get("watercolor_smoothness_score", 0.0),
        "micro":    ev.get("microtexture_density_score", 0.0),
        "verdict":  rv.get("review", ""),
        "texture":  name in texture,
    })

rows.sort(key=lambda x: x["grain"], reverse=True)

print(f"{'#':<3} {'verdict':<9} {'tex':>3} {'grain':>6} {'smooth':>7} {'micro':>6}  name")
print("-"*90)
for i, r in enumerate(rows, 1):
    tex = "Y" if r["texture"] else "N"
    print(f"{i:<3} {r['verdict']:<9} {tex:>3} {r['grain']:>6.1f} {r['smooth']:>7.1f} "
          f"{r['micro']:>6.1f}  {r['name']}")

print()
print("GRAIN TIER BREAKDOWN  (all 54 crystalline-flagged images):")
tiers = [
    ("45-49", 45, 50),
    ("50-54", 50, 55),
    ("55-59", 55, 60),
    ("60-64", 60, 65),
    ("65+",   65, 999),
]
for label, lo, hi in tiers:
    grp = [r for r in rows if lo <= r["grain"] < hi]
    if not grp:
        continue
    agree    = sum(1 for r in grp if r["verdict"] == "AGREE")
    disagree = sum(1 for r in grp if r["verdict"] == "DISAGREE")
    unsure   = sum(1 for r in grp if r["verdict"] == "UNSURE")
    # for non-texture-co-detections: reviewer AGREE means FP, DISAGREE means TP
    tp_cryst = sum(1 for r in grp if r["verdict"] == "DISAGREE" and not r["texture"])
    fp_cryst = sum(1 for r in grp if r["verdict"] == "AGREE" and not r["texture"])
    print(f"  grain {label:>6}: n={len(grp):2d}  AGREE={agree:2d} DISAG={disagree:2d} "
          f"UNSURE={unsure}  | cryst-only TP={tp_cryst} FP={fp_cryst}")
