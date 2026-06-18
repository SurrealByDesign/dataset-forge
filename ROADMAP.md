# Dataset Forge - Roadmap

---

## Version 1: Dataset Forge Inspect (current)

**Goal:** Produce explainable, read-only findings for image datasets, with
calibration driven by reviewer ground truth.

**Pipeline:** `Dataset -> DatasetContext -> Analyzer -> Finding -> Report`

### v1 Milestones

| Milestone | Status |
|---|---|
| `Finding` dataclass defined | done |
| `DatasetContext` dataclass defined | done |
| `Analyzer` base class defined | done |
| Texture analyzer (microtexture, speckle, watercolor smoothness signal) | done |
| JSON report writer | done |
| TXT report writer | done |
| CLI: `dataset-forge inspect <path>` | done |
| Inspect gallery output | done |
| Labeling tool for `ground_truth.json` | done |
| Decision review tool for `decision_review.json` | done |
| Crystalline faceting analyzer (`artifact.crystalline_faceting`)  --  pencil_grain + texture_consistency signal | done  --  first-pass uncalibrated; 9/11 known missed cases caught |
| Speck / glitter analyzer (`artifact.speck`)  --  independent speck threshold | pending |
| Frequency / periodic noise analyzer (`artifact.recursive_detail`) | pending |
| Sharpness / halo analyzer (`artifact.oversharpening`) | pending |
| Calibration metrics from ground truth | done |
| Calibration benchmark pass | in progress  --  crystalline detector live, FP review needed |

**v1 does not include:** cleanup, AI, UI, captions, plugins, exporters.

---

## Version 2: Dataset Forge Clean (future)

**Goal:** Apply deterministic, artifact-specific cleanup to images where Findings justify it.

Cleanup is per artifact family  --  not a single generic filter:

| Finding category | Cleanup strategy |
|---|---|
| `artifact.microtexture` | Edge-preserving denoise |
| `artifact.speck` | Isolated bright-pixel suppression with local inpainting |
| `artifact.crystalline_faceting` | Mid-frequency band suppression |
| `artifact.recursive_detail` | Frequency-domain attenuation |
| `artifact.oversharpening` | Unsharp-mask reversal; edge deconvolution |

Non-destructive pipeline (absolute):
- Originals are never modified
- Candidates written to separate output folder
- Side-by-side human review required before export
- Final export assembled from individually approved images only

**Prerequisite:** v1 findings are trusted.

---

## Version 3: Semantic Conservator (future)

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

## What Blocks v1

1. **Calibration evidence** - reviewer labels and decision reviews are needed
   before analyzer thresholds can be trusted. The tools now write local
   `ground_truth.json` and `decision_review.json` artifacts, which are generated
   review data and should remain untracked.

2. **Benchmark coverage** - local generated assets cover several artifact
   classes, but duplicate detection, halo-only samples, multi-strength
   calibration sets, and real-sample provenance are still missing.

---

## Priority Order

Reviewer-backed calibration > new analyzers > future cleanup work.

The v1 vertical slice exists; the most important next step is turning review
labels into precision/recall/F1 so thresholds can be adjusted with evidence.
