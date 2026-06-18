"""Generate semi-synthetic crystalline faceting benchmark fixtures.

Produces three deterministic PNG images committed as public benchmark fixtures
for CrystallineFacetingAnalyzer. Re-running this script reproduces the same
pixel values (no random seed needed -- crosshatch is fully deterministic).

Usage:
    uv run python scripts/generate_crystalline_fixtures.py
    uv run python scripts/generate_crystalline_fixtures.py --output path/to/dir

Images written to benchmarks/synthetic_defects/ (or --output):
    06_crystalline_low.png
        crosshatch spacing=4 amplitude=15
        Expected: grain ~45, smooth <52, micro >20
        CrystallineFacetingAnalyzer fires with LOW severity
        Purpose: threshold boundary -- minimal signal that triggers detection

    07_crystalline_medium.png
        crosshatch spacing=6 amplitude=30
        Expected: grain ~64, smooth ~37, micro ~66
        CrystallineFacetingAnalyzer fires with MEDIUM severity
        Purpose: strong synthetic match to real calibration images (grain ~62)

    08_crystalline_negative_smooth.png
        crosshatch spacing=12 amplitude=30
        Expected: grain ~62, smooth ~53 (ABOVE ceiling 52), micro ~43
        CrystallineFacetingAnalyzer does NOT fire (smoothness guard blocks it)
        Purpose: validates the watercolor_smoothness < 52 guard

Design rationale:
    pencil_grain = 0.58 * saturating(band_pass_mean, cap=6) + 0.42 * consistency
    - band_pass = |blur_sigma1.0 - blur_sigma2.4|  (1-2.4 px mid-frequency band)
    - consistency = 100 * exp(-stddev(block_means) / mean(block_means))
    Crosshatch lines at 45deg + 135deg produce uniform fine-scale energy
    (both terms rise together). Voronoi/random patterns fail because
    consistency is low (energy clusters near edges, not distributed uniformly).

Probe script: scripts/_probe_crystalline_synthetic.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))

from dataset_forge.analysis.texture import evaluate_texture
from dataset_forge.analyzers.crystalline import (
    CrystallineFacetingAnalyzer,
    _GRAIN_THRESHOLD,
    _SMOOTHNESS_CEILING,
    _MICRO_FLOOR,
)
from dataset_forge.context import (
    CONTEXT_SCHEMA_VERSION,
    AspectRatioStats,
    DatasetContext,
    FrequencyDistributions,
    ResolutionStats,
    TextureDistributions,
)

SIZE = 256
BASE_GREY = 128
_ANALYZER = CrystallineFacetingAnalyzer()
_CONTEXT = DatasetContext(
    schema_version=CONTEXT_SCHEMA_VERSION,
    analyzer_versions={},
    image_paths=(),
    image_count=1,
    error_count=0,
    resolution_stats=ResolutionStats.empty(),
    aspect_ratio_stats=AspectRatioStats.empty(),
    texture_distributions=TextureDistributions(
        mean=25.0, stddev=5.0, p10=18.0, p90=33.0, sample_count=10
    ),
    frequency_distributions=FrequencyDistributions.empty(),
    duplicate_hashes=frozenset(),
    duplicate_groups=(),
)


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

def _diagonal_crosshatch(
    size: int = SIZE,
    spacing: int = 4,
    amplitude: int = 15,
    base_grey: int = BASE_GREY,
) -> np.ndarray:
    """Uniform angular crosshatch at 45deg and 135deg.

    Fully deterministic: same (size, spacing, amplitude, base_grey) always
    produces the same pixel array. Lines are 1 pixel wide.
    """
    canvas = np.full((size, size), base_grey, dtype=np.int32)
    # 45-degree lines: y - x = k  (every `spacing` steps along the diagonal)
    for k in range(-size, size + size, spacing):
        for x in range(size):
            y = x + k
            if 0 <= y < size:
                canvas[y, x] -= amplitude
    # 135-degree lines: y + x = k
    for k in range(0, size * 2, spacing):
        for x in range(size):
            y = k - x
            if 0 <= y < size:
                canvas[y, x] -= amplitude
    arr = np.clip(canvas, 0, 255).astype(np.uint8)
    # Save as RGB so fixtures look like real images in viewers
    return np.stack([arr, arr, arr], axis=2)


# ---------------------------------------------------------------------------
# Fixture definitions
# ---------------------------------------------------------------------------

FIXTURES = [
    {
        "filename": "06_crystalline_low.png",
        "spacing": 4,
        "amplitude": 15,
        "description": "LOW severity crystalline fixture. Spacing=4 amplitude=15.",
    },
    {
        "filename": "07_crystalline_medium.png",
        "spacing": 6,
        "amplitude": 30,
        "description": "MEDIUM severity crystalline fixture. Spacing=6 amplitude=30.",
    },
    {
        "filename": "08_crystalline_negative_smooth.png",
        "spacing": 12,
        "amplitude": 30,
        "description": "Crystalline-negative fixture (smoothness guard). Spacing=12 amplitude=30.",
    },
]


def generate(output_dir: Path) -> list[dict]:
    """Generate all fixtures and return their measured scores."""
    output_dir.mkdir(parents=True, exist_ok=True)
    results = []

    for spec in FIXTURES:
        path = output_dir / spec["filename"]
        arr = _diagonal_crosshatch(spacing=spec["spacing"], amplitude=spec["amplitude"])
        Image.fromarray(arr).save(path)

        r = evaluate_texture(path)
        if r.status != "analyzed":
            raise RuntimeError(f"evaluate_texture failed on {path}: {r.error}")

        findings = _ANALYZER.analyze(path, _CONTEXT)
        cryst = [f for f in findings if f.category == "artifact.crystalline_faceting"]
        fires = len(cryst) > 0
        severity = cryst[0].severity.name if fires else "NONE"

        results.append({
            "filename": spec["filename"],
            "path": path,
            "spacing": spec["spacing"],
            "amplitude": spec["amplitude"],
            "grain": r.pencil_grain_score,
            "smooth": r.watercolor_smoothness_score,
            "micro": r.microtexture_density_score,
            "fires": fires,
            "severity": severity,
        })

    return results


def _print_results(results: list[dict]) -> None:
    W = max(len(r["filename"]) for r in results)
    print()
    print(f"{'filename':<{W}}  {'grain':>6}  {'smooth':>6}  {'micro':>5}  {'fires':>5}  severity")
    print("-" * (W + 40))
    for r in results:
        fire_str = "YES" if r["fires"] else "no"
        print(
            f"{r['filename']:<{W}}  {r['grain']:>6.1f}  {r['smooth']:>6.1f}"
            f"  {r['micro']:>5.1f}  {fire_str:>5}  {r['severity']}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate crystalline faceting benchmark fixtures."
    )
    parser.add_argument(
        "--output",
        default="benchmarks/synthetic_defects",
        help="Output directory (default: benchmarks/synthetic_defects/)",
    )
    args = parser.parse_args()

    output_dir = Path(args.output)
    if not output_dir.is_absolute():
        output_dir = _ROOT / output_dir

    print(f"Generating crystalline fixtures in {output_dir} ...")
    results = generate(output_dir)
    _print_results(results)

    # Validation
    print()
    for r in results:
        grain_ok = r["grain"] >= _GRAIN_THRESHOLD
        smooth_ok = r["smooth"] < _SMOOTHNESS_CEILING
        micro_ok = r["micro"] >= _MICRO_FLOOR
        all_guards = grain_ok and smooth_ok and micro_ok
        if r["filename"] == "08_crystalline_negative_smooth.png":
            if r["fires"]:
                print(f"WARNING: {r['filename']} fired but should be blocked by smoothness guard")
            else:
                print(f"OK  {r['filename']}: blocked by smoothness guard (smooth={r['smooth']:.1f} >= {_SMOOTHNESS_CEILING})")
        else:
            if r["fires"]:
                print(f"OK  {r['filename']}: fires with {r['severity']} (grain={r['grain']:.1f})")
            else:
                print(f"WARNING: {r['filename']} did not fire (grain={r['grain']:.1f}, smooth={r['smooth']:.1f}, micro={r['micro']:.1f})")

    print()
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
