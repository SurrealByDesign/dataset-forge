# Dataset Forge -- Why

LoRA training reproduces patterns from its dataset, including patterns the
creator did not intend. Dataset Forge exists to make those patterns easier to
inspect before training.

## Why Evidence First

A label such as "bad image" is not useful. A finding that names an analyzer,
category, severity, confidence, measurable evidence, likely false-positive
contexts, and a review action gives the creator something they can evaluate.

## Why Deterministic

Deterministic analysis is auditable and reproducible. The inspection manifest
records tool version, analyzer versions, profile, and effective policies so a
later comparison can explain when two runs differ.

## Why Dataset Context

Many image measurements are meaningful only relative to the dataset. Context
helps distinguish a genuine outlier from an intentional style shared by every
image.

## Why Independent Analyzer Families

Microtexture, crystalline faceting, halos, isolated specks, source encoding,
duplicates, and caption metadata have different causes and false-positive
patterns. Keeping analyzers independent prevents one opaque score from
pretending to represent all dataset concerns.

## Why The Review Desk

Reports preserve evidence, but image curation is visual work. The Review Desk
puts images, findings, filters, decisions, notes, and dataset context in one
local interface. It saves explicit human judgment rather than silently acting.

## Why No Quality Score

A single score hides evidence, weighting choices, and uncertainty. Dataset
Intelligence therefore reports counts, concentrations, coverage, provenance,
and remaining review work without grading the dataset.

## Why Preview Candidates Are Isolated

Sometimes a reviewer needs to compare a possible alternative with the source.
Manual import and LOCAL_CLASSICAL generation create disposable candidates
inside the inspect-output workspace. Isolation makes A/B review possible while
keeping the dataset unchanged.

## Why Restraint Matters

Watercolor texture, pencil grain, hard edges, glitter, and JPEG artifacts can
resemble analyzer targets. A trustworthy tool must make uncertainty visible,
support Accepted Style decisions, and accept that no action can be the right
outcome.
