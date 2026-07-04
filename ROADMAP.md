# Dataset Forge - Roadmap

---

## Product Direction

Dataset Forge is a LoRA Dataset Decision Engine.

Its purpose is to help LoRA dataset builders decide which images are ready to
train, which need review, and which should be excluded from training. Every
recommendation must be grounded in deterministic analysis, measurable evidence,
and explainable findings.

Everything after v0.6 should improve one of:

- decision quality
- confidence communication
- false-positive reduction
- review efficiency
- benchmark and corpus evidence

Repair, cleanup, and export remain future-only possibilities, not assumed next
steps.

---

## Released Foundations

### v0.1.0-alpha: Inspect Foundation

**Status:** Released.

- Stable Finding and Analyzer contracts.
- `dataset-forge inspect`.
- JSON/TXT inspection reports.
- Optional gallery output.
- First public benchmark framework.

### v0.2.0-alpha: Four-Analyzer Inspect Platform

**Status:** Released.

**Pipeline:** `Dataset -> DatasetContext -> Analyzer -> Finding -> Aggregation -> Dataset Summary -> Review Queue -> Report`

| Component | Status |
|---|---|
| `Finding` dataclass | shipped |
| `DatasetContext` dataclass | shipped |
| `Analyzer` base class | shipped |
| `TextureAnalyzer` -- microtexture, watercolor smoothness signal | shipped; first-pass uncalibrated |
| `CrystallineFacetingAnalyzer` -- pencil_grain + texture_consistency | shipped; first-pass uncalibrated |
| `OversharpeningHaloAnalyzer` -- edge-localized USM residuals | shipped; first-pass uncalibrated |
| `HighFrequencyIsolatedArtifactAnalyzer` -- sparse residual components | shipped; first-pass uncalibrated |
| Dataset Summary + Review Queue | shipped; advisory |
| Public benchmark suite | shipped |
| Public CLI surface locked to inspect-only | shipped |

v0.2.0-alpha did not include cleanup, repair, regeneration, AI editing, UI,
captions, plugins, or exporters.

### v0.3.0-alpha: Calibration Evidence

**Status:** Released.

Calibration Evidence compares an existing `inspection_report.json` against a
small ground-truth label file and reports:

- per-analyzer TP / FP / FN / TN
- precision, recall, F1, and false-positive rate
- category-level summaries
- schema-versioned JSON output

This is internal evidence tooling. It does not change analyzer thresholds or
expand the public CLI.

### v0.4.0-alpha: Review Decisions

**Status:** Released.

Review Decisions record human intent over inspected images and finding
categories:

- confirmed artifacts
- false positives
- acceptable style
- needs review
- ignored images/categories
- locked images/categories

This is internal decision-quality evidence. It does not plan or apply dataset
changes.

### v0.5.0-alpha: Validation Dossiers

**Status:** Released.

Validation Dossiers combine:

- an existing `inspection_report.json`
- schema-versioned calibration labels
- optional Review Decisions

The output summarizes per-analyzer and per-category reliability, false-positive
and false-negative examples, review disagreement, and threshold-review
candidates.

This is a validation layer for confidence communication and future
recommendation quality. It does not implement repair planning.

### v0.6.0-alpha: Real-World Validation Corpus

**Status:** Released.

The Real-World Validation Corpus framework defines how legally safe, labeled
real-world validation datasets should be organized.

It adds:

- a schema-versioned corpus manifest
- committed placeholder methodology fixtures
- Calibration Evidence label compatibility checks
- optional private/local fixture skipping
- public rules for what can and cannot be committed

The corpus is methodology only. It does not change analyzer thresholds,
implement recommendations, or expand the public CLI.

---

## v0.7: Recommendation / Decision Summary Layer

**Goal:** Turn existing findings, Dataset Summary, and Review Queue into
advisory training-set guidance.

Proposed decision language:

- **Ready to train** -- no concerning findings.
- **Needs review** -- evidence suggests a human should inspect before training.
- **Priority review / exclude-from-training candidate** -- stronger or multiple
  findings suggest the image may not belong in the training set unless the
  artifact is intentional.

Constraints:

- No deletion.
- No repair.
- No cleanup.
- No export.
- No image modification.
- Exclusion is not deletion.
- Recommendations must cite underlying findings and evidence.
- Uncalibrated signals must be labeled clearly.
- Existing report fields remain backward-compatible.

---

## v0.8: Recommendation Validation

**Goal:** Measure whether decision guidance matches labels and review decisions.

This phase should use Calibration Evidence, Review Decisions, Validation
Dossiers, and the Real-World Validation Corpus to answer:

- How often are review recommendations useful?
- How often are exclude-from-training candidates false positives?
- Which artifact families are trustworthy enough for stronger wording?
- Which confidence messages reduce overtrust?

No analyzer thresholds should change until validation evidence supports the
change.

---

## v0.9: Review Experience / Gallery Improvement

**Goal:** Make human review fast enough that users run Dataset Forge before
every LoRA.

Focus areas:

- Decision-oriented gallery sections.
- Evidence summaries that are useful at thumbnail and full-image scale.
- Clear confidence wording.
- Better grouping by reason for review.
- Easy handoff from terminal summary to visual review.

Still out of scope: cleanup, repair, export, UI-first redesign, and AI editing.

---

## v1.0: Stable LoRA Dataset Decision Engine

**Goal:** Ship a stable, read-only product that helps users decide what belongs
in a LoRA training set before training.

v1.0 should include:

- Stable `inspect` behavior.
- Stable decision guidance.
- Evidence-backed Ready / Review / Exclude-from-training candidate language.
- Clear calibration and confidence communication.
- Public benchmark and corpus evidence.
- Reports and gallery that reduce review burden.
- No source-image modification.

v1.0 succeeds when a user can say:

> "Instead of reviewing 400 images, Dataset Forge showed me the handful that
> actually needed attention."

---

## Analyzer Improvement

Analyzer work should be driven by decision quality, not novelty.

Priority areas:

- Populate the Real-World Validation Corpus with legally safe public-domain,
  CC0, or otherwise redistributable LoRA/image examples before claiming
  real-world reliability.
- Use Validation Dossiers on labeled real-world datasets before changing
  thresholds or adding analyzer families.
- Calibrate TextureAnalyzer against labeled ground truth.
- Resolve the CrystallineFacetingAnalyzer grain 45-55 TP/FP interleaving with
  evidence from a fourth discriminating signal.
- Keep Periodic Frequency Noise postponed until a better discriminator separates
  synthetic contamination from intentional repeated patterns.

---

## Future Vision Only

The following may become valuable only after decision guidance is reliable:

- Non-destructive export of human-approved training sets.
- Repair planning.
- Deterministic repair candidates.
- Additional analyzers.
- Dataset comparison.
- Lightweight review UI.
- LoRA validation feedback loop.

These are not assumed next steps. They require evidence that Dataset Forge can
reliably identify images that deserve intervention.

---

## Why Dataset Forge does not repair images yet

Repair is deferred until the tool can reliably identify images that deserve
intervention. A repair workflow built on weak or uncalibrated recommendations
would damage user trust and risk altering images that should be left alone.

Dataset Forge should first prove that it can reduce uncertainty: find the
images worth reviewing, explain the evidence, and communicate confidence
honestly. Only then should repair, cleanup, or export be reconsidered.
