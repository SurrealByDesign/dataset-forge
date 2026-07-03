# Dataset Forge -- Current Status

*Last updated: 2026-07-02. Reflects v0.2.0-alpha.*

---

## Release

**Dataset Forge v0.2.0-alpha** implements the inspect-only image inspection platform:

```
Findings -> Aggregation -> Dataset Summary -> Review Queue -> Report
```

Supported in v0.2.0-alpha:
- `dataset-forge inspect <path>` -- full inspect pipeline
- JSON and plain-text reports (`inspection_report.json`, `inspection_report.txt`)
- Optional gallery PNG (`--gallery`)
- Additive Dataset Summary and Review Queue report sections
- Public benchmark suite (18 expectations, all passing from fresh clone)

Not supported in v0.2.0-alpha (planned for later releases):
- Cleanup (v2+)
- Repair (future)
- Export (future)
- UI (v2+)
- Plugin system (v2+)
- Additional analyzers beyond the current first-pass set (v1.x)
- Calibrated thresholds (pending labeled benchmark ground truth)

---

## Test suite

**799 tests passing, 1 skipped.**

Covers: Finding, DatasetContext, Analyzer contracts, report writers, CLI,
inspect runner, gallery, benchmark framework, committed fixtures,
post-inspection review guidance, and public CLI surface.

```
uv run pytest tests/
```

---

## Implemented (inspect pipeline)

| Component | File | Status |
|---|---|---|
| CLI `inspect` command | `src/dataset_forge/cli.py` | Done |
| Inspect spine runner | `src/dataset_forge/inspect.py` | Done |
| Gallery writer | `src/dataset_forge/inspect_gallery.py` | Done |
| JSON + TXT report writers | `src/dataset_forge/report.py` | Done |
| Dataset Summary + Review Queue | `src/dataset_forge/post_inspection.py` | Advisory post-inspection sections |
| `Finding` dataclass | `src/dataset_forge/finding.py` | Done |
| `DatasetContext` dataclass | `src/dataset_forge/context.py` | Done |
| `Analyzer` base class | `src/dataset_forge/analyzers/base.py` | Done |
| `TextureAnalyzer` | `src/dataset_forge/analyzers/texture.py` | First-pass; uncalibrated |
| `CrystallineFacetingAnalyzer` | `src/dataset_forge/analyzers/crystalline.py` | First-pass; uncalibrated |
| `OversharpeningHaloAnalyzer` | `src/dataset_forge/analyzers/oversharpening.py` | First-pass; uncalibrated |
| `HighFrequencyIsolatedArtifactAnalyzer` | `src/dataset_forge/analyzers/high_frequency_isolated.py` | First-pass; uncalibrated |
| Benchmark framework | `src/dataset_forge/benchmark.py` | Done |
| Benchmark manifest | `benchmarks/benchmark_manifest.json` | 18 expectations; all pass |

Current finding categories:

- `texture.high_microtexture` for the texture artifact family (`artifact.texture` in planning language)
- `artifact.crystalline_faceting`
- `artifact.oversharpening_halo`
- `artifact.high_frequency_isolated`

---

## Not yet implemented (post-alpha gaps)

| Component | Notes |
|---|---|
| Speck/glitter analyzer calibration | First-pass isolated high-frequency analyzer implemented; synthetic fixtures pass; real-world calibration still pending |
| Oversharpening/halo analyzer calibration | First-pass USM-residual analyzer implemented; synthetic fixtures pass; real-world calibration still pending |
| Periodic frequency analyzer | Researched; not approved for implementation until a better discriminator exists |
| Recursive detail analyzer | Not yet investigated |
| Calibrated thresholds | Pending labeled benchmark ground truth for all analyzers |
| Real-world calibration datasets | Pending labeled ground truth beyond synthetic fixtures |

---

## Benchmark fixtures (committed, public)

Thirteen PNG fixtures are committed to `benchmarks/synthetic_defects/`:

| File | Analyzer | Expected result |
|---|---|---|
| `06_crystalline_low.png` | CrystallineFacetingAnalyzer | Fires LOW |
| `07_crystalline_medium.png` | CrystallineFacetingAnalyzer | Fires MEDIUM |
| `08_crystalline_negative_smooth.png` | CrystallineFacetingAnalyzer | No finding (smooth guard) |
| `09_texture_clean.png` | TextureAnalyzer | No finding (below floor) |
| `10_texture_positive.png` | TextureAnalyzer | Fires MEDIUM |
| `11_oversharpen_clean_edge.png` | OversharpeningHaloAnalyzer | No finding (clean hard-edge guard) |
| `12_oversharpen_halo_positive.png` | OversharpeningHaloAnalyzer | Fires MEDIUM |
| `13_oversharpen_texture_guard.png` | OversharpeningHaloAnalyzer | No finding (distributed texture guard) |
| `14_hfi_clean_negative.png` | HighFrequencyIsolatedArtifactAnalyzer | No finding (clean smooth guard) |
| `15_hfi_bright_speck_positive.png` | HighFrequencyIsolatedArtifactAnalyzer | Fires MEDIUM |
| `16_hfi_dark_speck_positive.png` | HighFrequencyIsolatedArtifactAnalyzer | Fires MEDIUM |
| `17_hfi_pencil_grain_guard.png` | HighFrequencyIsolatedArtifactAnalyzer | No finding (paper/pencil grain guard) |
| `18_hfi_edge_halo_guard.png` | HighFrequencyIsolatedArtifactAnalyzer | No finding (edge-adjacent halo guard) |

The public benchmark runs immediately from a fresh clone. No generation step required.

---

## Scripts

**Public tools** (documented, supported in v0.2.0-alpha):

| Script | Purpose |
|---|---|
| `scripts/run_benchmarks.py` | Run the public benchmark suite |
| `scripts/generate_crystalline_fixtures.py` | Regenerate committed crystalline PNG fixtures |
| `scripts/generate_texture_fixtures.py` | Regenerate committed texture PNG fixtures |
| `scripts/generate_benchmark_defects.py` | Generate private synthetic defect images (requires local reference image) |

**Internal development utilities** (not part of the public API):

Files beginning with `_` (`scripts/_*.py`) are internal calibration, diagnostic,
or development scripts. The following non-prefixed scripts are also internal
calibration utilities, not supported public tools:

`compute_metrics.py`, `crystalline_fp_characterization.py`,
`crystalline_severity_calibration.py`, `diagnostic_report.py`,
`label_ground_truth.py`, `pencil_grain_diagnostic.py`,
`review_decisions.py`, `validation_contact_sheet.py`

**Research probes** (`scripts/research/`):

Artifact-family research probes live in `scripts/research/`. Historical
oversharpening and speck/glitter probes remain in `benchmarks/results/`.

---

## Known limitations

- `texture_analyzer/v1`: z-score thresholds derived from one private dataset.
  Confidence capped at 0.70. FP rate ~15% (estimated).
- `crystalline_faceting_analyzer/v1`: threshold derived from calibration review.
  Confidence capped at 0.45. FP rate ~28% (estimated). Grain 45-55 range has
  significant TP/FP interleaving that requires a fourth discriminating signal.
- `oversharpening_halo_analyzer/v1`: USM-residual rule validated against
  synthetic fixtures only. Confidence capped at 0.45. Real-world precision and
  recall are not yet known.
- `high_frequency_isolated_artifact_analyzer/v1`: residual connected-component
  rule validated against synthetic fixtures only. Confidence capped at 0.45.
  Real-world precision and recall are not yet known.
- All first-pass analyzers emit `"calibrated": false` in their evidence dicts.
- Dataset Summary and Review Queue are advisory only. They organize existing
  findings for human review; they do not reject, regenerate, repair, export, or
  modify images.

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
