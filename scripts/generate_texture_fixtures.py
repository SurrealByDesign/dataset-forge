"""Generate synthetic texture benchmark fixtures for TextureAnalyzer.

Produces two deterministic PNG images committed as public benchmark fixtures.
Re-running reproduces the same pixel values (seeded RNG for noise image,
fully deterministic for flat grey).

Usage:
    uv run python scripts/generate_texture_fixtures.py
    uv run python scripts/generate_texture_fixtures.py --output path/to/dir

Images written to benchmarks/synthetic_defects/ (or --output):
    09_texture_clean.png
        Flat grey (128, 128, 128). microtexture ~0 (no local variation).
        TextureAnalyzer does NOT fire: micro below absolute floor (15).
        Purpose: clean anchor that pulls the group mean down, maximising
        the z-score of the noise companion.

    10_texture_positive.png
        Seeded uniform noise [68, 189) RGB, seed=42, 256x256.
        microtexture ~90 (high local pixel-to-blur deviation).
        TextureAnalyzer fires: micro >> floor AND high z-score relative
        to [clean, noise] group.
        Purpose: minimal synthetic positive that validates TextureAnalyzer
        detection without real images.

Context group design:
    Group "texture_committed" = [09_texture_clean, 10_texture_positive].
    mean(micro) = (0 + micro_noise) / 2
    stddev(micro) = micro_noise / 2  (two-sample std dev)
    z(noise) = (micro_noise - mean) / stddev = 1.0  (exactly MEDIUM boundary)

    Because z is structurally pinned to ~1.0 for any two-image [0, X] group,
    expected_severity is set to null in the manifest (fires at some severity
    is all we assert). The test suite checks the absolute-floor threshold
    and that a finding IS emitted; it does not pin severity.

Probe script: scripts/_probe_crystalline_synthetic.py (crystalline variant).
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
from dataset_forge.analyzers.texture import TextureAnalyzer, _ABSOLUTE_FLOOR
from dataset_forge.context import (
    CONTEXT_SCHEMA_VERSION,
    AspectRatioStats,
    DatasetContext,
    FrequencyDistributions,
    ResolutionStats,
    TextureDistributions,
)

SIZE = 256
_ANALYZER = TextureAnalyzer()

FIXTURES = [
    {
        "filename": "09_texture_clean.png",
        "kind": "flat_grey",
        "description": "Flat grey anchor. microtexture ~0, below absolute floor.",
    },
    {
        "filename": "10_texture_positive.png",
        "kind": "uniform_noise",
        "noise_low": 68,
        "noise_high": 189,
        "seed": 42,
        "description": "Seeded uniform noise. microtexture high. TextureAnalyzer fires.",
    },
]


def _make_flat_grey(size: int = SIZE) -> np.ndarray:
    arr = np.full((size, size), 128, dtype=np.uint8)
    return np.stack([arr, arr, arr], axis=2)


def _make_noise(size: int = SIZE, low: int = 68, high: int = 189, seed: int = 42) -> np.ndarray:
    rng = np.random.default_rng(seed)
    arr = rng.integers(low, high, (size, size), dtype=np.uint8)
    return np.stack([arr, arr, arr], axis=2)


def _build_group_context(micro_clean: float, micro_noise: float) -> DatasetContext:
    """Build a DatasetContext that reflects the two-image texture_committed group."""
    scores = [micro_clean, micro_noise]
    mean = float(np.mean(scores))
    # Population std (N=2): sqrt(((x-mean)^2 + (y-mean)^2) / 2)
    stddev = float(np.std(scores))
    return DatasetContext(
        schema_version=CONTEXT_SCHEMA_VERSION,
        analyzer_versions={},
        image_paths=(),
        image_count=2,
        error_count=0,
        resolution_stats=ResolutionStats.empty(),
        aspect_ratio_stats=AspectRatioStats.empty(),
        texture_distributions=TextureDistributions(
            mean=mean, stddev=stddev, p10=micro_clean, p90=micro_noise, sample_count=2
        ),
        frequency_distributions=FrequencyDistributions.empty(),
        duplicate_hashes=frozenset(),
        duplicate_groups=(),
    )


def generate(output_dir: Path) -> list[dict]:
    output_dir.mkdir(parents=True, exist_ok=True)
    results = []

    paths = {}
    for spec in FIXTURES:
        path = output_dir / spec["filename"]
        if spec["kind"] == "flat_grey":
            arr = _make_flat_grey()
        else:
            arr = _make_noise(low=spec["noise_low"], high=spec["noise_high"], seed=spec["seed"])
        Image.fromarray(arr).save(path)
        paths[spec["filename"]] = path

    # Measure both images
    measured = {}
    for spec in FIXTURES:
        path = paths[spec["filename"]]
        r = evaluate_texture(path)
        if r.status != "analyzed":
            raise RuntimeError(f"evaluate_texture failed on {path}: {r.error}")
        measured[spec["filename"]] = r

    clean_r = measured["09_texture_clean.png"]
    noise_r = measured["10_texture_positive.png"]

    ctx = _build_group_context(clean_r.microtexture_density_score, noise_r.microtexture_density_score)

    for spec in FIXTURES:
        path = paths[spec["filename"]]
        r = measured[spec["filename"]]
        findings = _ANALYZER.analyze(path, ctx)
        texture_findings = [f for f in findings if f.category == "texture.high_microtexture"]
        fires = len(texture_findings) > 0
        severity = texture_findings[0].severity.name if fires else "NONE"
        z = texture_findings[0].evidence.get("z_score") if fires else None

        results.append({
            "filename": spec["filename"],
            "path": path,
            "kind": spec["kind"],
            "micro": r.microtexture_density_score,
            "grain": r.pencil_grain_score,
            "smooth": r.watercolor_smoothness_score,
            "fires": fires,
            "severity": severity,
            "z_score": z,
        })

    return results


def _print_results(results: list[dict]) -> None:
    W = max(len(r["filename"]) for r in results)
    print()
    print(f"{'filename':<{W}}  {'micro':>6}  {'grain':>6}  {'smooth':>6}  {'fires':>5}  {'sev':>8}  z")
    print("-" * (W + 52))
    for r in results:
        fire_str = "YES" if r["fires"] else "no"
        z_str = f"{r['z_score']:.3f}" if r["z_score"] is not None else "   -"
        print(
            f"{r['filename']:<{W}}  {r['micro']:>6.1f}  {r['grain']:>6.1f}"
            f"  {r['smooth']:>6.1f}  {fire_str:>5}  {r['severity']:>8}  {z_str}"
        )
    print()
    print(f"Absolute floor: {_ABSOLUTE_FLOOR}")
    clean = next(r for r in results if r["kind"] == "flat_grey")
    noise = next(r for r in results if r["kind"] == "uniform_noise")
    print(f"Clean micro: {clean['micro']:.3f}  (should be near 0)")
    print(f"Noise micro: {noise['micro']:.3f}  (should be > {_ABSOLUTE_FLOOR})")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate texture benchmark fixtures."
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

    print(f"Generating texture fixtures in {output_dir} ...")
    results = generate(output_dir)
    _print_results(results)

    clean = next(r for r in results if r["kind"] == "flat_grey")
    noise = next(r for r in results if r["kind"] == "uniform_noise")

    ok = True
    if clean["fires"]:
        print(f"WARNING: {clean['filename']} fired but should be clean")
        ok = False
    else:
        print(f"OK  {clean['filename']}: no finding (micro={clean['micro']:.1f} < floor {_ABSOLUTE_FLOOR})")

    if noise["fires"]:
        print(f"OK  {noise['filename']}: fires with {noise['severity']} (micro={noise['micro']:.1f}, z={noise['z_score']:.3f})")
    else:
        print(f"WARNING: {noise['filename']} did not fire (micro={noise['micro']:.1f})")
        ok = False

    print()
    print("Done." if ok else "WARNINGS -- check output above.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
