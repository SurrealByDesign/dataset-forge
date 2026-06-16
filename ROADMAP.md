# Dataset Forge – Roadmap

---

## Version 1: Dataset Forge Inspect (current)

**Goal:** Produce calibrated, explainable findings for the anthropomorphic dataset.

**Pipeline:** `Dataset → DatasetContext → Analyzer → Finding → Report`

### v1 Milestones

| Milestone | Status |
|---|---|
| `Finding` dataclass defined | pending |
| `DatasetContext` dataclass defined | pending |
| `Analyzer` base class defined | pending |
| Frequency analyzer (periodic noise, microtexture) | in progress |
| Glitter analyzer | pending |
| Sharpness / halo analyzer | pending |
| Synthetic benchmarks (glitter, noise, sharpness, speckle, halo) | blocked |
| JSON report writer | next |
| TXT report writer | pending |
| CLI: `dataset-forge inspect <path>` | pending |
| Calibration benchmark pass | blocked |

**v1 does not include:** cleanup, AI, UI, captions, plugins, exporters.

---

## Version 2: Dataset Forge Clean (future)

**Goal:** Apply deterministic cleanup to images where Findings justify it.

- Speck removal
- Edge-preserving smoothing
- Frequency artifact suppression
- Acceptance checks against originals
- Dry-run / preview mode
- No originals overwritten

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

1. **Calibration benchmarks** — synthetic images with known artifact levels
   needed to validate analyzer thresholds before trusting findings.

2. **`Finding` and `DatasetContext` formalization** — `ImageEvidence` in
   `evidence.py` is a predecessor but does not match the Bible schema.

---

## Priority Order

Shipping a complete v1 vertical slice > expanding architecture.

The benchmark blocker is the most important thing to resolve.
