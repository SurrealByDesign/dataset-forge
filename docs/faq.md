# FAQ

## Does Dataset Forge change my dataset?

No. Source images and caption sidecars are never modified, moved, renamed,
deleted, quarantined, or exported.

## Is `No Findings Emitted` the same as ready for training?

No. It means only that current analyzers emitted no review finding.

## Are findings defects?

No. They are advisory review signals. Intentional style and source encoding can
produce similar evidence.

## Where are decisions saved?

Review decisions, workflow state, and notes are saved to
`review_decisions.json` using schema v2.

## Does Set Aside Intent move an image?

No. It records workflow intent only. No folder is created and no file moves.

## What does preview approval do?

It updates approval state in `improvement_preview.json`. It does not apply,
export, or replace an image.

## Does LOCAL_CLASSICAL clean or repair images?

No. It produces conservative disposable preview candidates for A/B review.

## Are ComfyUI and Krea supported?

No. Static descriptors exist for contract compatibility only. There are no
integrations, API calls, credentials, or provider execution paths.

## Why did one image receive several findings?

Analyzers are independent review signals. The Review Desk nests all findings
under the image so the reviewer can interpret them together.

## Why does the preview plan show only one operation?

The current deterministic planner selects one operation per image using fixed
precedence. Review the complete evidence list; the operation is advisory and
may not represent every finding family.

## Can I compare two inspections made with different versions?

Yes. Comparison still runs and reports manifest compatibility warnings.

## Is there a quality or readiness score?

No. Dataset Intelligence is descriptive and non-scoring.

