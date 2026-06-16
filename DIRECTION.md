# Dataset Forge – Current Direction

> This document defines what the project is doing right now.
> Unlike PROJECT_BIBLE.md, it is expected to evolve as milestones are reached.

---

## Current Objective

Ship **Dataset Forge Inspect** — a complete, working vertical slice:

```
Dataset → DatasetContext → Analyzer → Finding → Report
```

The goal is not architectural perfection. The goal is a trustworthy analysis
report that justifies future cleanup.

---

## Ultimate Objective

Produce cleaner, more consistent LoRA training datasets through evidence-based
analysis and minimally invasive intervention.

Analysis is the foundation. Cleanup is the product.

---

## What Is In Scope Now

- `Finding` dataclass (universal output contract)
- `DatasetContext` dataclass (statistical reference frame)
- `Analyzer` base class and initial analyzers
- JSON and TXT report writers
- CLI: `dataset-forge inspect <path>`
- Calibration benchmarks for each analyzer

---

## What Is Out of Scope for v1

- AI cleanup
- UI
- Caption generation or auditing
- Plugin systems
- Exporters
- Large architectural rewrites
- Any feature without an immediate consumer in the v1 pipeline

Preserve existing out-of-scope code. Do not delete it. Do not expand it.

---

## Definition of Done for v1

```bash
dataset-forge inspect ./dataset
```

Produces a coherent, trustworthy report based on real analyzers and calibrated
evidence. At that point, Dataset Forge stops being an idea and becomes a
working tool.

---

## Primary Reference Dataset

The anthropomorphic character dataset (hotdogs, bananas, pickle wizard, armored
characters — watercolor and colored-pencil style) is the benchmark every
implementation decision is measured against.

Before implementing any feature, ask:

> "Does this make Dataset Forge better at safely analyzing and improving this dataset?"

If no, postpone to v2.
