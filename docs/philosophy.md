# Philosophy

Dataset Forge exists to reduce uncertainty before training, not to automate
judgment.

## Evidence Before Decisions

Analyzers emit findings with categories, evidence, severity, confidence, and
plain-language explanations. A finding is a review signal. It is not proof of
a defect and it is never an automatic instruction to exclude an image.

## Determinism

Given the same files, analyzer versions, profile, and policies, inspection
results are reproducible. `inspection_manifest.json` records that provenance.
Comparison warns when two runs were produced under different conditions.

## Source Images Are Preserved

Inspection, Review Desk decisions, comparison, planning, and preview approval
never modify, move, rename, delete, quarantine, or export source images.

LOCAL_CLASSICAL may read one source image and create a disposable candidate
inside `inspect_output/preview_artifacts/`. That candidate is not a source
image and is never applied to the dataset.

## Human Review Is The Product

The useful outcome is not a score. It is a reviewer who can answer:

1. Which images deserve attention?
2. What evidence caused each image to appear?
3. Is the signal a real concern, accepted style, source encoding, or ambiguity?
4. What decision did the reviewer record?

## Descriptive, Not Grading

Dataset Intelligence organizes existing evidence. It does not produce a
quality score, readiness score, grade, pass/fail label, or AI-written judgment.

## Advisory Preview Planning

Improvement Preview describes a possible operation and provider type. Manual
imports and LOCAL_CLASSICAL generation create isolated candidates for A/B
review only. Approval records intent; it does not execute an improvement.

## Restraint

`No Findings Emitted` is a valid result. `Keep` and `Accepted Style` are valid
human decisions. Dataset Forge earns trust by explaining evidence clearly and
by leaving source datasets alone.

