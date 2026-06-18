# Dataset Forge -- Current Status

*Last updated: 2026-06-18. Reflects v0.1 alpha.*

---

## Release

**Dataset Forge v0.1 alpha** implements the v1 Inspect slice:

```
Dataset -> DatasetContext -> Analyzer -> Finding -> Report
```

Supported in v0.1 alpha:
- `dataset-forge inspect <path>` -- full inspect pipeline
- JSON and plain-text reports (`inspection_report.json`, `inspection_report.txt`)
- Optional gallery PNG (`--gallery`)
- Public benchmark suite (10 expectations, all passing from fresh clone)

Not supported in v0.1 alpha (planned for later releases):
- Cleanup (v2+)
- UI (v2+)
- Plugin system (v2+)
- Additional analyzers beyond the two shipped (v1.x)
- Calibrated thresholds (pending labeled benchmark ground truth)

---

## Test suite

**644 tests passing.**

Covers: Finding, DatasetContext, Analyzer contracts, report writers, CLI,
inspect runner, gallery, benchmark framework, and all committed fixtures.

```
uv run pytest tests/
```

---

## Implemented (v1 pipeline)

| Component | File | Status |
|---|---|---|
| CLI `inspect` command | `src/dataset_forge/cli.py` | Done |
| Inspect spine runner | `src/dataset_forge/inspect.py` | Done |
| Gallery writer | `src/dataset_forge/inspect_gallery.py` | Done |
| JSON + TXT report writers | `src/dataset_forge/report.py` | Done |
| `Finding` dataclass | `src/dataset_forge/finding.py` | Done |
| `DatasetContext` dataclass | `src/dataset_forge/context.py` | Done |
| `Analyzer` base class | `src/dataset_forge/analyzers/base.py` | Done |
| `TextureAnalyzer` | `src/dataset_forge/analyzers/texture.py` | First-pass; uncalibrated |
| `CrystallineFacetingAnalyzer` | `src/dataset_forge/analyzers/crystalline.py` | First-pass; uncalibrated |
| Benchmark framework | `src/dataset_forge/benchmark.py` | Done |
| Benchmark manifest | `benchmarks/benchmark_manifest.json` | 10 expectations; all pass |

---

## Not yet implemented (v1 gaps)

| Component | Notes |
|---|---|
| Speck/glitter analyzer | Research probe: DEFER -- signal inverts vs clean images |
| Oversharpening/halo analyzer | Research probe: DEFER -- no reliable pixel-neighborhood signal |
| Periodic frequency / recursive detail analyzer | Not yet investigated |
| Calibrated thresholds | Pending labeled benchmark ground truth for all analyzers |
| Phase 2 measurement cache | `ImageMeasurements` dataclass; replaces `lru_cache` on `evaluate_texture` |

---

## Benchmark fixtures (committed, public)

Five PNG fixtures are committed to `benchmarks/synthetic_defects/`:

| File | Analyzer | Expected result |
|---|---|---|
| `06_crystalline_low.png` | CrystallineFacetingAnalyzer | Fires LOW |
| `07_crystalline_medium.png` | CrystallineFacetingAnalyzer | Fires MEDIUM |
| `08_crystalline_negative_smooth.png` | CrystallineFacetingAnalyzer | No finding (smooth guard) |
| `09_texture_clean.png` | TextureAnalyzer | No finding (below floor) |
| `10_texture_positive.png` | TextureAnalyzer | Fires MEDIUM |

The public benchmark runs immediately from a fresh clone. No generation step required.

---

## Scripts (internal / calibration)

Files in `scripts/` beginning with `_` are internal calibration, diagnostic, or
research tools. They are not part of the public API.

Files in `scripts/research/` are artifact-family research probes. Both current
probes (oversharpening, speck/glitter) are DEFERRED per their research reports.

---

## Known limitations

- `texture_analyzer/v1`: z-score thresholds derived from one private dataset.
  Confidence capped at 0.70. FP rate ~15% (estimated).
- `crystalline_faceting_analyzer/v1`: threshold derived from calibration review.
  Confidence capped at 0.45. FP rate ~28% (estimated). Grain 45-55 range has
  significant TP/FP interleaving that requires a fourth discriminating signal.
- Both analyzers emit `"calibrated": false` in their evidence dicts.

---

## Next recommended tasks

1. **Fourth discriminating signal for crystalline** -- grain 45-55 TP/FP
   interleaving cannot be resolved by threshold adjustment alone. Candidates:
   spatial coherence, directional frequency energy, micro-edge profile.

2. **TextureAnalyzer calibration** -- z-score thresholds are uncalibrated.
   11 UNSURE images from the anthropomorph review need a dedicated pass.

3. **Recursive detail overload** -- next artifact family in ARCHITECTURE.md.
   No existing partial signal; requires a fresh probe before implementation.

---

## Internal notes

Detailed calibration results, private dataset statistics, and probe reports:
`docs/internal_calibration_notes.md`
