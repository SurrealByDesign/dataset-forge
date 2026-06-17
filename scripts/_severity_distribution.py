"""
Verify severity distribution on the anthropomorph dataset under the new model.
Compares old (all-MEDIUM) vs new (grain-tiered) severity assignment.
"""
import json
from pathlib import Path

DATASET = Path("C:/Users/someo/Desktop/ANTHROPOMORPHS")
findings = json.loads(
    (DATASET / "inspect_output/inspection_report.json").read_text("utf-8")
)["findings"]

# Only crystalline_faceting findings (not error, not texture)
cryst = [
    f for f in findings
    if f.get("category") == "artifact.crystalline_faceting"
]

from dataset_forge.analyzers.crystalline import (
    _SEVERITY_MEDIUM_GRAIN, _SEVERITY_HIGH_GRAIN,
)

def new_sev(grain):
    if grain >= _SEVERITY_HIGH_GRAIN:   return "HIGH"
    if grain >= _SEVERITY_MEDIUM_GRAIN: return "MEDIUM"
    return "LOW"

rows = []
for f in cryst:
    grain = f["evidence"]["pencil_grain_score"]
    rows.append({
        "name": Path(f["image_path"]).name,
        "grain": grain,
        "old": "MEDIUM",
        "new": new_sev(grain),
    })
rows.sort(key=lambda x: x["grain"], reverse=True)

print(f"\n{'#':>2}  {'old':>6}  {'new':>6}  {'grain':>6}  name")
print("-" * 72)
for i, r in enumerate(rows, 1):
    changed = " *" if r["new"] != r["old"] else ""
    print(f"{i:>2}  {r['old']:>6}  {r['new']:>6}  {r['grain']:>6.1f}  {r['name']}{changed}")

print()
old_counts = {"HIGH": 0, "MEDIUM": 54, "LOW": 0}
new_counts  = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
for r in rows:
    new_counts[r["new"]] += 1

print(f"Total crystalline findings: {len(rows)}")
print(f"Old:  LOW={old_counts['LOW']}  MEDIUM={old_counts['MEDIUM']}  HIGH={old_counts['HIGH']}")
print(f"New:  LOW={new_counts['LOW']}  MEDIUM={new_counts['MEDIUM']}  HIGH={new_counts['HIGH']}")
print(f"Changed: {sum(1 for r in rows if r['new'] != r['old'])}")
