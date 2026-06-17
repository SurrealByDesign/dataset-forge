import json, statistics
from pathlib import Path

DATASET = Path("C:/Users/someo/Desktop/ANTHROPOMORPHS")
review  = json.loads((DATASET / "decision_review.json").read_text("utf-8"))["reviews"]
report  = json.loads((DATASET / "inspect_output/inspection_report.json").read_text("utf-8"))

texture     = set()
crystalline = {}
for f in report["findings"]:
    name = Path(f["image_path"]).name
    cat  = f.get("category", "")
    if cat == "texture.high_microtexture":
        texture.add(name)
    if cat == "artifact.crystalline_faceting":
        crystalline[name] = f.get("evidence", {})

fps = []
for name, rv in review.items():
    if rv.get("review") == "AGREE" and name in crystalline and name not in texture:
        ev = crystalline[name]
        fps.append({
            "name": name,
            "grain":  ev.get("pencil_grain_score", 0),
            "smooth": ev.get("watercolor_smoothness_score", 0),
            "micro":  ev.get("microtexture_density_score", 0),
        })

fps.sort(key=lambda x: x["grain"], reverse=True)
print(f"Count: {len(fps)}")
print()
print(f"{'name':<55} {'grain':>6} {'smooth':>7} {'micro':>6}")
print("-" * 78)
for r in fps:
    print(f"{r['name']:<55} {r['grain']:>6.1f} {r['smooth']:>7.1f} {r['micro']:>6.1f}")

grains  = [r["grain"]  for r in fps]
smooths = [r["smooth"] for r in fps]
micros  = [r["micro"]  for r in fps]
print()
print(f"grain  -- min={min(grains):.1f}  max={max(grains):.1f}  mean={statistics.mean(grains):.1f}  stdev={statistics.stdev(grains):.1f}")
print(f"smooth -- min={min(smooths):.1f}  max={max(smooths):.1f}  mean={statistics.mean(smooths):.1f}  stdev={statistics.stdev(smooths):.1f}")
print(f"micro  -- min={min(micros):.1f}  max={max(micros):.1f}  mean={statistics.mean(micros):.1f}  stdev={statistics.stdev(micros):.1f}")
