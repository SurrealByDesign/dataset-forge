# Benchmark Inventory

This document records the benchmark material currently present in the repository
workspace and the benchmark categories Dataset Forge intends to support.

The benchmark system is documentation and calibration support for analysis. It
does not modify source images, does not run cleanup, and does not make
recommendations by itself.

## Benchmark Folders

| Folder | Current contents | Purpose | Git status |
|---|---|---|---|
| `benchmarks/` | README, real sample manifest proposal, benchmark subfolders | Root for benchmark guidance and local benchmark assets | README and real sample proposal are tracked |
| `benchmarks/reference/` | `.gitkeep`, local `banana_reference.jpg` | Local clean reference images used to generate synthetic defect sets | Reference images are ignored; `.gitkeep` is tracked |
| `benchmarks/synthetic_defects/` | `.gitkeep`, generated PNG variants, generated manifest | Deterministic synthetic defect benchmark outputs | Generated outputs are ignored; `.gitkeep` is tracked |
| `benchmarks/real_samples/` | Five JPG samples | Real-world sample images for future benchmark classification | Currently tracked |
| `benchmarks/results/` | Not present in this workspace | Intended location for benchmark run outputs | Ignored if created |
| `benchmarks/generated/` | Not present in this workspace | Intended location for generated benchmark artifacts | Ignored if created |
| `benchmarks/output/`, `benchmarks/outputs/` | Not present in this workspace | Alternate generated benchmark output locations | Ignored if created |

## Benchmark-Related Files

| File | Purpose |
|---|---|
| `benchmarks/README.md` | Explains private benchmark image handling and deterministic synthetic defect generation. |
| `benchmarks/real_samples_manifest.proposal.json` | Proposed metadata replacement for tracked real sample images. Includes dimensions, hashes, byte sizes, provenance placeholders, and category placeholders. |
| `benchmarks/synthetic_defects/benchmark_manifest.json` | Local generated manifest for the current synthetic defect set. Records source image hash, seed, strength, generated files, and parameters. |
| `scripts/generate_benchmark_defects.py` | Deterministic local generator for synthetic defect variants. |
| `tests/test_benchmark_generator.py` | Tests the synthetic benchmark generator behavior. |

## Synthetic Benchmark Assets

The current local generated set was produced from
`benchmarks/reference/banana_reference.jpg` with seed `1234` and strength
`medium`.

| Asset | Defect type | Intended purpose | Category coverage |
|---|---|---|---|
| `00_reference.png` | `reference` | Baseline image copied into normalized PNG form for comparison against generated variants. | Clean reference |
| `01_glitter_speckles.png` | `glitter_speckles` | Bright small speckles for highlight/glitter contamination detection. | Glitter contamination, speckle noise |
| `02_recursive_microtexture.png` | `recursive_microtexture` | Repeating microtexture pattern for texture-density and periodic pattern sensitivity. | Periodic noise, over-textured surfaces |
| `03_crunchy_oversharpened.png` | `crunchy_oversharpened` | Unsharp-mask style crunchy detail for sharpness and halo sensitivity. | Oversharpening halos, edge artifacts |
| `04_color_noise.png` | `color_noise` | Per-channel noise variation for noisy-color and speckle-like artifact checks. | Speckle/noise coverage, but not a dedicated luminance speckle set |
| `05_mixed_artifacts.png` | `mixed_artifacts` | Combined microtexture, color noise, oversharpening, and glitter speckles. | Compound artifact stress case |

The generator supports `light`, `medium`, and `strong` strengths, but this
workspace currently contains only one generated strength level.

## Real Benchmark Assets

`benchmarks/real_samples/` currently contains five JPG images:

| Asset | Dimensions | Current metadata status | Intended purpose |
|---|---:|---|---|
| `1steak.jpg` | 1085 x 1450 | Hash and size documented; provenance and category still TODO. | Future real-world artifact classification sample. |
| `gimpfrog.jpg` | 1085 x 1450 | Hash and size documented; provenance and category still TODO. | Future real-world artifact classification sample. |
| `picklewizard.jpg` | 1083 x 1453 | Hash and size documented; provenance and category still TODO. | Future real-world artifact classification sample. |
| `snakemountain.jpg` | 1118 x 1407 | Hash and size documented; provenance and category still TODO. | Future real-world artifact classification sample. |
| `vtp4jc1040s51.jpg` | 1920 x 2400 | Hash and size documented; provenance and category still TODO. | Future real-world artifact classification sample or clean reference candidate. |

These files should not be treated as redistribution-safe until their provenance,
license, and intended defect category are documented. The manifest proposal is
the right replacement path if the images should stop being tracked while staying
available locally.

## Proposed Benchmark Categories

| Category | Current asset coverage | Notes |
|---|---|---|
| Periodic noise | Partial | `02_recursive_microtexture.png` provides a repeating microtexture pattern, but there is no separately named `periodic_noise` folder or multi-strength matrix. |
| Glitter contamination | Present | `01_glitter_speckles.png` and `05_mixed_artifacts.png` cover bright speckle contamination. |
| Oversharpening halos | Partial | `03_crunchy_oversharpened.png` covers oversharpening. Dedicated halo-only assets are not present. |
| Speckle noise | Partial | Glitter speckles and color noise exist. A dedicated neutral speckle-noise benchmark is not present. |
| Duplicate detection | Missing | No duplicate or near-duplicate benchmark set is present. |

## Known Gaps

- No canonical `benchmarks/synthetic/<category>/` hierarchy exists yet, even
  though the architecture describes that layout.
- Only one generated synthetic set is present locally; there is no committed
  manifest matrix for multiple strengths, seeds, or reference images.
- Real samples still need provenance, license status, and intended defect
  categories before they can be safely used as durable project benchmarks.
- There is no dedicated duplicate-detection benchmark set.
- There is no dedicated halo-only benchmark distinct from general
  oversharpening.
- There is no benchmark results history under `benchmarks/results/`.

## Recommended Next Benchmark Task

Create a versioned benchmark manifest that classifies each synthetic and real
asset by category, expected detector response, provenance status, and allowed
redistribution status. After that, add missing duplicate-detection and halo-only
synthetic sets so analyzer calibration can compare expected findings against
known defects.
