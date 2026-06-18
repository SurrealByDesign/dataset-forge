# Dataset Forge -- Project Bible

> This document is the project constitution.
> It has higher priority than all previous conversations, implementation decisions, and architectural drafts.
> If a proposed implementation conflicts with this document, explain the conflict instead of implementing.
> Amend this document rarely, deliberately, and only with justification.

---

## Mission

Dataset Forge exists to produce the highest-quality AI training datasets through
evidence-based analysis and minimally invasive intervention.

Its purpose is not to make images prettier.

Its purpose is to understand datasets, identify genuine problems, and recommend
the smallest necessary action to improve training quality while preserving the
original artistic intent.

The ideal outcome for a healthy dataset is a thorough analysis that recommends
no changes at all.

---

## Core Philosophy

- Preserve first.
- Analyze before modifying.
- Prefer deterministic methods.
- Dataset context matters.
- No image should be judged in isolation when meaningful dataset context exists.
- A finding without calibration is an opinion.
- A finding with calibration is evidence.
- Every recommendation must be explainable.
- The least invasive action is preferred.
- The architecture should anticipate growth.
- The implementation should not.

---

## What Dataset Forge Is

Dataset Forge is an AI dataset understanding and quality assurance platform.

Cleanup is only one possible consequence of understanding.

The analyzer is more important than the cleanup.

The report is more important than automation.

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

It should never optimize for making images "look nicer."

It should optimize for producing better training datasets.

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
- Improve LoRA training quality through conservative intervention

If a proposed feature does not make this dataset better, it should not be part of v1.

---

## Version 1: Dataset Forge Inspect

Version 1 is analysis only.

Its pipeline is:

```
Dataset -> DatasetContext -> Analyzer -> Finding -> Report
```

No cleanup is required for v1.

No AI is required for v1.

No UI is required for v1.

Success is measured by producing trustworthy findings.

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

Only uncertain or significant interventions should require user review.

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
- Reports clearly explain recommendations.
- Benchmark tests validate analyzer performance.
- Healthy datasets may legitimately receive zero recommended modifications.

The project succeeds by understanding datasets.

Cleanup is optional.

---

## Development Rule

Before implementing any feature, ask:

> Does this improve understanding of the dataset?

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

Its value should come from producing reliable, explainable, benchmarked
understanding rather than opaque automation.

The software should earn trust through measurement, transparency, and restraint.

The best compliment a user can give Dataset Forge is:

> "It looked carefully at my dataset and correctly decided to leave almost everything alone."
