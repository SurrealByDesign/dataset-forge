# Dataset Forge

**v0.25.0-alpha** -- adds Dataset Intelligence to the local Review Desk while preserving read-only review workflows.

Dataset Forge helps you decide which images belong in your LoRA before you train.

It is for LoRA dataset builders who want evidence-backed answers to three
questions:

- Which images emitted no current review findings?
- Which images need human review?
- Which images deserve priority attention before training?

Every recommendation is grounded in deterministic analysis, measurable
evidence, and explainable findings.

```text
Raw Dataset
-> Inspect
-> Recommendations
-> Review
-> Human Decisions
-> Compare
-> Improvement Planning
-> Improvement Preview
-> Train
```

**v0.25.0-alpha is read-only decision support.** Dataset Forge reads your
dataset and writes reports beside it. It never modifies source images. There is
still no cleanup, repair, export, hosted web app, cloud service, plugins, or
new analyzer family in this release. v0.25 adds Dataset Intelligence inside
the Review Desk: deterministic, sidecar-derived review status, evidence
summary, analyzer contribution, dataset coverage, review guidance, and
provenance. It does not score, grade, pass, or fail datasets.

---

## 60-Second Quick Start

Install:

```text
git clone https://github.com/surrealbydesign/dataset-forge.git
cd dataset-forge
uv sync
```

Inspect a dataset:

```text
uv run dataset-forge inspect my_dataset/
```

Open the local Review Desk first:

```text
uv run dataset-forge review my_dataset/inspect_output/
```

Expected outputs:

| Output | What to do with it |
|---|---|
| `recommendation_summary.md` | Start here. Review Priority Review, then Needs Review. |
| `inspection_report.txt` | Read detailed findings in plain text. |
| `inspection_report.json` | Machine-readable evidence and findings. |
| `recommendation_summary.json` | Machine-readable No Findings Emitted / Needs Review / Priority Review sidecar. |
| `triage_dossiers.md` | Image-level triage dossiers with findings nested under each image. |
| `triage_dossiers.json` | Machine-readable triage dossier sidecar. |
| `inspection_manifest.json` | Provenance sidecar describing how inspect ran. |
| `review_decisions_template.json` | Optional starter file for v2 human review decisions. |
| `review_decisions.json` | Persistent local Review Desk decisions, workflow state, and notes. |
| `review_gallery.html` | Optional visual review page from `--review-gallery`. |
| `priority_review_contact_sheet.png` | Optional visual sheet from `--contact-sheets`. |
| `needs_review_contact_sheet.png` | Optional visual sheet from `--contact-sheets`. |
| `improvement_plan.md` | Optional advisory plan from `dataset-forge plan`. |
| `improvement_plan.json` | Machine-readable Improvement Plan sidecar. |
| `improvement_preview.md` | Optional execution-free preview from `dataset-forge preview`. |
| `improvement_preview.json` | Machine-readable Improvement Preview sidecar. |

Optional visual review outputs:

```text
uv run dataset-forge inspect my_dataset/ --review-gallery --contact-sheets
```

Optional local review decisions:

```text
uv run dataset-forge review my_dataset/inspect_output/
```

Optional comparison after a second inspect run:

```text
uv run dataset-forge compare old_run/inspect_output/ new_run/inspect_output/ --output comparison/
```

Optional Improvement Plan:

```text
uv run dataset-forge plan my_dataset/inspect_output/
```

Optional Improvement Preview:

```text
uv run dataset-forge preview my_dataset/inspect_output/improvement_plan.json
```

---

## What It Does

Dataset Forge builds a statistical picture of your dataset, then runs
independent analyzers that compare each image against that baseline. Current
reports separate images with no findings from images that deserve human review.

The normal workflow is:

1. Run `dataset-forge inspect my_dataset/`.
2. Open `dataset-forge review my_dataset/inspect_output/`.
3. Review Priority Review images first.
4. Review Needs Review and No Findings Emitted images if useful.
5. Record decisions, workflow state, and notes in the local Review Desk.
6. Re-run inspect after dataset changes or a later review pass.
7. Compare runs with `dataset-forge compare ...`.
8. Generate an advisory Improvement Plan with `dataset-forge plan ...` if you
   want evidence-backed Improvement Candidates for future work.
9. Preview the plan with `dataset-forge preview ...` if you want a traceable
   execution-free explanation of each candidate.
10. Train with the images you decide belong in the dataset.

A healthy dataset can legitimately produce zero findings. That is a valid
and correct result, not a failure.

**Analyzers in v0.19.0-alpha:**

| Analyzer | What it detects | Status |
|---|---|---|
| `texture_analyzer/v1` | Elevated microtexture density relative to dataset baseline | First-pass; uncalibrated |
| `crystalline_faceting_analyzer/v1` | Angular micro-polygon shading on surfaces | First-pass; uncalibrated |
| `oversharpening_halo_analyzer/v1` | Edge-localized USM residuals consistent with oversharpening / halo bands | First-pass; uncalibrated |
| `high_frequency_isolated_artifact_analyzer/v1` | Sparse isolated high-frequency residual components such as bright/dark specks | First-pass; uncalibrated |

All analyzers are conservative. Confidence values are capped until calibration
against labeled ground truth is complete. The oversharpening/halo analyzer is
read-only, uses synthetic benchmark fixtures to validate its USM-residual signal
shape, and remains uncalibrated for real-world precision/recall. The isolated
high-frequency analyzer is also read-only and synthetic-fixture-backed only.
Treat findings as candidates for human review, not automated decisions. v0.19
does not change analyzer behavior, recommendation rules, JSON schemas, gallery
behavior, contact sheets, review decisions, comparison behavior, Improvement
Planning behavior, or source images.

---

## Who it is for

Dataset Forge is for people who:

- Train LoRA models and suspect their image dataset carries GPT fingerprints
- Want to know which images deserve attention before training
- Work with images generated by GPT-based tools (DALL-E, Midjourney, Ideogram, etc.)
- Need findings they can audit, not opaque scores

It is not a general image quality tool, an upscaler, or a cleanup utility.
The first reference use case is watercolor and colored-pencil anthropomorphic
character datasets with GPT-style artifacts including crystalline microtexture,
glitter-like speckle, periodic frequency contamination, oversharpening, and
edge halos.

---

## Current limitations (v0.19.0-alpha)

- **Analyzers are not calibrated to published ground truth.** Thresholds were
  derived from an initial labeled review of one private dataset. Precision and
  recall are known for that dataset but are not general. Treat findings as
  informed candidates for human review, not certified detections.

- **Four analyzers are currently implemented.** Periodic frequency / recursive
  detail remains unimplemented. The oversharpening/halo and isolated
  high-frequency analyzers are conservative first-pass detectors backed by
  synthetic fixtures, not published real-world calibration.

- **No public recommendation command yet.** v0.25.0-alpha exposes `inspect`,
  local `review`, sidecar-only `compare`, advisory `plan`, and
  execution-free `preview`. There is no separate `dataset-forge recommend`
  command.

- **No cleanup, repair, execution, or export.** v0.25.0-alpha is read-only.
  Improvement Planning writes `improvement_plan.json` and
  `improvement_plan.md` only. Improvement Preview writes
  `improvement_preview.json` and `improvement_preview.md` only. Cleanup,
  repair, execution, and export are future-only possibilities, not assumed next
  steps. See [ROADMAP.md](ROADMAP.md). Code for future phases exists in the
  repository but is not active or supported in the public CLI.

- **No hosted web app.** Dataset Forge is a CLI tool. Reports are JSON, plain text,
  Markdown, optional static HTML, and optional PNG contact sheets. These visual
  outputs are not interactive and record no review state by themselves. The
  optional `review` command starts a local-only browser surface over existing
  sidecars and writes only `review_decisions.json`.

- **z-score findings require dataset context.** `texture_analyzer/v1` uses
  dataset-relative z-scores. On a dataset of fewer than five images the baseline
  statistics are not meaningful.

- **Most scripts are internal development utilities.** The public scripts are
  `run_benchmarks.py`, `generate_crystalline_fixtures.py`,
  `generate_texture_fixtures.py`, and `generate_benchmark_defects.py`.
  All other files in `scripts/` -- whether prefixed with `_` or not -- are
  internal calibration, diagnostic, or research tools and are not part of the
  public API. `scripts/research/` holds artifact-family research probes.

---

## v0.19 Real-World Triage Evidence

v0.19 does not implement deterministic execution. The release improves
real-image triage before any cleanup, export, repair, or pixel modification
exists.

v0.19 focus:

- Renames user-facing ready wording to **No Findings Emitted** until
  calibration supports stronger claims.
- Add image-level triage dossiers with findings nested underneath each image.
- Add analyzer coverage summaries so users know which analyzers ran, which
  emitted findings, and which artifact families remain uncovered or
  uncalibrated.
- Clarify that no finding is not proof that an image is artifact-free or
  guaranteed suitable for LoRA training.
- Improve wording around crystalline faceting, high microtexture, Priority
  Review, and accepted/acceptable style.
- Validate the full read-only workflow against the anthropomorphic LoRA
  dataset.

Execution, cleanup, export, repair, source-image modification, and pixel
modification remain explicitly out of scope.

---

## v0.20 Browser-Based Review Desk

v0.20 makes the local browser review workflow the primary human-facing Dataset
Forge experience. After `inspect`, the CLI points users clearly to the output
directory, the Review Desk command, and the best evidence files to open first.

Implemented v0.20 focus:

- Show images grouped by Priority Review, Needs Review, and No Findings
  Emitted.
- Show thumbnail, filename, triage status, finding categories,
  confidence/severity, evidence summary, suggested review action, and links or
  anchors to detailed triage dossier entries.
- Add filters for status, analyzer/finding category, severity, and confidence.
- Let the user record decisions in the browser: Keep, Accepted Style / False
  Positive, Improvement Candidate, Removal Candidate, Undecided, workflow
  state, and notes.
- Persist decisions to `review_decisions.json` using
  `dataset-forge/review-decisions/v2`, with v1 migration on load.

The browser workflow must remain local, deterministic, and sidecar-based. It
must not modify source images, execute cleanup, export datasets, add automatic
repair, or add network dependencies.

---

## v0.21 Dataset Overview

v0.21 adds a Dataset Overview inside the Review Desk. The overview summarizes
existing inspect sidecars and review decisions without running analyzers or
changing files.

Implemented v0.21 focus:

- Show total images and triage counts.
- Show review progress, decision counts, and workflow counts.
- Show top finding categories and analyzer coverage.
- Provide deterministic next-action guidance.
- Make read-only, sidecar-driven scope visible in the interface.
- Clarify that Quarantine Planned is workflow intent only, not file movement.

The overview is descriptive only. It does not score dataset quality, change
analyzer thresholds, create folders, move images, copy images, export datasets,
or execute improvements.

---

## v0.22 Review Desk Contracts

v0.22 keeps the Review Desk user experience unchanged and moves the
sidecar-derived Review Desk payload into a tested internal contract layer. This
makes the local browser desk easier to maintain while preserving deterministic,
read-only behavior.

Implemented v0.22 focus:

- Separate Review Desk data builders from the localhost server.
- Keep the Review Desk consuming generated sidecars only.
- Preserve the existing `review_decisions.json` schema and write path.
- Add tests for deterministic overview, progress, category, analyzer coverage,
  next-action, and payload contract generation.

This release does not add profiles, analyzer configuration, cleanup, execution,
export, repair, image modification, or new analyzers.

---

## v0.23 Inspection Manifest

v0.23 adds `inspection_manifest.json` as a provenance sidecar for inspect runs.
It records how inspection was performed without changing analyzer execution,
recommendation rules, Review Desk behavior, or existing sidecar schemas.

Implemented v0.23 focus:

- Record Dataset Forge version and default inspection profile.
- Record inspect inputs such as dataset path, recursion, limit, and counts.
- Record sidecar schema references.
- Record current analyzer versions, families, emitted categories, advisory
  calibration status, and default enabled / visible / included policies.
- Leave `disabled_analyzers` empty until configurable review signals exist.

The manifest is descriptive only. It does not implement profile selection,
analyzer toggles, configurable review signals, dataset analytics, cleanup,
execution, export, repair, or manifest-aware comparison.

---

## v0.24 Manifest-Aware Comparison

v0.24 makes `dataset-forge compare` read optional `inspection_manifest.json`
sidecars and report whether two inspect outputs were produced under comparable
conditions.

Implemented v0.24 focus:

- Add an advisory `inspection_compatibility` section to `comparison_summary.json`.
- Show a short Inspection Compatibility section near the top of
  `comparison_summary.md`.
- Report compatible manifests, missing provenance, and differences in manifest
  schema, inspection profile, Dataset Forge version, analyzer participation,
  analyzer versions, display policy, and triage policy.
- Continue comparing older outputs without manifests.

Comparison remains advisory and sidecar-only. It does not block comparison,
rerun analyzers, reinterpret findings, inspect images, modify source files,
change recommendations, or implement configurable review signals.

---

## v0.25 Dataset Intelligence

v0.25 expands the local Review Desk with Dataset Intelligence. This is
dataset-level evidence organization, not scoring or grading.

Implemented v0.25 focus:

- Add `dataset_intelligence` to the Review Desk data contract.
- Summarize review status, remaining undecided work, evidence categories,
  affected image counts, analyzer contribution, dataset coverage, dataset
  characteristics, review guidance, and provenance.
- Use `inspection_manifest.json` and `comparison_summary.json` when present,
  while continuing to work when those optional sidecars are absent.
- Keep the image grid and human decisions as the primary Review Desk workflow.

Dataset Intelligence is descriptive, deterministic, evidence-first, and
sidecar-derived. It does not create a new sidecar, run analyzers, inspect
pixels, score datasets, grade datasets, pass or fail datasets, modify source
images, move files, create quarantine folders, execute cleanup, repair images,
or export datasets.

---

## What To Read First

New users should read these first:

- `README.md` -- install, inspect, outputs, and normal workflow.
- `recommendation_summary.md` from your first run -- the main review report.
- `inspection_report.txt` from your first run -- detailed plain-text findings.
- `benchmarks/README.md` -- what the public benchmark suite proves.

You can ignore these until later:

- `ARCHITECTURE.md` -- useful when changing internals.
- `PROJECT_BIBLE.md` -- useful before major product or architecture changes.
- `ROADMAP.md` and `CURRENT_STATUS.md` -- useful when joining development.
- `CLI_OUTPUT.md` -- acceptance notes for command/report wording.
- `scripts/research/` -- internal analyzer research probes.

---

## Requirements

- Python 3.11 or newer
- [uv](https://docs.astral.sh/uv/) recommended, or pip

Runtime dependencies are installed automatically:

- Pillow >= 10.0
- opencv-python >= 4.10

---

## Install

Recommended:

```text
git clone https://github.com/surrealbydesign/dataset-forge.git
cd dataset-forge
uv sync
```

Or with pip:

```text
pip install -e .
```

---

## Inspect A Dataset

Copy and paste:

```text
uv run dataset-forge inspect my_dataset/
```

Use an explicit output folder when you do not want reports inside
`my_dataset/inspect_output/`:

```text
uv run dataset-forge inspect my_dataset/ --output my_report/
```

Example terminal output:

```text
Dataset Forge Inspect
=====================
Dataset:  my_dataset/
Output:   my_dataset/inspect_output

Images:   100
Analyzed: 100
Errors:   0

Summary
-------
Total findings:  19
  HIGH severity:  2
  MEDIUM severity: 11
  LOW severity:   6

Images with findings:        15 / 100
No Findings Emitted:         85 / 100

85 images emitted no current review findings.
15 images have findings. Review report for details.

Recommendation Summary
----------------------
  No Findings Emitted: 85
  Needs Review:        13
  Priority Review:     2

Recommendations are advisory and based only on existing findings.
Execution, cleanup, export, and source-image modification are out of scope.
Source images were not modified.

Report written:
  my_dataset/inspect_output/inspection_report.json
  my_dataset/inspect_output/inspection_report.txt
  my_dataset/inspect_output/recommendation_summary.json
  my_dataset/inspect_output/recommendation_summary.md
  my_dataset/inspect_output/triage_dossiers.json
  my_dataset/inspect_output/triage_dossiers.md
  my_dataset/inspect_output/inspection_manifest.json
```

Reports are written to the output directory (default: a folder named
`inspect_output/` inside your dataset directory). Source images are not
touched.

Reports also include additive post-inspection sections:

- **Dataset Summary** -- counts what was found across the dataset.
- **Review Queue** -- advisory ordering for which images deserve human attention first.
- **Recommendation Summary sidecars** -- No Findings Emitted, Needs Review,
  and Priority Review guidance derived from existing findings only.
- **Triage Dossiers** -- image-level evidence files with findings nested under
  each image, analyzer coverage summaries, review status, and suggested human
  action.
- **Optional static review gallery** -- `review_gallery.html`, generated only
  with `--review-gallery`, for visual review of Priority Review and Needs
  Review images.
- **Optional recommendation contact sheets** --
  `priority_review_contact_sheet.png` and `needs_review_contact_sheet.png`,
  generated only with `--contact-sheets`.
- **Optional local review server** -- `dataset-forge review <inspect_output>`,
  started only when requested, for recording decisions in `review_decisions.json`.
- **Optional dataset comparison** -- `dataset-forge compare <before> <after>
  --output <comparison_output>`, for comparing two existing inspect output
  folders without reading source images.

These sections are review aids only. Dataset Forge does not delete, modify,
repair, reject, regenerate, or export images.

In the product direction for v1, these sections become the evidence base for
decision-oriented guidance:

- **No Findings Emitted** -- no current deterministic analyzer emitted a review
  finding.
- **Needs review** -- evidence suggests a human should inspect the image before training.
- **Priority Review** -- stronger or multiple findings suggest the image should
  be reviewed before other images.

Exclusion is not deletion. Dataset Forge may eventually help identify images to
leave out of training, but source files remain untouched.

### Optional: static review gallery

```
uv run dataset-forge inspect path/to/dataset/ --review-gallery
```

Writes `review_gallery.html`, a static, read-only visual review surface over
`inspection_report.json` and `recommendation_summary.json`. It does not rerun
analyzers, recompute recommendations, record review decisions, modify images,
or create a web app.

### Optional: local review decisions

```
uv run dataset-forge review path/to/dataset/inspect_output/
```

Starts a localhost-only review surface at `127.0.0.1`. It reads
`inspection_report.json`, `recommendation_summary.json`, and optional existing
`review_decisions.json`. It writes only `review_decisions.json` using the
existing `dataset-forge/review-decisions/v1` schema.

The review server does not rerun analyzers, recompute recommendations, edit the
static gallery, modify images, change reports, repair, clean up, export, use a
database, use a login, or contact any cloud service.

### Optional: compare inspect outputs

```
uv run dataset-forge compare path/to/before/inspect_output/ path/to/after/inspect_output/ --output path/to/comparison/
```

Writes `comparison_summary.json` and `comparison_summary.md`. The comparison
uses existing `inspection_report.json`, `recommendation_summary.json`, and
optional `review_decisions.json` sidecars only. When `inspection_manifest.json`
is present, comparison adds advisory compatibility status and warnings so users
can see whether the two inspect runs used matching provenance.

The comparison shows changed recommendations, new findings, resolved findings,
recommendation count changes, finding category changes, and analyzer output
changes. It does not rerun analyzers, inspect images, compare pixels, modify
reports, modify review decisions, block comparison, reinterpret findings, or
classify changes as better or worse.

### Optional: recommendation contact sheets

```
uv run dataset-forge inspect path/to/dataset/ --contact-sheets
```

Writes `priority_review_contact_sheet.png` and
`needs_review_contact_sheet.png`, read-only visual review aids over
`inspection_report.json` and `recommendation_summary.json`. Empty groups produce
small deterministic empty-state sheets. No Findings Emitted images do not get a
contact sheet by default because no-finding images should stay quiet.

Contact sheets do not rerun analyzers, recompute recommendations, write
thumbnails beside source images, record review decisions, modify images, or
create a web app. They show at most the first 100 images per sheet in
Recommendation Summary order.

### Internal: calibration evidence

v0.19.0-alpha includes internal Calibration Evidence: comparing an existing
`inspection_report.json` with a small ground-truth label file to compute
per-analyzer and per-category TP/FP/FN/TN, precision, recall, F1, and
false-positive rate.

This is internal evidence tooling. It does not change analyzer thresholds,
modify images, add cleanup/repair/export, or change the public `inspect`
behavior.

### Internal: review decisions

v0.19.0-alpha includes persistent Review Decisions: schema-versioned JSON files
that record human intent for images or finding categories after inspection and
calibration review.

Review Decisions can mark findings as confirmed artifacts, false positives,
acceptable style, needing review, ignored, or locked. `dataset-forge inspect`
creates `review_decisions_template.json` only when absent and reads
`review_decisions.json` when present so Markdown/HTML outputs can show Already
Reviewed or Pending Review status. `dataset-forge review` can record those
decisions without hand-editing JSON. Review Decisions do not modify images,
change recommendations, plan repair, export datasets, or change analyzer
behavior.

### Internal: validation dossiers

v0.19.0-alpha includes internal Validation Dossiers: deterministic JSON summaries
that combine an existing `inspection_report.json`, calibration labels, and
optional Review Decisions to assess analyzer reliability.

Validation Dossiers report per-analyzer and per-category metrics, false-positive
and false-negative examples, review disagreement counts, threshold-review
candidates, and conservative readiness statuses. They are evidence for future
confidence communication and recommendation quality. They do not change
thresholds, modify images, plan repair, export datasets, or change the public
`inspect` behavior.

### Internal: real-world validation corpus

v0.19.0-alpha includes the Real-World Validation Corpus framework under
`benchmarks/real_world/`. It defines how labeled real-world LoRA/image datasets
should be organized for future reliability validation.

The committed corpus uses synthetic placeholder metadata only so fresh clones
remain deterministic. Legally safe public-domain/CC0 real-world fixtures can be
added later with labels and expected validation outputs. Private/local datasets
may be used under the ignored private corpus path and are skipped when absent.

The corpus is methodology only. It does not change analyzer thresholds, modify
images, plan repair, export datasets, or change the public `inspect` behavior.

### Recommendation summary

v0.19.0-alpha writes Recommendation Summary sidecars from `dataset-forge inspect`
with schema
`dataset-forge/recommendation-summary/v1`.

It consumes only existing inspection findings and DatasetContext image paths. It
does not inspect images, run analyzers, generate new evidence, modify Findings,
read Validation Dossiers, or interpret calibration evidence. Existing Review
Decisions may annotate Markdown/HTML presentation only; they do not affect
recommendation rules or `recommendation_summary.json`.

The deliberately boring four-rule engine is:

- analyzer error -> Priority Review
- HIGH or CRITICAL finding -> Priority Review
- findings from multiple categories -> Priority Review
- any other finding -> Needs Review
- no findings -> No Findings Emitted

The output has no numeric quality score and no serialized priority field. It is
additive and is not embedded into `inspection_report.json`. Recommendation
labels and `recommendation_summary.json` must be reproducible from the
Inspection Report alone. There is no public `dataset-forge recommend` command.

`recommendation_summary.md` is organized for human review: Dataset Summary,
most common finding categories, analyzer coverage, Priority Review first,
Needs Review second, No Findings Emitted summarized without listing every
no-finding image, important notes, and next steps. Each Priority Review and
Needs Review item explains why it appears there using the primary reason,
finding categories, severity, analyzer names, finding count, and nested finding
evidence already present in the recommendation sidecar.

`No Findings Emitted` means Dataset Forge emitted no current findings requiring
review. It does not guarantee the image is artifact-free, caption-ready, or
suitable for LoRA training.

### Why Dataset Forge does not repair images yet

Repair is deferred because Dataset Forge must first earn trust at the decision
layer. Before it can suggest changing an image, it must reliably identify which
images deserve intervention, explain why, and measure false positives against
labeled real-world datasets.

Today the product is intentionally read-only. Its job is to reduce uncertainty
before training, not automate judgment.

### Optional: inspection gallery

```
uv run dataset-forge inspect path/to/dataset/ --gallery
```

Writes `inspection_gallery.png`  --  a contact sheet with findings grouped by
severity alongside clean reference images.

---

## Reading the report

Each finding in `inspection_report.txt` looks like this:

```
image_023.png
  [MEDIUM] artifact.crystalline_faceting  --  confidence 0.45 (FP rate ~28%)
  Benchmark: uncalibrated
  Evidence: pencil_grain_score=64.2, watercolor_smoothness_score=36.6, microtexture_density_score=65.8
  Why: pencil_grain=64.2 is above the detection threshold. Crystalline
       surface faceting detected based on mid-frequency texture pattern.
  Action: Candidate for review. Do not change the image without inspecting
          it first.
```

Every finding includes:
- **Severity** (LOW / MEDIUM / HIGH / CRITICAL)
- **Confidence** and **estimated false-positive rate**
- **Benchmark version**  --  `uncalibrated` means thresholds have not been
  validated against published ground truth for your dataset type
- **Raw evidence**  --  the measurements that produced the finding
- **A plain-language explanation** of why the finding was made
- **A recommended action**, which may be "leave alone"

Images with no findings are listed separately. They are not an afterthought.

---

## Safety guarantees

- **Source images are read-only.** Dataset Forge never writes to your image files.
  No move, rename, modify, or delete operation is performed on source images.
- **Reports are written separately.** All output goes to the directory you specify,
  not inside your dataset.
- **Cleanup, repair planning, repair, and export are not implemented in
  v0.25.0-alpha.** There is no public flag or command that modifies, repairs,
  exports, rejects, or regenerates images. `dataset-forge plan` writes advisory
  Improvement Candidates only. This is by design.
- **Every finding is explainable.** No finding is emitted without an evidence dict,
  a human-readable explanation, and a recommendation. No black-box scores.
- **Healthy images stay quiet.** Images with no findings are listed as No
  Findings Emitted in the sidecar summary, but that is not a guarantee that an
  image is artifact-free.

---

## Benchmarks

Analyzer thresholds are validated against committed synthetic fixtures. The
committed public fixtures run without any setup from a fresh clone:

```
uv run python scripts/run_benchmarks.py
```

The public manifest includes committed fixture expectations plus optional
generated/private cases. Optional ignored/generated/private fixtures may be
present locally and are skipped automatically when absent. See
[benchmarks/README.md](benchmarks/README.md) for the full manifest description.

### Internal measurement cache

The disk-backed measurement cache is internal and opt-in. It is disabled by
default, stores measurements only, and has no CLI flags.

- `DATASET_FORGE_MEASUREMENT_CACHE_DIR=/path/to/cache` enables the cache.
- `DATASET_FORGE_DISABLE_MEASUREMENT_CACHE=1` bypasses cache reads and writes.

---

## Tests

```
uv run pytest tests/
```

The automated suite covers the full inspect pipeline: Finding,
DatasetContext, Analyzer contracts, report writers, CLI, inspect runner,
gallery, static review gallery, contact sheets, benchmark framework, committed fixtures, post-inspection review
guidance, calibration evidence, review decisions, validation dossiers, the
real-world validation corpus framework, internal recommendation summaries, and
public CLI surface.

---

## License

MIT. See [LICENSE](LICENSE).

---

## Architecture and project docs

| Document | Contents |
|---|---|
| [PROJECT_BIBLE.md](PROJECT_BIBLE.md) | Project constitution  --  read before changing anything |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Inspect pipeline structure, Finding schema, artifact family model |
| [WHY.md](WHY.md) | Reasoning behind major design decisions |
| [DIRECTION.md](DIRECTION.md) | Current milestone and scope |
| [ROADMAP.md](ROADMAP.md) | v0.19.0-alpha status and future milestone plan |
| [CURRENT_STATUS.md](CURRENT_STATUS.md) | Implementation status; resume from here |
| [CLI_OUTPUT.md](CLI_OUTPUT.md) | Acceptance criteria for terminal and report output |
| [benchmarks/README.md](benchmarks/README.md) | Benchmark manifests and fixture inventory |
