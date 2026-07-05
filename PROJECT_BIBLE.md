# Dataset Forge -- Project Bible

> This document is the project constitution.
> It has higher priority than all previous conversations, implementation decisions, and architectural drafts.
> If a proposed implementation conflicts with this document, explain the conflict instead of implementing.
> Amend this document rarely, deliberately, and only with justification.

---

## Mission

Rule Zero: Dataset Forge exists to reduce uncertainty, not automate judgment.

Dataset Forge helps LoRA dataset builders decide which images are ready to
train, which need review, and which should be excluded from training. Every
recommendation must be grounded in deterministic analysis, measurable evidence,
and explainable findings.

Its purpose is not to make images prettier.

Its purpose is to understand datasets, identify genuine problems, and help the
user make better training-set decisions while preserving original artistic
intent.

The ideal outcome for a healthy dataset is a thorough analysis that recommends
no changes at all.

---

## Core Philosophy

- Source images are sacred.
- Evidence comes before recommendations.
- Recommendations are advisory.
- Exclusion is not deletion.
- Healthy images should stay quiet.
- Prefer deterministic methods.
- Dataset context matters.
- No image should be judged in isolation when meaningful dataset context exists.
- A finding without calibration is an opinion.
- A finding with calibration is evidence.
- Every recommendation must be explainable.
- Benchmarks are product assets, not test chores.
- The decision is the product; gallery and report are interfaces.
- The architecture should anticipate growth.
- The implementation should not.

---

## What Dataset Forge Is

Dataset Forge is a LoRA Dataset Decision Engine.

It helps users decide which images are ready to train, which images need human
review, and which images should be excluded from training.

Inspection is the evidence layer.

The analyzer is more important than cleanup.

The decision is more important than automation.

Dataset Forge's long-term purpose is deterministic, evidence-backed dataset
improvement. Cleanup may eventually belong in the product, but only after the
tool has earned trust as a decision engine.

The only acceptable long-term cleanup path is:

```
Inspect
-> Recommend
-> Explain
-> Human Review
-> Persistent Decisions
-> Dataset Comparison
-> Cleanup Planning
-> Optional Cleanup Execution
```

The forbidden path is:

```
Inspect
-> Automatically Clean
```

This is not a promise to build cleanup now. It is a constraint on any future
cleanup work.

---

## What Dataset Forge Is Not

Dataset Forge is not:

- an image enhancer
- a Photoshop replacement
- a one-click AI cleanup tool
- a beauty filter
- a generic upscaler
- a prompt generator
- a caption generator
- a UI-first application
- an automatic dataset judge
- an automatic deletion tool

It should never optimize for making images "look nicer."

It should optimize for reducing uncertainty before training.

---

## Primary Use Case

The first and most important use case is improving the existing anthropomorphic
training dataset: hotdogs, bananas, pickle wizard, armored characters  --  watercolor
and colored-pencil style with GPT-style artifacts including glitter, crystalline
microtexture, speckle, oversharpening, periodic noise, and edge halos.

Specifically:

- Detect GPT-style glitter
- Detect crystalline microtexture
- Detect periodic frequency contamination
- Detect oversharpening
- Detect edge halos
- Detect inconsistent texture treatment
- Preserve watercolor and colored-pencil appearance
- Leave healthy images untouched
- Improve LoRA training quality through conservative dataset decisions

If a proposed feature does not make this dataset better, it should not be part of v1.

---

## Version 1: Dataset Forge Decision Engine

Version 1 is read-only decision support.

Its pipeline is:

```
Dataset -> DatasetContext -> Analyzer -> Finding -> Decision Guidance -> Report / Gallery
```

No cleanup is required for v1.

No AI is required for v1.

No source-image modification is allowed in v1.

Success is measured by producing trustworthy Ready / Review /
Exclude-from-training guidance backed by findings.

---

## DatasetContext

DatasetContext is the statistical understanding of the dataset.

It exists only to help analyzers make better decisions.

It should remain minimal in v1.

Initially it should contain:

- dataset metadata
- resolution statistics
- aspect ratio statistics
- texture metric distributions
- frequency metric distributions
- duplicate hashes
- schema version
- analyzer versions

Future additions must be additive rather than disruptive.

Do not over-engineer this object.

---

## Finding

Finding is the universal output contract.

Every analyzer emits Findings.

Everything downstream consumes Findings.

A Finding should contain:

- analyzer
- category
- severity
- confidence
- estimated false-positive rate
- benchmark version
- evidence
- explanation
- recommendation

If a future analyzer can be added without changing the Finding schema,
the architecture is succeeding.

---

## Analyzer Design

Analyzers must:

- operate independently
- consume DatasetContext
- emit Findings
- be benchmarked
- be calibrated
- be individually testable

Analyzer-specific logic should never leak into the core architecture.

---

## Benchmarks

Benchmarks are not optional.

Every analyzer should be validated against benchmark data.

Synthetic benchmarks should exist for:

- glitter
- periodic noise
- oversharpening
- speckling
- halo artifacts

Real-world benchmark collections can eventually exist for:

- Flux
- SDXL
- Ideogram
- Midjourney
- other generators

Benchmarks are first-class project assets.

---

## Approval Philosophy

The project should use exception-based approval.

Healthy images should pass automatically.

Only uncertain or significant training-set decisions should require user review.

Users should never be forced to manually inspect hundreds of healthy images.

---

## AI Policy

AI is not a foundational dependency.

The architecture should allow AI modules in the future.

Version 1 should not require AI.

Deterministic solutions should always be attempted first.

---

## Scope Management

The architecture should anticipate growth.

The implementation should not.

Future possibilities include:

- caption auditing
- duplicate detection
- style consistency analysis
- licensing analysis
- additional analyzers

These should not delay shipping the first working version.

---

## Definition of Success

Version 1 succeeds if:

- DatasetContext is built correctly.
- Analyzers emit calibrated Findings.
- Reports and galleries clearly explain decision guidance.
- Benchmark tests validate analyzer performance.
- Healthy datasets may legitimately receive zero review or exclusion candidates.

The project succeeds by reducing uncertainty before training.

Cleanup is future-only and optional. If it is ever implemented, it must be
justified by inspection evidence, recommendation explanations, human review,
persistent decisions, and comparison outputs. It must never be automatic.

---

## Development Rule

Before implementing any feature, ask:

> Does this improve the user's ability to decide what belongs in the training set?

If not, it probably does not belong in Dataset Forge.

---

## Amendment Process

PROJECT_BIBLE.md should not be modified casually.

Before changing the Bible, answer:

1. Does this solve a real problem encountered during implementation?
2. Can the same goal be achieved without changing the Bible?
3. Will this make the current anthropomorph dataset workflow better?
4. Does this increase implementation complexity?
5. Does this delay shipping v1?

If the answer to (5) is yes, the amendment should be strongly questioned.

---

## Long-Term Vision

Dataset Forge should become the trusted evidence engine for AI training datasets.

The long-term product may grow from evidence-backed decisions into
evidence-backed dataset improvement, including cleanup planning and optional
cleanup execution. That future must preserve the same rule: source images are
sacred, human intent is explicit, and automatic cleanup after inspection alone
is never acceptable.

Its value should come from producing reliable, explainable, benchmarked
training-set decisions rather than opaque automation.

The software should earn trust through measurement, transparency, and restraint.

The best compliment a user can give Dataset Forge is:

> "It showed me exactly which images needed attention before training, and left the rest alone."
