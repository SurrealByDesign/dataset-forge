"""Probe existing synthetic assets to measure actual analyzer scores."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dataset_forge.analysis.texture import evaluate_texture

SYNTH = Path("D:/dataset-forge/benchmarks/synthetic_defects")
REAL  = Path("D:/dataset-forge/benchmarks/real_samples")

images = sorted(SYNTH.glob("*.png")) + sorted(REAL.glob("*.jpg"))
if not images:
    print("No images found.")
    raise SystemExit(1)

print(f"{'name':<45} {'micro':>6} {'grain':>6} {'smooth':>7} {'speck':>6} {'sharp':>6}")
print("-" * 80)
for p in images:
    r = evaluate_texture(p)
    if r.status == "error":
        print(f"{p.name:<45}  ERROR: {r.error}")
        continue
    print(f"{p.name:<45} {r.microtexture_density_score:>6.1f} {r.pencil_grain_score:>6.1f} "
          f"{r.watercolor_smoothness_score:>7.1f} {r.highlight_speck_score:>6.1f} "
          f"{r.edge_sharpness_score:>6.1f}")
