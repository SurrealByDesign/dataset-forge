# Dataset Forge Benchmarks

This directory holds benchmark manifests, committed synthetic fixture images,
and (locally only) private real-sample images.

---

## Quick start (fresh clone)

The public benchmark runs immediately after cloning  --  no generation step required.
Committed fixture images are already present in `benchmarks/synthetic_defects/`.

```
uv run python scripts/run_benchmarks.py
```

Expected output: all expectations PASS, exit 0.

---

## Manifests

| File | Tracked in git | Purpose |
|---|---|---|
| `benchmark_manifest.json` | Yes | Public suite  --  synthetic-committed cases only |
| `local_benchmark_manifest.json` | **No** | Private suite  --  real dataset samples |

### Public manifest (`benchmark_manifest.json`)

All cases in the public manifest reference images that are committed to git
(`provenance: "synthetic-committed"`) or are marked `private: true` (skipped
automatically if missing). No generation step is needed to run the public suite.

Run it:

```
uv run python scripts/run_benchmarks.py
```

### Local manifest (`local_benchmark_manifest.json`)

Contains cases that reference private real images from a local training dataset.
This file is gitignored and must never be committed.

To run it:

```
uv run python scripts/run_benchmarks.py --manifest benchmarks/local_benchmark_manifest.json
```

Missing images are skipped (not failed), so partial runs are safe.

---

## Synthetic defects (`benchmarks/synthetic_defects/`)

Most files here are gitignored. The following fixtures are **committed to git**
and are present immediately after cloning:

| File | Generator | Analyzer | Result |
|---|---|---|---|
| `06_crystalline_low.png` | `generate_crystalline_fixtures.py` | CrystallineFacetingAnalyzer | Fires LOW |
| `07_crystalline_medium.png` | `generate_crystalline_fixtures.py` | CrystallineFacetingAnalyzer | Fires MEDIUM |
| `08_crystalline_negative_smooth.png` | `generate_crystalline_fixtures.py` | CrystallineFacetingAnalyzer | No finding (smooth guard) |
| `09_texture_clean.png` | `generate_texture_fixtures.py` | TextureAnalyzer | No finding (below floor) |
| `10_texture_positive.png` | `generate_texture_fixtures.py` | TextureAnalyzer | Fires MEDIUM |

All generators are deterministic. Re-running them reproduces identical pixel values.

```
uv run python scripts/generate_crystalline_fixtures.py
uv run python scripts/generate_texture_fixtures.py
```

The `synthetic-generated` cases in the public manifest (cases 00--05) reference images
that are **not** committed. They are marked `private: true` and are skipped automatically.
To generate them, a local reference image is required (see `generate_benchmark_defects.py`).

---

## Real samples (`benchmarks/real_samples/`)

All image files here are gitignored. Place private calibration images here manually.
Filenames and expected scores are documented in `local_benchmark_manifest.json`
(also gitignored).

---

## Results

`benchmarks/results/` is gitignored. Each `run_benchmarks.py` run writes
`benchmark_results.json` and `benchmark_results.txt` there.
