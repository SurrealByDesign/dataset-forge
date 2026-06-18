# Benchmark Inventory

Current state of the Dataset Forge benchmark system as of v0.1 alpha.

---

## Public benchmark suite

Runs immediately from a fresh clone. No private images or generation step required.

```
uv run python scripts/run_benchmarks.py
```

**Status: 10 / 10 expectations passing.**

Manifest: `benchmarks/benchmark_manifest.json`

### Committed fixtures (`benchmarks/synthetic_defects/`)

Five PNG fixtures are committed to git. They are deterministic and reproducible.

| File | Generator script | Analyzer tested | Expected result |
|---|---|---|---|
| `06_crystalline_low.png` | `generate_crystalline_fixtures.py` | CrystallineFacetingAnalyzer | Fires LOW (grain=45.1) |
| `07_crystalline_medium.png` | `generate_crystalline_fixtures.py` | CrystallineFacetingAnalyzer | Fires MEDIUM (grain=64.2) |
| `08_crystalline_negative_smooth.png` | `generate_crystalline_fixtures.py` | CrystallineFacetingAnalyzer | No finding (smooth guard: smooth=53.2 > 52 ceiling) |
| `09_texture_clean.png` | `generate_texture_fixtures.py` | TextureAnalyzer | No finding (micro=0.0, below absolute floor) |
| `10_texture_positive.png` | `generate_texture_fixtures.py` | TextureAnalyzer | Fires MEDIUM (micro=88.7, z=1.0) |

Generators are deterministic and seeded. Re-running them reproduces identical pixel values:

```
uv run python scripts/generate_crystalline_fixtures.py
uv run python scripts/generate_texture_fixtures.py
```

### Skipped cases (synthetic-generated, not committed)

Cases `00`, `04`, and `05` in the public manifest are marked `private: true`
and are skipped automatically when the referenced images are absent. Cases `01`,
`02`, and `03` are not in the public manifest (files exist locally if generated,
but are gitignored and have no manifest expectations). A local reference image
is required to generate any of these via `scripts/generate_benchmark_defects.py`.
Skipped cases do not count as failures.

---

## Local benchmark suite (optional)

Manifest: `benchmarks/local_benchmark_manifest.json` (gitignored -- never commit this)

References private real-sample images in `benchmarks/real_samples/` (also gitignored).
Place images there manually. Missing images are skipped, not failed.

```
uv run python scripts/run_benchmarks.py --manifest benchmarks/local_benchmark_manifest.json
```

---

## Benchmark folders

| Folder | Git status | Purpose |
|---|---|---|
| `benchmarks/synthetic_defects/` | Committed fixtures only (see above); other generated files ignored | Synthetic fixture images |
| `benchmarks/real_samples/` | All image files gitignored | Private calibration images (optional, local only) |
| `benchmarks/reference/` | All image files gitignored | Local reference images for generating synthetic defects |
| `benchmarks/results/` | Gitignored | Per-run benchmark output and research probe reports |

---

## Benchmark coverage

| Artifact family | Public fixture coverage | Analyzer tested |
|---|---|---|
| Microtexture | 2 cases (clean + MEDIUM) | TextureAnalyzer |
| Crystalline faceting | 3 cases (LOW, MEDIUM, negative) | CrystallineFacetingAnalyzer |
| Speck / glitter | None | Not yet implemented |
| Recursive detail overload | None | Not yet implemented |
| Oversharpening / halos | None | Not yet implemented |

---

## Known gaps

- No synthetic fixtures for speck/glitter, recursive detail, or oversharpening families.
- No fixture exercises the HIGH severity tier for either analyzer.
- No fixture exercises TextureAnalyzer CRITICAL tier.
- Real-sample benchmark cases are private and optional; not reproducible from a fresh clone.
- Benchmark results history is not versioned (results/ is gitignored).

---

## Analyzer regression tests

In addition to the benchmark manifests, committed fixtures have dedicated
regression tests:

| Test file | Fixtures tested | Tests |
|---|---|---|
| `tests/test_crystalline_fixtures.py` | 06, 07, 08 | 32 |
| `tests/test_texture_fixtures.py` | 09, 10 | 21 |
| `tests/test_benchmark.py` | Benchmark framework | 29 |
