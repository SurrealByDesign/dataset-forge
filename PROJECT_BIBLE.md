# Dataset Forge -- Project Constitution

This document defines the product rules that should change only through an
explicit product decision.

## Mission

Dataset Forge reduces uncertainty before LoRA or image-dataset training. It
organizes deterministic evidence so a human can decide what belongs in a
dataset and document that decision.

## Rule Zero

**Evidence supports judgment. It does not replace judgment.**

## Product Commitments

- Source datasets are read-only.
- Findings are advisory review signals.
- The Review Desk is the primary human-facing interface.
- Human decisions are explicit and persistent.
- Sidecars are local, inspectable, and versioned.
- Repeated runs are deterministic under the same recorded conditions.
- Dataset Intelligence is descriptive and non-scoring.
- Comparison explains provenance differences rather than hiding them.
- Candidate previews remain isolated, disposable artifacts.
- Approval never implies application or execution.

## Required Language

- Use **No Findings Emitted** or **No current review finding**.
- Never describe that state as proof of training readiness.
- Use **Exclude Candidate**, not language implying deletion.
- Use **Set Aside Intent (no files moved)** for workflow intent.
- Use **candidate preview** for an A/B artifact.
- Keep raw machine IDs visible as secondary technical references.

## Product Boundary

Dataset Forge is not an image editor, dataset cleanup engine, improved-dataset
exporter, training pipeline, cloud review service, or automatic dataset judge.

LOCAL_CLASSICAL is a narrow preview generator. It does not apply its output to
the dataset and does not change this boundary.

## Analyzer Rules

Analyzers must be deterministic, independently testable, policy-blind, and
transparent about evidence and advisory calibration. False-positive contexts
must be documented. New analyzer behavior requires focused fixtures and
real-dataset validation.

## Contract Rules

- Evolve persisted schemas additively where possible.
- Record analyzer, profile, policy, and tool provenance in the manifest.
- Keep Review Desk payload construction separate from HTTP persistence.
- Do not make Review Desk run analyzers or inspect pixels.
- Do not accept browser-supplied candidate filesystem paths.
- Preserve deterministic sorting, hashing, and identifiers.

## Success

Dataset Forge succeeds when a reviewer can quickly understand which images
need attention, why they were surfaced, what decision they made, and where
that decision was saved, without risking the source dataset.
