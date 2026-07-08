# Dataset Forge -- Current Direction

> This document defines what the project is doing right now.
> Unlike PROJECT_BIBLE.md, it is expected to evolve as milestones are reached.

---

## Current Objective

**v0.23.0-alpha** -- add an Inspection Manifest provenance sidecar while
preserving the same user-facing behavior.

The Review Desk remains the primary human-facing interface. `inspect` now also
writes `inspection_manifest.json` so future tools can understand how an
inspection was performed without changing today's review workflow.

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

- `inspection_manifest.json`
- default inspection profile metadata
- analyzer descriptor metadata for existing analyzers
- analyzer execution/display/triage policies recorded as current defaults
- compatibility metadata for existing inspect and recommendation schemas
- tests proving existing inspect, review, compare, and CLI behavior remain stable

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
- manifest-aware comparison
- hosted/cloud review
- database-backed state

`cleanup/`, `execution/`, `transforms/`, and `exporters/` remain legacy or
future-only code paths. They are not part of the public v0.23 workflow and
should not be expanded for this release.

---

## Primary Reference Dataset

The anthropomorphic character dataset remains the real-world validation set for
review workflow decisions.

Before implementing a feature, ask:

> "Does this help a human safely decide what to do with this real dataset
> before training, without modifying files?"

If no, postpone it.
