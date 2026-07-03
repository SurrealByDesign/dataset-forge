# Dataset Forge - Roadmap

---

## v0.2.0-alpha: Dataset Forge Inspect -- Released

**Goal:** Produce explainable, read-only findings for image datasets.

**Pipeline:** `Dataset -> DatasetContext -> Analyzer -> Finding -> Aggregation -> Dataset Summary -> Review Queue -> Report`

**Status:** Released. See [CURRENT_STATUS.md](CURRENT_STATUS.md) for the
authoritative implementation state.

### v0.2.0-alpha -- Shipped

| Component | Status |
|---|---|
| `Finding` dataclass | shipped |
| `DatasetContext` dataclass | shipped |
| `Analyzer` base class | shipped |
| `TextureAnalyzer` -- microtexture, watercolor smoothness signal | shipped; first-pass uncalibrated |
| `CrystallineFacetingAnalyzer` -- pencil_grain + texture_consistency | shipped; first-pass uncalibrated |
| `OversharpeningHaloAnalyzer` -- edge-localized USM residuals | shipped; first-pass uncalibrated |
| `HighFrequencyIsolatedArtifactAnalyzer` -- sparse residual components | shipped; first-pass uncalibrated |
| JSON + TXT report writers | shipped |
| CLI: `dataset-forge inspect <path>` | shipped |
| Optional gallery PNG output | shipped |
| Dataset Summary + Review Queue -- advisory post-inspection guidance | shipped |
| Public benchmark suite (18 expectations, synthetic fixtures committed) | shipped |
| Public CLI surface locked to inspect-only | shipped |

**v0.2.0-alpha does not include:** cleanup, repair, regeneration, AI editing,
UI, captions, plugins, or exporters.

### v0.2.0-alpha -- Analyzer Research Status

The current alpha includes four first-pass analyzers. Some shipped analyzers
still need real-world calibration; that calibration work is post-alpha.

| Artifact family | Status | Reason |
|---|---|---|
| Texture (`artifact.texture` family; runtime category `texture.high_microtexture`) | first-pass implemented | dataset-relative microtexture z-score; real-world calibration still pending |
| Speck / glitter (`artifact.high_frequency_isolated`) | first-pass implemented | residual connected-component signal validated on synthetic bright/dark speck fixtures; real-world calibration still pending |
| Crystalline faceting (`artifact.crystalline_faceting`) | first-pass implemented | pencil grain + smoothness + microtexture rule; crystalline 45-55 grain band still needs better discrimination |
| Oversharpening / halo (`artifact.oversharpening_halo`) | first-pass implemented | USM-residual signal validated on synthetic fixtures; real-world calibration still pending |
| Periodic frequency noise | researched; not approved for implementation | FFT symmetric peaks plus autocorrelation failed to separate positives from intentional repeated patterns and crystalline guard fixtures; postponed until a better discriminator exists |
| Recursive detail (`artifact.recursive_detail`) | not yet investigated | no probe conducted; no partial signal |

Research reports: `benchmarks/results/probe_speck_glitter/` and
`benchmarks/results/probe_oversharpening/`.

### v0.2.0-alpha -- Known limitations

- Analyzer thresholds are uncalibrated against published ground truth.
  Confidence is capped (TextureAnalyzer: 0.70, CrystallineFacetingAnalyzer: 0.45,
  OversharpeningHaloAnalyzer: 0.45, HighFrequencyIsolatedArtifactAnalyzer: 0.45).
  All emit `"calibrated": false` in evidence dicts.
- Crystalline grain 45-55 range has significant TP/FP interleaving;
  a fourth discriminating signal is needed before precision improves.
- TextureAnalyzer z-score thresholds are derived from one private dataset.

---

## Post-v0.2.0-alpha Work

The following items belong in subsequent releases. No timeline is set for any of
these.

### Analyzer improvement (v1.x)

- Fourth discriminating signal for `CrystallineFacetingAnalyzer` -- resolve
  grain 45-55 TP/FP interleaving (spatial coherence, directional frequency
  energy, or micro-edge profile).
- TextureAnalyzer calibration against labeled ground truth.
- Periodic frequency noise: postponed until a better discriminator separates
  synthetic periodic contamination from intentional repeated patterns.
- Research probe for `artifact.recursive_detail` (no signal investigation yet).
- Oversharpening/halo calibration against labeled real-world examples; current
  USM-residual analyzer is synthetic-fixture-backed only.
- High-frequency isolated artifact calibration against labeled real-world
  examples; current residual component analyzer is synthetic-fixture-backed only.

---

## v2: Dataset Forge Clean (future, no timeline)

**Goal:** Apply deterministic, artifact-specific cleanup to images where Findings justify it.

Cleanup is per artifact family  --  not a single generic filter:

| Finding category | Cleanup strategy |
|---|---|
| `artifact.texture` / `texture.high_microtexture` | Edge-preserving denoise |
| `artifact.high_frequency_isolated` | Isolated bright/dark component suppression with local inpainting |
| `artifact.crystalline_faceting` | Mid-frequency band suppression |
| `artifact.recursive_detail` | Frequency-domain attenuation |
| `artifact.oversharpening_halo` | Unsharp-mask reversal; edge deconvolution |

Non-destructive pipeline (absolute):
- Originals are never modified
- Candidates written to separate output folder
- Side-by-side human review required before export
- Final export assembled from individually approved images only

**Prerequisite:** v1 findings are trusted.

---

## v3: Semantic Conservator (future, no timeline)

**Goal:** Reduce GPT fingerprints that deterministic methods cannot reach.

- AI-proposed changes only; never automatic application
- All proposals compared against original using v1 metrics
- Human review at every step
- Dataset Forge remains the decision-maker

**Prerequisite:** v2 deterministic cleanup is validated.

---

## Future Phases (no timeline)

- Caption auditing
- Style consistency analysis
- Duplicate detection (surface in v1 DatasetContext, action in later version)
- Licensing analysis
- Real-world benchmark collections (Flux, SDXL, Ideogram, Midjourney)
- LoRA validation feedback loop

---

## Priority Order (post v0.2.0-alpha)

Calibration against labeled ground truth > fourth crystalline discriminating
signal > new artifact family research > v2 cleanup work.

The inspect vertical slice is shipped. The most valuable next step is
calibrating existing analyzer thresholds with precision/recall/F1 evidence
from labeled ground truth, then resolving the crystalline 45-55 TP/FP problem.
