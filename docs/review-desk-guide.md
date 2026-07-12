# Review Desk Guide

The Review Desk is Dataset Forge's primary human-facing interface.

## First Screen

**Next Action** points to the highest-priority unresolved review set. **Show
Next Review Set** changes filters and selection only.

Core counts remain visible. Deeper Dataset Intelligence sections are collapsed
by default so the Review Queue stays close to the top of the page.

## Review Queue

Images are grouped into Priority Review, Needs Review, and No Findings Emitted.
Each card shows the filename, triage group, decision, workflow state, finding
labels, severity, confidence, and raw category IDs.

Select a card to open its detail pane. Use filters for decision, workflow,
triage, category, severity, confidence, or filename/evidence text.

## Evidence

Friendly category and analyzer names appear first. Raw IDs remain visible for
traceability. Evidence values are unchanged from inspection sidecars.

Treat explanations as advisory. JPEG compression, natural grain, watercolor
or pencil texture, engraving, hard-edge line art, and intentional highlights
or glitter can resemble analyzer targets.

## Decisions And Workflow

Choose a human decision, then optionally change workflow state and add notes.
The save indicator reports `Saving...`, `Saved`, or `Save failed`.

All decisions save to `review_decisions.json`. **Set Aside Intent (no files
moved)** records workflow intent only. Dataset Forge does not create a folder
or move an image.

## Image Viewer

- Click the large source preview to open the viewer.
- Double-click a thumbnail to open it directly.
- Use Space to toggle the viewer and Escape to close it.
- Use the toolbar for fit, 100% pixels, zoom in, and zoom out.
- Use the mouse wheel to zoom and drag to pan.
- Use Previous/Next or arrow keys to move without leaving the viewer.

## Improvement Preview Workspace

When `improvement_preview.json` exists, the detail pane shows the operation,
rationale, evidence, Provider descriptor, descriptor compatibility, provider
availability, Preview Plan state, and Candidate availability. If a Candidate
Preview exists, the workspace offers side-by-side, original-only, and
candidate-only views.

Without a Candidate Preview, **Accept plan** and **Reject plan** update the
Preview Plan decision only. With a candidate, the controls describe a Candidate
decision. Neither action applies the candidate.

## Browser State

Filters, thumbnail size, selected image, and collapsed sections use browser
session state where supported. Reloading sidecars from another CLI command may
require a page refresh.
