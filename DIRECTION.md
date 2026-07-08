# Dataset Forge -- Current Direction

> This document defines what the project is doing right now.
> Unlike PROJECT_BIBLE.md, it is expected to evolve as milestones are reached.

---

## Current Objective

**v0.24.0-alpha** -- make Dataset Comparison manifest-aware while preserving
the same user-facing behavior.

The Review Desk remains the primary human-facing interface. `compare` now reads
optional `inspection_manifest.json` sidecars and explains whether two inspect
outputs were produced under comparable conditions.

---

## Product Identity

Dataset Forge is an evidence-first, deterministic, non-destructive LoRA
dataset curation workstation.

It helps users:

- inspect image datasets
- understand evidence
- make human review decisions
- document those decisions before training

The product reduces uncertainty. It does not automate judgment.

---

## What Is In Scope Now

- advisory `inspection_compatibility` in `comparison_summary.json`
- an Inspection Compatibility section in `comparison_summary.md`
- warnings for missing manifests and manifest differences
- compatibility checks for manifest schema, profile, tool version, analyzer
  participation, analyzer versions, display policy, and triage policy
- tests proving existing comparison fields and behavior remain stable

---

## What Is Out of Scope Now

- cleanup
- execution
- repair
- export
- source-image modification
- moving, copying, deleting, renaming, or quarantining files
- quarantine folder creation
- analyzer threshold changes
- new analyzer families
- configurable review signals
- profile UI or analyzer toggles
- blocking comparison behavior
- hosted/cloud review
- database-backed state

`cleanup/`, `execution/`, `transforms/`, and `exporters/` remain legacy or
future-only code paths. They are not part of the public v0.24 workflow and
should not be expanded for this release.

---

## Primary Reference Dataset

The anthropomorphic character dataset remains the real-world validation set for
review workflow decisions.

Before implementing a feature, ask:

> "Does this help a human safely decide what to do with this real dataset
> before training, without modifying files?"

If no, postpone it.
