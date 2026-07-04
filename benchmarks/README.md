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

Expected output: all committed fixture expectations PASS, exit 0. Optional
generated/private cases may be skipped when their local images are absent.

---

## Manifests

| File | Tracked in git | Purpose |
|---|---|---|
| `benchmark_manifest.json` | Yes | Public suite  --  committed synthetic fixtures plus optional generated/private cases |
| `local_benchmark_manifest.json` | **No** | Private suite  --  real dataset samples |
| `real_world/manifest.json` | Yes | Real-world validation corpus framework  --  committed placeholder methodology fixtures plus optional private/local groups |

### Public manifest (`benchmark_manifest.json`)

The public manifest contains two kinds of cases:

- `synthetic-committed`: images tracked in git and always available from a fresh clone.
- `synthetic-generated` / `private: true`: optional local cases that are skipped
  automatically if the referenced images are absent.

No generation step is needed for the committed public fixture expectations.

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
| `11_oversharpen_clean_edge.png` | committed fixture | OversharpeningHaloAnalyzer | No finding (clean hard-edge guard) |
| `12_oversharpen_halo_positive.png` | committed fixture | OversharpeningHaloAnalyzer | Fires MEDIUM |
| `13_oversharpen_texture_guard.png` | committed fixture | OversharpeningHaloAnalyzer | No finding (distributed texture guard) |
| `14_hfi_clean_negative.png` | committed fixture | HighFrequencyIsolatedArtifactAnalyzer | No finding (clean smooth guard) |
| `15_hfi_bright_speck_positive.png` | committed fixture | HighFrequencyIsolatedArtifactAnalyzer | Fires MEDIUM |
| `16_hfi_dark_speck_positive.png` | committed fixture | HighFrequencyIsolatedArtifactAnalyzer | Fires MEDIUM |
| `17_hfi_pencil_grain_guard.png` | committed fixture | HighFrequencyIsolatedArtifactAnalyzer | No finding (paper/pencil grain guard) |
| `18_hfi_edge_halo_guard.png` | committed fixture | HighFrequencyIsolatedArtifactAnalyzer | No finding (edge-adjacent halo guard) |

The crystalline and texture generators are deterministic. Re-running them
reproduces identical pixel values for fixtures 06--10. Fixtures 11--18 are
committed benchmark assets; add a deterministic generator before changing them.

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

## Real-world validation corpus (`benchmarks/real_world/`)

v0.6.0-alpha adds a corpus framework for labeled real-world validation datasets.
It is methodology only: no analyzer thresholds, inspect output, CLI behavior,
repair planning, cleanup, repair, export, or UI behavior changes.

The committed corpus currently includes a public synthetic placeholder group to
prove manifest, label, and validation-dossier compatibility. It is not
real-world reliability evidence. Legally safe public-domain/CC0 or otherwise
redistributable real-world fixtures can be added later with source/license
metadata, labels, and expected outputs.

Private/local real-world datasets belong under `benchmarks/real_world/private/`,
which is gitignored. Missing optional private fixtures are skipped cleanly so
fresh-clone benchmark and test behavior remains deterministic.

---

## Results

`benchmarks/results/` is gitignored. Each `run_benchmarks.py` run writes
`benchmark_results.json` and `benchmark_results.txt` there.
