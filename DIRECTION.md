# Dataset Forge -- Current Direction

> This document defines what the project is doing right now.
> Unlike PROJECT_BIBLE.md, it is expected to evolve as milestones are reached.

---

## Current Objective

**v0.21.0-alpha** -- make the local Review Desk a clearer dataset curation
workstation by adding a Dataset Overview and deterministic next-action
guidance.

The Review Desk remains the primary human-facing interface. It consumes
existing inspect sidecars, shows review progress, explains which images need
attention, and records human decisions in `review_decisions.json`.

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

- Dataset Overview inside the localhost Review Desk
- review progress counts and decision counts
- next-action guidance based only on existing sidecars
- top finding category summaries
- analyzer coverage summaries
- clearer read-only and sidecar-driven scope language
- documentation cleanup that reflects the current review-first direction

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
- hosted/cloud review
- database-backed state

`cleanup/`, `execution/`, `transforms/`, and `exporters/` remain legacy or
future-only code paths. They are not part of the public v0.21 workflow and
should not be expanded for this release.

---

## Primary Reference Dataset

The anthropomorphic character dataset remains the real-world validation set for
review workflow decisions.

Before implementing a feature, ask:

> "Does this help a human safely decide what to do with this real dataset
> before training, without modifying files?"

If no, postpone it.
