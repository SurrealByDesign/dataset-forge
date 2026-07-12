# Dataset Forge -- Product Brief

> Current as of v1.9.3. For first-time use, start with
> [Getting Started](getting-started.md).

Dataset Forge is a local LoRA/image dataset curation workstation. It inspects
images and caption sidecars, organizes deterministic evidence, and lets a
human record decisions in the browser Review Desk.

## Primary User

A LoRA creator or technical artist who wants to understand a dataset before
training without allowing a tool to change the source files.

## Core Jobs

1. Find images that deserve attention.
2. Explain why each image was surfaced.
3. Preserve raw evidence and provenance.
4. Record human decisions and notes.
5. Compare runs under potentially different inspection conditions.
6. Review advisory operation plans and isolated candidate previews.

## Product Outputs

The product writes versioned JSON sidecars, readable Markdown/text reports,
review decisions, and optional isolated preview artifacts. Dataset Intelligence
is computed in the Review Desk and is not persisted as another sidecar.

## Safety

Source images and caption sidecars are never modified, moved, renamed, deleted,
quarantined, or exported. There is no improvement-application workflow.

## Success Measure

A first-time reviewer can identify what to review next, understand the
evidence, record a decision, and find the saved sidecar without learning the
internal architecture.
