# Improvement Preview Guide

Improvement Preview is the planning and A/B review layer between human
decisions and any hypothetical future application step. Dataset Forge has no
application or improved-dataset export step.

## Build A Preview Plan

Record Review Desk decisions first, then run:

```powershell
uv run dataset-forge preview <inspect_output>
```

The command writes:

- `improvement_preview.json`
- `improvement_preview.md`

Each record contains the source image reference, human decision, current
findings, recommended operation, rationale, confidence, required provider
type, preview status, and approval state.

## Planning Vocabulary

Operations are stable machine values such as `KEEP`, `MANUAL_CAPTION`,
`REMOVE_DUPLICATE`, `REPLACE_SOURCE`, `REDUCE_HALO`,
`REDUCE_ENCODING_ARTIFACTS`, and `NO_ACTION`.

They describe planning intent. For example, `REMOVE_DUPLICATE` does not remove
anything and `REPLACE_SOURCE` does not replace a file.

## Manual Candidate Import

```powershell
uv run dataset-forge preview-import <inspect_output> <source-image> <candidate-image>
```

Dataset Forge validates the candidate, copies its existing bytes into the
isolated preview workspace, records hashes and metadata, and leaves both the
source and original candidate untouched.

## Local Classical Generation

```powershell
uv run dataset-forge preview-generate <inspect_output> <source-image>
```

This works only when the record explicitly requests a supported
`LOCAL_CLASSICAL` operation. Current operations are `REDUCE_HALO` and
`REDUCE_ENCODING_ARTIFACTS`. Pillow and NumPy produce deterministic disposable
PNG candidates with explicit parameters and provenance.

## Artifact Storage

Candidates are stored below:

```text
inspect_output/
  preview_artifacts.json
  preview_artifacts/
    preview-<stable-id>/
      candidate-<hash>.png
```

Browser requests use allow-listed artifact IDs, not arbitrary filesystem paths.

## Approval

The Review Desk can record `NOT_REQUESTED`, `APPROVED`, or `REJECTED` in the
preview plan. When no Candidate Preview exists, the UI presents these as
**Accept plan** and **Reject plan**. When a candidate exists, it presents a
Candidate decision. These choices update planning metadata only; they do not
execute an operation, export an image, or replace the source.

## Regenerating Plans

`dataset-forge preview` rebuilds planning records from current sidecars.
Regenerating after decisions or findings change can change record identity and
may make an older candidate unrelated to the new plan. Review the plan and
candidate association after regeneration.
