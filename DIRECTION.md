# Dataset Forge -- Current Direction

## Current Release

**v1.9.2 -- Documentation, Terminology, and Product Polish**

This release changes documentation and product language only. It adds no
analyzers, providers, schemas, workflows, or runtime behavior.

## Product Identity

Dataset Forge is a deterministic, evidence-first, advisory, sidecar-based
workstation for curating LoRA and image datasets. The localhost Review Desk is
the primary interface. Source datasets remain read-only.

The product helps users:

- inspect images and adjacent caption metadata;
- understand advisory findings and dataset-level evidence;
- record human decisions, workflow state, and notes;
- compare inspection runs with provenance warnings;
- document possible improvement operations;
- review isolated manual or LOCAL_CLASSICAL candidate previews.

## Current Boundary

Dataset Forge does not apply preview candidates, modify source images or
captions, export improved datasets, train models, call cloud providers, or
perform automatic cleanup. ComfyUI and Krea are descriptor metadata only.

## Documentation Authority

Start with [README.md](README.md) and [docs/README.md](docs/README.md).
Historical files labeled as design records are not current product plans.

## Release Test

Before accepting a change, ask:

> Does this help a human understand evidence or record a decision while
> preserving the source dataset and current sidecar contracts?

If not, it is outside the current direction.
