"""Probe: can semi-synthetic images trigger CrystallineFacetingAnalyzer?

Tests five image families across a range of parameters. Saves probe images
to benchmarks/results/probe_crystalline/ (gitignored). Prints a score table
and a summary of which configurations cross all three detection thresholds.

Run with:
    uv run python scripts/_probe_crystalline_synthetic.py

No benchmark manifests are modified. No fixtures are committed.
"""

from __future__ import annotations

import math
import sys
import tempfile
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
    _SEVERITY_MEDIUM_GRAIN,
    _SEVERITY_HIGH_GRAIN,
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
RNG = np.random.default_rng(42)

# Output directory (gitignored under benchmarks/results/)
OUT_DIR = _ROOT / "benchmarks" / "results" / "probe_crystalline"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Minimal DatasetContext (crystalline analyzer doesn't use it, but API needs it)
# ---------------------------------------------------------------------------

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

_ANALYZER = CrystallineFacetingAnalyzer()


# ---------------------------------------------------------------------------
# Image generators
# ---------------------------------------------------------------------------

def _flat_grey() -> np.ndarray:
    """Baseline: solid grey 256x256. Should score near zero on all signals."""
    return np.full((SIZE, SIZE), BASE_GREY, dtype=np.uint8)


def _diagonal_crosshatch(spacing: int, amplitude: int) -> np.ndarray:
    """Uniform angular crosshatch at 45 deg and 135 deg.

    Lines are 1 pixel wide, spaced every `spacing` pixels along both diagonals.
    This is the main candidate for triggering pencil_grain:
    - band_pass responds to the 1-2.4 px edge transitions at each line
    - texture_consistency is high because lines tile uniformly across the image
    """
    canvas = np.full((SIZE, SIZE), BASE_GREY, dtype=np.int32)
    # 45-degree lines: y - x = const (every `spacing` steps)
    for k in range(-SIZE, SIZE + SIZE, spacing):
        for x in range(SIZE):
            y = x + k
            if 0 <= y < SIZE:
                canvas[y, x] -= amplitude
    # 135-degree lines: y + x = const (every `spacing` steps)
    for k in range(0, SIZE * 2, spacing):
        for x in range(SIZE):
            y = k - x
            if 0 <= y < SIZE:
                canvas[y, x] -= amplitude
    return np.clip(canvas, 0, 255).astype(np.uint8)


def _single_diagonal(spacing: int, amplitude: int) -> np.ndarray:
    """Single-direction diagonal lines (45 deg only).

    Tests whether one angular direction is sufficient to raise pencil_grain,
    or whether the second direction (crosshatch) is needed for consistency.
    """
    canvas = np.full((SIZE, SIZE), BASE_GREY, dtype=np.int32)
    for k in range(-SIZE, SIZE + SIZE, spacing):
        for x in range(SIZE):
            y = x + k
            if 0 <= y < SIZE:
                canvas[y, x] -= amplitude
    return np.clip(canvas, 0, 255).astype(np.uint8)


def _voronoi_flat(n_cells: int, amplitude: int) -> np.ndarray:
    """Voronoi cells with flat (constant) shading per cell.

    Each cell is assigned a random offset from the base grey. Edges between
    cells are sharp 1-pixel discontinuities. This mimics blocky faceting
    without gradients -- similar to some GPT crystalline patterns.

    Expected behaviour: texture_consistency is LOW (edge pixels cluster near
    cell boundaries, not uniformly distributed), so pencil_grain may be lower
    than crosshatch despite similar amplitude.
    """
    seeds_y = RNG.integers(0, SIZE, n_cells)
    seeds_x = RNG.integers(0, SIZE, n_cells)
    offsets = RNG.integers(-amplitude, amplitude + 1, n_cells).astype(np.int32)

    yy, xx = np.mgrid[0:SIZE, 0:SIZE]
    # Distance from each pixel to each seed
    dy = yy[:, :, None] - seeds_y[None, None, :]
    dx = xx[:, :, None] - seeds_x[None, None, :]
    dists = dy ** 2 + dx ** 2
    nearest = np.argmin(dists, axis=2)
    canvas = BASE_GREY + offsets[nearest]
    return np.clip(canvas, 0, 255).astype(np.uint8)


def _voronoi_gradient(n_cells: int, amplitude: int) -> np.ndarray:
    """Voronoi cells with linear gradient shading within each cell.

    Each cell's brightness varies linearly from one side to the other at a
    random angle, mimicking the angular surface normal variation in GPT
    crystalline faceting. Edges remain sharp.

    Expected: higher band_pass than flat Voronoi (gradients produce mid-freq
    content within each cell), more similar to real GPT faceting visually.
    """
    seeds_y = RNG.integers(0, SIZE, n_cells)
    seeds_x = RNG.integers(0, SIZE, n_cells)
    angles = RNG.uniform(0, 2 * math.pi, n_cells)

    yy, xx = np.mgrid[0:SIZE, 0:SIZE]
    dy = yy[:, :, None] - seeds_y[None, None, :]
    dx = xx[:, :, None] - seeds_x[None, None, :]
    dists = dy ** 2 + dx ** 2
    nearest = np.argmin(dists, axis=2)

    # Gradient along each cell's angle
    canvas = np.full((SIZE, SIZE), float(BASE_GREY))
    for i in range(n_cells):
        mask = nearest == i
        # Project pixel coordinates onto cell angle, normalise to [-0.5, 0.5]
        proj = (
            (xx[mask] - seeds_x[i]) * math.cos(angles[i])
            + (yy[mask] - seeds_y[i]) * math.sin(angles[i])
        ) / (SIZE * 0.5)
        proj = np.clip(proj, -0.5, 0.5)
        canvas[mask] += amplitude * proj

    return np.clip(canvas, 0, 255).astype(np.uint8)


def _triangle_tile(tile_size: int, amplitude: int) -> np.ndarray:
    """Alternating light/dark triangular tiles.

    Divides the image into right-triangles and shades them alternately.
    Creates uniform angular edges across the whole image -- the most
    visually similar to crystalline faceting and maximally consistent.
    """
    canvas = np.full((SIZE, SIZE), BASE_GREY, dtype=np.int32)
    yy, xx = np.mgrid[0:SIZE, 0:SIZE]
    # Which tile row/column
    tile_row = yy // tile_size
    tile_col = xx // tile_size
    # Within-tile coordinates normalised to [0, 1)
    ty = (yy % tile_size) / tile_size
    tx = (xx % tile_size) / tile_size
    # Upper-left or lower-right triangle
    upper_left = tx + ty < 1.0
    cell_parity = (tile_row + tile_col) % 2
    dark = upper_left ^ (cell_parity == 0)
    canvas[dark] -= amplitude
    canvas[~dark] += amplitude
    return np.clip(canvas, 0, 255).astype(np.uint8)


# ---------------------------------------------------------------------------
# Measurement
# ---------------------------------------------------------------------------

def _measure(label: str, arr: np.ndarray) -> dict:
    """Save array to disk, measure with evaluate_texture, return result dict."""
    path = OUT_DIR / f"{label}.png"
    Image.fromarray(arr).save(path)
    r = evaluate_texture(path)
    if r.status != "analyzed":
        return {"label": label, "error": r.error}

    findings = _ANALYZER.analyze(path, _CONTEXT)
    cryst_findings = [f for f in findings if f.category == "artifact.crystalline_faceting"]
    fires = len(cryst_findings) > 0
    severity = cryst_findings[0].severity.name if fires else "-"

    grain = r.pencil_grain_score
    smooth = r.watercolor_smoothness_score
    micro = r.microtexture_density_score
    cons = r.texture_consistency_score
    bp_raw = r.local_contrast_score  # closest proxy we have accessible

    threshold_ok = (
        grain >= _GRAIN_THRESHOLD
        and smooth < _SMOOTHNESS_CEILING
        and micro >= _MICRO_FLOOR
    )

    return {
        "label": label,
        "grain": grain,
        "smooth": smooth,
        "micro": micro,
        "consistency": cons,
        "fires": fires,
        "severity": severity,
        "all_ok": threshold_ok,
    }


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def main() -> None:
    results: list[dict] = []

    # 1. Baseline
    print("Generating probe images ...")
    results.append(_measure("00_flat_grey", _flat_grey()))

    # 2. Diagonal crosshatch -- main candidate
    for spacing in (2, 4, 6, 8, 12):
        for amp in (15, 30, 50, 80):
            label = f"crosshatch_s{spacing:02d}_a{amp:02d}"
            results.append(_measure(label, _diagonal_crosshatch(spacing, amp)))

    # 3. Single-direction diagonal
    for spacing in (4, 6):
        for amp in (30, 60):
            label = f"single_diag_s{spacing:02d}_a{amp:02d}"
            results.append(_measure(label, _single_diagonal(spacing, amp)))

    # 4. Voronoi flat shading
    for cells in (20, 40, 80):
        for amp in (30, 60):
            label = f"voronoi_flat_c{cells:02d}_a{amp:02d}"
            results.append(_measure(label, _voronoi_flat(cells, amp)))

    # 5. Voronoi gradient shading
    for cells in (20, 40, 80):
        for amp in (30, 60):
            label = f"voronoi_grad_c{cells:02d}_a{amp:02d}"
            results.append(_measure(label, _voronoi_gradient(cells, amp)))

    # 6. Triangle tile
    for tile_sz in (4, 8, 12, 16):
        for amp in (20, 40, 60):
            label = f"triangle_t{tile_sz:02d}_a{amp:02d}"
            results.append(_measure(label, _triangle_tile(tile_sz, amp)))

    # ------------------------------------------------------------------
    # Print full table
    # ------------------------------------------------------------------
    W = max(len(r["label"]) for r in results if "error" not in r)
    hdr = f"{'image':<{W}}  {'grain':>6}  {'smooth':>6}  {'micro':>5}  {'consist':>7}  {'fires':>5}  severity"
    sep = "-" * len(hdr)
    print()
    print("FULL SCORE TABLE")
    print(sep)
    print(hdr)
    print(sep)
    for r in results:
        if "error" in r:
            print(f"{r['label']:<{W}}  ERROR: {r['error']}")
            continue
        fire_str = "YES" if r["fires"] else "no"
        mark = " <-- FIRES" if r["fires"] else ""
        print(
            f"{r['label']:<{W}}  {r['grain']:>6.1f}  {r['smooth']:>6.1f}"
            f"  {r['micro']:>5.1f}  {r['consistency']:>7.1f}"
            f"  {fire_str:>5}  {r['severity']:<8}{mark}"
        )

    # ------------------------------------------------------------------
    # Summary: which images meet all three thresholds?
    # ------------------------------------------------------------------
    firing = [r for r in results if "error" not in r and r["all_ok"]]
    print()
    print("THRESHOLD ANALYSIS")
    print(sep)
    print(f"Thresholds: grain>={_GRAIN_THRESHOLD}, smooth<{_SMOOTHNESS_CEILING}, micro>={_MICRO_FLOOR}")
    print(f"Images meeting all three thresholds: {len(firing)} / {len(results)}")
    if firing:
        print()
        print(f"  {'image':<{W}}  grain  smooth   micro  severity")
        for r in firing:
            print(
                f"  {r['label']:<{W}}  {r['grain']:>5.1f}  "
                f"{r['smooth']:>6.1f}  {r['micro']:>6.1f}  {r['severity']}"
            )

    # ------------------------------------------------------------------
    # Monotonicity check: do crosshatch scores rise with amplitude?
    # ------------------------------------------------------------------
    print()
    print("CROSSHATCH MONOTONICITY CHECK (spacing=4)")
    print(sep)
    print(f"  {'amplitude':>9}  grain  smooth   micro")
    for amp in (15, 30, 50, 80):
        key = f"crosshatch_s04_a{amp:02d}"
        row = next((r for r in results if r.get("label") == key), None)
        if row and "error" not in row:
            print(
                f"  A={amp:<7}  {row['grain']:>5.1f}  "
                f"{row['smooth']:>6.1f}  {row['micro']:>6.1f}"
            )

    print()
    print(f"Probe images saved to: {OUT_DIR}")


if __name__ == "__main__":
    main()
