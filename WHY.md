# Dataset Forge – Why

This document explains why Dataset Forge exists and why major architectural
decisions were made the way they were. Future developers should understand
the reasoning, not just the implementation.

---

## Why This Project Exists

LoRA training quality is directly limited by dataset quality.

Most LoRA practitioners focus on prompt engineering and training parameters.
The dataset itself — what images are included, what artifacts they carry,
whether they are internally consistent — receives far less attention.

The existing anthropomorphic character dataset (hotdogs, bananas, pickle wizard,
armored characters — watercolor and colored-pencil style) was generated primarily
by GPT-based image tools. These images carry GPT fingerprints: crystalline
microtexture, glitter-like speckle, periodic frequency contamination,
oversharpening, and edge halos. The LoRA learns these fingerprints alongside
the intended artistic style.

The goal is not to produce prettier images. The goal is to give the LoRA
fewer false patterns to learn.

Dataset Forge exists because no existing tool approaches this problem with
the required care: evidence-based, explainable, non-destructive, and willing
to recommend leaving most images alone.

---

## Why Analysis Before Cleanup

Cleanup without analysis is guesswork.

The first question is not "how do I fix this image" but "does this image
need fixing, and why, and how confident are we?"

A finding without calibration is an opinion. A finding with calibration is evidence.

Dataset Forge is built around that distinction.

---

## Why DatasetContext

Images cannot be correctly judged in isolation.

An image with high microtexture density might be healthy if the whole dataset
has high microtexture. The same score in a lower-texture dataset is a problem.

DatasetContext supplies the statistical reference frame that makes per-image
findings meaningful. Without it, thresholds are arbitrary. With it, findings
are calibrated against the actual dataset.

---

## Why Finding Is the Universal Contract

A stable, typed Finding schema means:

- Analyzers can be added without changing downstream consumers
- Reports can be generated from any combination of analyzers
- Benchmarks can validate each analyzer independently
- Future cleanup modules consume the same output as reports

If Finding changes, everything changes. So it is designed to be stable
and extended only additively.

---

## Why Deterministic Before AI

Deterministic methods are:
- auditable — you can inspect every decision
- reproducible — same input, same output
- fast — no inference cost
- explainable — you can say exactly why a finding was made

AI methods may eventually solve problems deterministic methods cannot
(recursively embedded microfacet structure, semantic simplification of
generated textures). But they should be introduced only when deterministic
methods demonstrably fall short, not as a first resort.

---

## Why Version 1 Is Analysis Only

Cleanup is the consequence of understanding, not the goal.

Building cleanup before the analysis is solid means building cleanup on
guesswork. The right order is:

1. Understand what is wrong and why (v1)
2. Decide whether to act (v1 output)
3. Act deterministically where appropriate (future)
4. Act with AI where determinism is insufficient (future)

Skipping step 1 produces tools that do things to images. Dataset Forge
should be a tool that understands datasets.

---

## Why Benchmarks Are Mandatory

Thresholds without validation are arbitrary.

A benchmark for glitter detection tells you: at this threshold, you catch
this fraction of true positives and produce this many false positives.
Without a benchmark, you don't know either number.

Benchmarks are how the project earns trust.

---

## Why the Scope Is Deliberately Narrow for v1

The natural expansion pressure on a tool like this is enormous:
- add captions
- add upscaling
- add style transfer
- add UI
- add AI cleanup
- add duplicate detection

Each individual addition seems reasonable. Collectively, they prevent
shipping anything.

Version 1 is a vertical slice: one complete path from dataset to calibrated
report. That slice must work before anything else is added.

---

## Why Artifact Families Are Treated Separately

During calibration review of the anthropomorph dataset, eleven images the
analyzer marked CLEAN were flagged by the human reviewer. Investigation showed
that these images shared a specific artifact — crystalline surface faceting,
angular micro-polygon shading — that is distinct from the elevated high-frequency
noise the microtexture analyzer was measuring.

Diagnostic analysis across all seven available texture metrics confirmed the
distinction with statistical evidence:

- `highlight_speck`: Cohen's d = −0.01 against the clean population. No signal.
  The speck metric counts near-white isolated pixels. Crystalline faceting
  produces mid-frequency angular texture, not bright isolated points.
- `pencil_grain`: Cohen's d = +0.80. Strong signal. Pencil grain measures
  medium-frequency texture uniformly distributed across the image — which is
  exactly what faceted surfaces produce.
- `microtexture_density`: Cohen's d = +0.99. The primary signal, but the
  current threshold is too conservative to catch the faceting population.

The lesson: using a single score as a proxy for all GPT contamination produces
a system that is well-calibrated for one artifact family and blind to others.
Treating them separately — each with its own analyzer, evidence schema, and
threshold — is not premature abstraction. It is the correct response to
empirical evidence that they are different phenomena.

---

## Why Cleanup Must Be Artifact-Specific

A generic texture smoothing filter applied across all findings would damage
healthy image characteristics:

- Legitimate pencil grain is indistinguishable from GPT microtexture by any
  smoothing filter that does not understand what it is removing.
- Intentional specular highlights (eyes, metallic surfaces, water) are
  destroyed by speck-suppression logic targeting glitter artifacts.
- Genuine watercolor edge variation is harmed by halo-removal filters.

The cleanup strategy must be derived from the finding category, not applied
uniformly. This is why Finding carries a `category` field, not just a severity.

---

## Why "Leave Healthy Images Alone" Is a Design Goal

Most tools measure success by the number of changes made.
Dataset Forge measures success by the quality of findings.

A run that correctly identifies 5 images with glitter artifacts and
correctly leaves 95 images untouched is a success.

A run that applies mild cleanup to all 100 images without evidence
is a failure, even if the images look slightly better.

LEAVE_ALONE is not a fallback. It is a first-class, evidence-based outcome.
