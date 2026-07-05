# Dataset Forge - Roadmap

---

## Product Direction

Dataset Forge is a LoRA Dataset Decision Engine.

Its purpose is to help LoRA dataset builders decide which images are ready to
train, which need review, and which deserve priority attention before training. Every
recommendation must be grounded in deterministic analysis, measurable evidence,
and explainable findings.

Everything after v0.8 should improve one of:

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

### v0.7.0-alpha: Internal Recommendation Summary

**Status:** Released.

Recommendation Summary adds an internal, additive
`dataset-forge/recommendation-summary/v1` schema over existing findings and
DatasetContext image paths.

It uses exactly four deterministic rules:

- analyzer error -> **Priority Review**
- HIGH or CRITICAL finding -> **Priority Review**
- findings from multiple categories -> **Priority Review**
- any other finding -> **Needs Review**
- no findings -> **Ready for Training**

Constraints:

- Internal/additive only.
- No public recommendation command.
- No inspect report wiring.
- No deletion, repair, cleanup, export, or image modification.
- No validation, calibration, or Review Decisions coupling.
- No numeric quality scores or serialized priority fields.
- Recommendations cite existing findings only.
- Existing report fields remain unchanged.

---

### v0.8.0-alpha: User-Visible Recommendation Summary

**Status:** Released.

`dataset-forge inspect` writes additive Recommendation Summary sidecars:

- `recommendation_summary.json`
- `recommendation_summary.md`

The sidecars use the v0.7 four-rule engine unchanged:

- analyzer error -> **Priority Review**
- HIGH or CRITICAL finding -> **Priority Review**
- findings from multiple categories -> **Priority Review**
- any other finding -> **Needs Review**
- no findings -> **Ready for Training**

Constraints:

- No `dataset-forge recommend` command.
- No embedding into `inspection_report.json`.
- No deletion, repair, cleanup, export, regeneration, or image modification.
- No validation, calibration, or Review Decisions coupling.
- No numeric quality scores or serialized priority fields.
- Recommendations cite existing findings only.
- Every Recommendation Summary must be reproducible from
  `inspection_report.json` alone.
- Ready for Training is not a guarantee that an image is artifact-free.

---

### v0.9.0-alpha: Recommendation Markdown Presentation

**Status:** Released.

v0.9 polishes `recommendation_summary.md` into a human-facing review report
without changing recommendation logic or JSON output.

It adds:

- summary counts at the top of the Markdown report
- Priority Review first, then Needs Review
- grouping by artifact family
- filename, recommendation, primary reason, and finding references per review item
- Ready for Training summarized without listing every ready image
- Important Notes and Next Step sections

Constraints:

- No recommendation rule changes.
- No `recommendation_summary.json` schema changes.
- No inspect schema changes.
- No CLI surface changes.
- No analyzer changes.
- No gallery, UI, export, repair, or cleanup.
- No validation, calibration, or Review Decisions coupling.

---

## v0.10: Recommendation Validation

**Goal:** Measure whether decision guidance matches labels and review decisions.

This phase should use Calibration Evidence, Review Decisions, Validation
Dossiers, and the Real-World Validation Corpus to answer:

- How often are review recommendations useful?
- How often are Priority Review recommendations false positives?
- Which artifact families are trustworthy enough for stronger wording?
- Which confidence messages reduce overtrust?

No analyzer thresholds should change until validation evidence supports the
change.

---

## v1.0 Track: Review Experience / Gallery Improvement

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
