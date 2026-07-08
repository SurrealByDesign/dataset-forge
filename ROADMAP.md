# Dataset Forge - Roadmap

---

## Product Direction

Dataset Forge is a LoRA Dataset Decision Engine.

Its purpose is to help LoRA dataset builders decide which images emitted no
current review findings, which need review, and which deserve priority attention before training. Every
recommendation must be grounded in deterministic analysis, measurable evidence,
and explainable findings.

Everything after v0.8 should improve one of:

- decision quality
- confidence communication
- false-positive reduction
- review efficiency
- benchmark and corpus evidence

Repair, cleanup execution, and export remain future-only possibilities, not
assumed next steps.

The long-term direction is deterministic, evidence-backed dataset improvement.
Dataset Forge may later support Improvement Planning and optional cleanup execution,
but only after the decision path is trustworthy:

```
Inspect
-> Recommend
-> Explain
-> Human Review
-> Persistent Decisions
-> Dataset Comparison
-> Improvement Planning
-> Optional Cleanup Execution
```

It must never become:

```
Inspect
-> Automatically Clean
```

This is not a commitment to build cleanup in the current roadmap. The current
product remains a LoRA Dataset Decision Engine.

---

## Released Foundations

### v0.1.0-alpha: Inspect Foundation

**Status:** Released.

- Stable Finding and Analyzer contracts.
- `dataset-forge inspect`.
- JSON/TXT inspection reports.
- Optional gallery output.
- First public benchmark framework.

### v0.2.0-alpha: Four-Analyzer Inspect Platform

**Status:** Released.

**Pipeline:** `Dataset -> DatasetContext -> Analyzer -> Finding -> Aggregation -> Dataset Summary -> Review Queue -> Report`

| Component | Status |
|---|---|
| `Finding` dataclass | shipped |
| `DatasetContext` dataclass | shipped |
| `Analyzer` base class | shipped |
| `TextureAnalyzer` -- microtexture, watercolor smoothness signal | shipped; first-pass uncalibrated |
| `CrystallineFacetingAnalyzer` -- pencil_grain + texture_consistency | shipped; first-pass uncalibrated |
| `OversharpeningHaloAnalyzer` -- edge-localized USM residuals | shipped; first-pass uncalibrated |
| `HighFrequencyIsolatedArtifactAnalyzer` -- sparse residual components | shipped; first-pass uncalibrated |
| Dataset Summary + Review Queue | shipped; advisory |
| Public benchmark suite | shipped |
| Public CLI surface locked to inspect-only | shipped |

v0.2.0-alpha did not include cleanup, repair, regeneration, AI editing, UI,
captions, plugins, or exporters.

### v0.3.0-alpha: Calibration Evidence

**Status:** Released.

Calibration Evidence compares an existing `inspection_report.json` against a
small ground-truth label file and reports:

- per-analyzer TP / FP / FN / TN
- precision, recall, F1, and false-positive rate
- category-level summaries
- schema-versioned JSON output

This is internal evidence tooling. It does not change analyzer thresholds or
expand the public CLI.

### v0.4.0-alpha: Review Decisions

**Status:** Released.

Review Decisions record human intent over inspected images and finding
categories:

- confirmed artifacts
- false positives
- acceptable style
- needs review
- ignored images/categories
- locked images/categories

This is internal decision-quality evidence. It does not plan or apply dataset
changes.

### v0.5.0-alpha: Validation Dossiers

**Status:** Released.

Validation Dossiers combine:

- an existing `inspection_report.json`
- schema-versioned calibration labels
- optional Review Decisions

The output summarizes per-analyzer and per-category reliability, false-positive
and false-negative examples, review disagreement, and threshold-review
candidates.

This is a validation layer for confidence communication and future
recommendation quality. It does not implement repair planning.

### v0.6.0-alpha: Real-World Validation Corpus

**Status:** Released.

The Real-World Validation Corpus framework defines how legally safe, labeled
real-world validation datasets should be organized.

It adds:

- a schema-versioned corpus manifest
- committed placeholder methodology fixtures
- Calibration Evidence label compatibility checks
- optional private/local fixture skipping
- public rules for what can and cannot be committed

The corpus is methodology only. It does not change analyzer thresholds,
implement recommendations, or expand the public CLI.

---

### v0.7.0-alpha: Internal Recommendation Summary

**Status:** Released.

Recommendation Summary adds an internal, additive
`dataset-forge/recommendation-summary/v1` schema over existing findings and
DatasetContext image paths.

It uses exactly four deterministic rules:

- analyzer error -> **Priority Review**
- HIGH or CRITICAL finding -> **Priority Review**
- findings from multiple categories -> **Priority Review**
- any other finding -> **Needs Review**
- no findings -> **Ready for Training**

Constraints:

- Internal/additive only.
- No public recommendation command.
- No inspect report wiring.
- No deletion, repair, cleanup, export, or image modification.
- No validation, calibration, or Review Decisions coupling.
- No numeric quality scores or serialized priority fields.
- Recommendations cite existing findings only.
- Existing report fields remain unchanged.

---

### v0.8.0-alpha: User-Visible Recommendation Summary

**Status:** Released.

`dataset-forge inspect` writes additive Recommendation Summary sidecars:

- `recommendation_summary.json`
- `recommendation_summary.md`

The sidecars use the v0.7 four-rule engine unchanged:

- analyzer error -> **Priority Review**
- HIGH or CRITICAL finding -> **Priority Review**
- findings from multiple categories -> **Priority Review**
- any other finding -> **Needs Review**
- no findings -> **Ready for Training**

Constraints:

- No `dataset-forge recommend` command.
- No embedding into `inspection_report.json`.
- No deletion, repair, cleanup, export, regeneration, or image modification.
- No validation, calibration, or Review Decisions coupling.
- No numeric quality scores or serialized priority fields.
- Recommendations cite existing findings only.
- Every Recommendation Summary must be reproducible from
  `inspection_report.json` alone.
- Ready for Training is not a guarantee that an image is artifact-free.

---

### v0.9.0-alpha: Recommendation Markdown Presentation

**Status:** Released.

v0.9 polishes `recommendation_summary.md` into a human-facing review report
without changing recommendation logic or JSON output.

It adds:

- summary counts at the top of the Markdown report
- Priority Review first, then Needs Review
- grouping by artifact family
- filename, recommendation, primary reason, and finding references per review item
- Ready for Training summarized without listing every ready image
- Important Notes and Next Step sections

Constraints:

- No recommendation rule changes.
- No `recommendation_summary.json` schema changes.
- No inspect schema changes.
- No CLI surface changes.
- No analyzer changes.
- No gallery, UI, export, repair, or cleanup.
- No validation, calibration, or Review Decisions coupling.

---

### v0.10.0-alpha: Static Review Gallery

**Status:** Released.

v0.10 adds an optional static visual review surface:

- `dataset-forge inspect <dataset> --review-gallery`
- `review_gallery.html`

The gallery consumes existing sidecars only:

- `inspection_report.json`
- `recommendation_summary.json`
- source image paths referenced by those reports

Constraints:

- No analyzer reruns.
- No recommendation recomputation.
- No recommendation rule changes.
- No `inspection_report.json` schema changes.
- No buttons, checkboxes, forms, review decisions, server, or web app.
- No deletion, repair, cleanup, export, regeneration, or image modification.
- Plain deterministic HTML with embedded CSS and no external assets.

---

### v0.11.0-alpha: Recommendation Contact Sheets

**Status:** Released.

v0.11 adds optional recommendation-oriented PNG contact sheets:

- `dataset-forge inspect <dataset> --contact-sheets`
- `priority_review_contact_sheet.png`
- `needs_review_contact_sheet.png`

The contact sheets consume existing sidecars only:

- `inspection_report.json`
- `recommendation_summary.json`
- source image paths referenced by those reports

Constraints:

- No analyzer reruns.
- No recommendation recomputation.
- No recommendation rule changes.
- No `inspection_report.json` or `recommendation_summary.json` schema changes.
- No Ready for Training contact sheet by default.
- Empty Priority Review or Needs Review groups produce deterministic
  empty-state sheets.
- No review decisions, buttons, forms, server, web app, deletion, repair,
  cleanup, export, regeneration, or image modification.

---

### v0.12.0-alpha: Explainable Recommendations

**Status:** Released.

v0.12 improves presentation only for existing recommendation outputs:

- `recommendation_summary.md`
- `review_gallery.html`

It makes each Priority Review and Needs Review item answer "why is this image
here?" using existing recommendation and finding references:

- recommendation
- primary reason
- finding categories
- severity
- analyzer names
- finding count

Constraints:

- No recommendation rule changes.
- No `recommendation_summary.json` schema changes.
- No `inspection_report.json` schema changes.
- No analyzer behavior changes.
- No contact sheet behavior changes.
- No review decisions, validation coupling, cleanup, repair, export, web app,
  browser state, confidence tiers, quality scores, or new commands.

---

### v0.13.0-alpha: Persistent Human Review Decisions

**Status:** Released.

v0.13 preserves human review knowledge across inspect runs:

- `dataset-forge inspect` writes `review_decisions_template.json` only when no
  template already exists.
- Existing `review_decisions.json` files are loaded but never overwritten.
- `recommendation_summary.md` and optional `review_gallery.html` show
  Already Reviewed / Pending Review status.
- Human decisions use the existing `dataset-forge/review-decisions/v1` schema.

Constraints:

- No recommendation rule changes.
- No `recommendation_summary.json` schema changes.
- No `inspection_report.json` schema changes.
- No analyzer behavior changes.
- No contact sheet behavior changes.
- No browser editing, buttons, forms, server, cleanup, repair, export, or image
  modification.

---

### v0.14.0-alpha: Local Review Decision Server

**Status:** Released.

v0.14 makes review decisions usable without hand-editing JSON:

- `dataset-forge review <inspect_output>`
- Localhost-only server bound to `127.0.0.1`
- Reads existing `inspection_report.json`, `recommendation_summary.json`, and
  optional `review_decisions.json`
- Writes only `review_decisions.json`
- Uses the existing `dataset-forge/review-decisions/v1` schema and decision
  values

Constraints:

- No recommendation rule changes.
- No `recommendation_summary.json` schema changes.
- No `inspection_report.json` schema changes.
- No analyzer behavior changes.
- No contact sheet or static gallery behavior changes.
- No cleanup, repair, export, source image mutation, database, login, cloud,
  frontend framework, build step, or hidden browser state.

---

### v0.15.0-alpha: Dataset Comparison

**Status:** Released.

v0.15 lets users compare two existing inspect output folders:

- `dataset-forge compare <before_inspect_output> <after_inspect_output> --output <comparison_output>`
- Reads `inspection_report.json`, `recommendation_summary.json`, and optional
  `review_decisions.json`
- Writes `comparison_summary.json`
- Writes `comparison_summary.md`

The comparison answers what deserves attention because something changed:

- recommendation count changes
- finding category changes
- analyzer output count changes
- images whose recommendation changed
- findings present after but not before
- findings present before but not after
- review-decision availability and decision counts only

Constraints:

- No analyzer reruns.
- No image inspection or pixel comparison.
- No recommendation rule changes.
- No `recommendation_summary.json` schema changes.
- No `inspection_report.json` schema changes.
- No review-decision interpretation.
- No cleanup, repair, export, browser UI, charts, graphs, scores, or
  better/worse wording.
- Finding identity uses normalized image path, category, analyzer, and severity;
  duplicate findings are treated as multisets.

---

### v0.16.0-alpha: First-Time User Experience Audit

**Status:** Released.

v0.16 makes Dataset Forge easier to understand on first contact:

- README opens with the LoRA dataset workflow instead of architecture.
- Adds a 60-second Quick Start around `dataset-forge inspect my_dataset/`.
- Explains the normal flow: Raw Dataset -> Inspect -> Recommendations ->
  Review -> Human Decisions -> Compare -> Train.
- Clarifies expected outputs and what to open first.
- Separates beginner docs from advanced architecture/status documents.
- Improves CLI help text using user workflow language.
- Makes common missing-sidecar errors more actionable.

Constraints:

- No analyzer changes.
- No recommendation rule changes.
- No report schema changes.
- No comparison behavior changes.
- No new commands.
- No cleanup, repair, export, browser features, or new analyzers.

---

### v0.17.0-alpha: Improvement Planning

**Status:** Released.

v0.17 adds the first evidence-backed planning stage:

- Adds `dataset-forge plan <inspect_output>`.
- Consumes existing `inspection_report.json`, `recommendation_summary.json`,
  optional `review_decisions.json`, and optional `comparison_summary.json`.
- Writes `improvement_plan.json` and `improvement_plan.md`.
- Uses Improvement Candidate terminology for the new planning output.
- Maps existing findings and recommendations to abstract Suggested
  Improvements only.
- Respects human review decisions:
  `CONFIRMED_ARTIFACT` remains eligible, `FALSE_POSITIVE`,
  `ACCEPTABLE_STYLE`, and `IGNORE` suppress planning, `LOCKED` prevents
  candidates, and `NEEDS_REVIEW` defers planning.

Constraints:

- No image modification.
- No copied, moved, renamed, deleted, or exported source files.
- No cleanup execution.
- No repair algorithms.
- No analyzer changes.
- No recommendation rule changes.
- No comparison behavior changes.
- No report schema changes.
- No browser UI, buttons, execution state, or hidden automation.

---

### v0.18.0-alpha: Improvement Preview

**Status:** Released.

v0.18 adds the final planning stage before any future deterministic execution:

- Adds `dataset-forge preview <improvement_plan.json>`.
- Consumes existing `improvement_plan.json`, optional `review_decisions.json`,
  and optional `comparison_summary.json`.
- Writes `improvement_preview.json` and `improvement_preview.md`.
- Explains each Improvement Candidate with suggested improvement, evidence,
  triggering findings, review decisions, planning status, execution
  availability, and expected outcome.
- Marks execution availability as `Not Implemented`.

Constraints:

- No image modification.
- No image processing.
- No analyzer execution.
- No cleanup execution.
- No repair.
- No export.
- No recommendation rule changes.
- No report schema changes.

---

## v0.19.0-alpha: Real-World Triage Evidence

**Status:** Implemented.

**Goal:** Make Dataset Forge better at helping a human decide what to do with
real images before any cleanup, export, or deterministic execution exists.

v0.19 should be validated against the anthropomorphic LoRA dataset, not only
against unit tests or synthetic fixtures. The release should treat real review
friction as product evidence: confusing labels, weak confidence wording,
missing analyzer coverage context, overly broad improvement language, and any
place where a human cannot tell why one image appears before another.

Primary changes:

- Rename user-facing **Ready for Training** language to **No Findings Emitted**
  or **No Current Review Finding** until calibration supports stronger wording.
- Clarify that no finding means no current deterministic analyzer emitted a
  review signal. It does not certify that an image is artifact-free, optimal,
  complete, caption-ready, or guaranteed suitable for LoRA training.
- Add image-level triage dossiers that place each image at the center and nest
  findings, evidence values, analyzer names, severity, confidence notes, review
  status, and suggested next human action underneath.
- Make recommendation outputs image-centered, with finding-level evidence as
  supporting detail rather than separate competing work items.
- Add analyzer coverage summaries: which analyzers ran, which emitted findings,
  which emitted none, which remain uncalibrated, and which artifact families are
  not currently covered.
- Improve wording around crystalline faceting so it is not presented as generic
  microtexture or automatically mapped to microtexture cleanup language.
- Improve wording around high microtexture so users understand when it is a
  dataset-relative review signal rather than proof of a defect.
- Improve Priority Review wording so it means "review first" rather than
  "exclude" or "execute an improvement."
- Improve accepted-style / acceptable-style language so human review can record
  intentional texture without treating it as analyzer failure.
- Validate the full inspect -> recommendation summary -> review gallery ->
  human review decisions -> comparison -> improvement planning -> preview
  workflow against the anthropomorphic dataset.

v0.19 should use Calibration Evidence, Review Decisions, Validation Dossiers,
and the Real-World Validation Corpus where useful, but the release is not only
a validation metrics release. It is a real-image triage-quality release.

Questions v0.19 should answer:

- How often are review recommendations useful?
- How often are Priority Review recommendations false positives?
- Which artifact families are trustworthy enough for stronger wording?
- Which confidence messages reduce overtrust?
- Do the reports and galleries give enough evidence for a human to make the
  next decision without opening unrelated files?
- Does the Improvement Plan overstate execution readiness or inflate work by
  treating each finding as a separate image-level action?

No analyzer thresholds should change until validation evidence supports the
change.

Constraints:

- No deterministic execution.
- No cleanup execution.
- No export.
- No repair.
- No source-image modification.
- No pixel modification.
- No automatic exclude/delete/move/rename decisions.
- No public command that implies Dataset Forge can execute improvements.
- Behavior remains deterministic, read-only, advisory, and sidecar-based.

---

## v0.20.0-alpha: Browser-Based Review Desk

**Status:** Planned.

**Goal:** Make the local browser review workflow the primary human-facing
Dataset Forge experience. A first-time user should immediately understand
which images need attention, why they were flagged, what decision they should
make, and where that decision is saved.

v0.20 is Review UX Consolidation, not execution. It turns the local review
server into an image-centered browser Review Desk over existing sidecars while
keeping `review_gallery.html` as a secondary read-only artifact.

Primary changes:

- After `inspect`, print the output directory and the most useful files to open
  first, especially the local review gallery / review desk.
- Make the browser review desk the main review entry point after inspect.
- Show images, not just reports.
- Group images by:
  - Priority Review
  - Needs Review
  - No Findings Emitted
- Each image card should show:
  - thumbnail
  - filename
  - triage status
  - finding categories
  - confidence and severity
  - evidence summary
  - suggested review action
  - links or anchors to detailed triage dossier entries
- Add basic filtering:
  - status
  - analyzer / finding category
  - severity
  - confidence
- Support decision-making in the browser:
  - Keep
  - Accepted Style / False Positive
  - Improvement Candidate
  - Removal Candidate
  - Undecided
  - Notes field
- Store workflow state separately from human decision:
  - In Dataset
  - Quarantine Planned
  - Reviewed
- Persist decisions to `review_decisions.json`.
- Move Review Decisions to `dataset-forge/review-decisions/v2`.
- Migrate existing v1 review decisions when loaded.

Constraints:

- Local-only browser UI.
- Deterministic and sidecar-based.
- No network dependencies.
- No source-image modification.
- No cleanup execution.
- No dataset export.
- No automatic repair.
- No automatic exclude/delete/move/rename decisions.
- No cloud service, login, database, or hosted app.

---

## v0.21.0-alpha: Review Desk Dataset Overview

**Goal:** Make the Review Desk immediately answer "where should I look next?"
for real datasets.

v0.21 is Review Desk overview and progress guidance, not execution. It adds a
computed Dataset Overview to the local browser desk from existing sidecars only.

Scope:

- Show total image count and triage counts.
- Show review progress, decision counts, and workflow counts.
- Show top finding categories in deterministic order.
- Show analyzer coverage summaries.
- Add deterministic next-action guidance:
  - undecided Priority Review images first
  - then undecided Needs Review images
  - then optional No Findings Emitted sampling
  - then complete-state guidance
- Make read-only, sidecar-driven scope visible in the Review Desk.
- Clarify that Quarantine Planned is workflow intent only, not file movement.

Constraints:

- No source-image modification.
- No file movement, copying, deletion, export, or quarantine folder creation.
- No cleanup, repair, execution, or automatic improvement action.
- No analyzer threshold changes.
- No new analyzer families.
- No `review_decisions.json` schema change unless a true blocker appears.
- No hosted app, login, database, cloud service, or network dependency.

---

## v0.22.0-alpha: Review Desk Maintainability & Contracts

**Goal:** Preserve the current Review Desk experience while making its internal
data contract explicit, tested, and easier to extend.

v0.22 is maintainability work, not a user-visible capability release. It
separates sidecar-derived Review Desk payload construction from the localhost
server and documents the internal `dataset-forge/review-desk-data/v1` contract.

Scope:

- Keep `dataset-forge review` as the primary local browser workflow.
- Move deterministic Review Desk payload builders into an internal contract
  module.
- Test overview, review progress, top finding category, analyzer coverage,
  next-action, and full payload generation directly.
- Preserve the existing Review Desk browser behavior and public command
  surface.
- Preserve `review_decisions.json` schema v2.

Constraints:

- No source-image modification.
- No file movement, copying, deletion, export, or quarantine folder creation.
- No cleanup, repair, execution, or automatic improvement action.
- No analyzer threshold changes.
- No new analyzer families.
- No inspection profile UI or configurable review signal UI.
- No hosted app, login, database, cloud service, or network dependency.

---

## v0.23.0-alpha: Inspection Manifest

**Goal:** Record how an inspection was performed without changing current
behavior.

v0.23 adds `inspection_manifest.json` as an additive provenance sidecar written
by `dataset-forge inspect`. It prepares Dataset Forge for future configurable
review signals, analyzer families, calibration, and manifest-aware comparison
without implementing those features yet.

Scope:

- Write `inspection_manifest.json` with schema
  `dataset-forge/inspection-manifest/v1`.
- Record Dataset Forge tool name/version.
- Record the default inspection profile only:
  `default` / `Default Inspection` / `v1`.
- Record dataset path, recursive flag, limit, image count, analyzed count, and
  error count.
- Record sidecar schema references for `inspection_report.json`,
  `recommendation_summary.json`, and `triage_dossiers.json`.
- Record existing analyzer descriptors: id, display name, version, family,
  categories emitted, advisory calibration status, and current default
  enabled / visible / included policies.
- Record finding count and affected image count per analyzer.
- Keep `disabled_analyzers` empty.

Constraints:

- No analyzer execution changes.
- No analyzer threshold changes.
- No recommendation behavior changes.
- No Review Desk behavior changes.
- No comparison behavior changes.
- No existing sidecar schema changes.
- No profile UI, analyzer toggles, configurable review signals, dataset
  analytics, cleanup, execution, export, repair, source-image modification, or
  quarantine behavior.

---

## v0.24.0-alpha: Manifest-Aware Comparison

**Goal:** Teach comparison to explain when two inspect outputs were produced
under different inspection manifests.

v0.24 keeps comparison read-only and sidecar-only. It loads optional
`inspection_manifest.json` files and emits advisory compatibility status and
warnings, but it does not block comparison by default and supports older outputs
without manifests.

Scope:

- Add `inspection_compatibility` to `comparison_summary.json`.
- Add an Inspection Compatibility section to `comparison_summary.md`.
- Report missing manifests as `provenance_unavailable`.
- Report differences in manifest schema, inspection profile, Dataset Forge
  version, analyzer participation, analyzer versions, display policy, and
  triage policy.
- Preserve all existing comparison fields and behavior.

Constraints:

- No analyzer behavior changes.
- No analyzer threshold changes.
- No recommendation behavior changes.
- No Review Desk behavior changes.
- No review-decision schema changes.
- No existing sidecar schema changes.
- No cleanup, execution, export, repair, transforms, source-image handling, or
  quarantine behavior.
- No profile UI, analyzer toggles, configurable review signals, dataset
  analytics, new analyzers, or blocking comparison behavior.

---

## v0.25.0-alpha: Dataset Intelligence

**Goal:** Expand the Review Desk from image-level review into dataset-level
understanding without scoring, grading, fixing, exporting, or automating the
dataset.

v0.25 keeps Dataset Intelligence inside the Review Desk contract layer. It does
not create a new sidecar. Every value is derived from existing sidecars:
`inspection_report.json`, `recommendation_summary.json`, `triage_dossiers.json`,
optional `inspection_manifest.json`, optional `review_decisions.json`, and
optional `comparison_summary.json`.

Scope:

- Add `dataset_intelligence` to the Review Desk payload.
- Include review status, evidence summary, analyzer contribution, dataset
  coverage, dataset characteristics, deterministic review guidance, provenance,
  and explicit descriptive/read-only scope.
- Use manifest metadata for analyzer family, calibration status, execution
  policy, display policy, triage policy, profile, and Dataset Forge version when
  available.
- Surface comparison availability without merging comparison deltas into the
  review workflow.
- Keep the image grid and human decision controls as the primary work surface.

Constraints:

- No new sidecar.
- No quality score, readiness score, grade, pass/fail label, or AI summary.
- No analyzer behavior changes.
- No analyzer threshold changes.
- No new analyzers.
- No profile UI, analyzer toggles, configurable review signals, cleanup,
  execution, export, repair, transforms, source-image modification, file
  movement, quarantine folders, training integration, cloud review, or database
  state.

## v0.26.0-alpha: Analyzer Descriptor System

**Goal:** Create an internal analyzer metadata contract without changing
analyzer behavior.

v0.26 makes Analyzer Descriptors the authoritative metadata source for built-in
analyzers. The analyzer registry continues to own execution order and fresh
analyzer instances.

Scope:

- Add `analyzer_descriptors.py`.
- Define `AnalyzerDescriptor` with id, display name, description, version,
  family, emitted categories, calibration status, deterministic flag,
  context/measurement requirements, and default execution/display/triage
  policies.
- Keep policies stable as enabled/disabled, visible/hidden, and
  included/excluded.
- Keep current analyzers in family `Technical Quality` with calibration status
  `advisory` and defaults `enabled` / `visible` / `included`.
- Make `inspection_manifest.json` use descriptor metadata while preserving the
  existing manifest shape.
- Keep Review Desk and Dataset Intelligence consuming manifest snapshots.

Constraints:

- No analyzer behavior changes.
- No threshold changes.
- No new analyzers.
- No configurable review signals.
- No review profiles or profile UI.
- No calibration metrics.
- No plugin system.
- No new sidecars.
- No cleanup, execution, export, repair, transforms, quarantine behavior, source
  image modification, or image handling changes.

## v0.27.0-alpha: Configurable Review Signals Foundation

**Goal:** Add internal policy resolution without changing current behavior.

v0.27 creates the foundation that future Configurable Review Signals and Review
Profiles can build on. It is not a user-facing configuration release.

Scope:

- Add internal `ReviewSignalPolicy`, `ResolvedReviewSignalPolicy`, and
  `PolicyResolution` helpers.
- Keep policy fields limited to execution, display, and triage.
- Resolve effective policy from Analyzer Descriptor defaults only.
- Keep all current analyzers resolving to enabled / visible / included.
- Make Inspection Manifest analyzer policy fields resolver-derived while
  preserving the existing `inspection_manifest.json` shape and current values.
- Keep analyzers unaware of policy.

Constraints:

- No analyzer behavior changes.
- No threshold changes.
- No recommendation behavior changes.
- No Review Desk behavior changes.
- No comparison behavior changes.
- No Dataset Intelligence behavior changes.
- No existing sidecar schema changes.
- No public CLI surface changes beyond version metadata.
- No profile UI, analyzer toggles, user configuration, Review Profiles, new
  analyzers, calibration, cleanup, execution, export, repair, transforms,
  quarantine behavior, source image modification, or image handling changes.

## v0.28+: Review Profile Contract

Future Review Profiles should build on the v0.27 resolver by layering profile
policy overrides on top of Analyzer Descriptor defaults. This remains future
work; v0.27 does not expose profile selection or analyzer toggles.

---

## v1.0: Stable LoRA Dataset Decision Engine

**Goal:** Ship a stable, read-only product that helps users decide what belongs
in a LoRA training set before training.

v1.0 should include:

- Stable `inspect` behavior.
- Stable decision guidance.
- Evidence-backed No Findings / Review / Exclude-from-training candidate
  language.
- Clear calibration and confidence communication.
- Public benchmark and corpus evidence.
- Reports and gallery that reduce review burden.
- No source-image modification.

v1.0 succeeds when a user can say:

> "Instead of reviewing 400 images, Dataset Forge showed me the handful that
> actually needed attention."

---

## Analyzer Improvement

Analyzer work should be driven by decision quality, not novelty.

Priority areas:

- Populate the Real-World Validation Corpus with legally safe public-domain,
  CC0, or otherwise redistributable LoRA/image examples before claiming
  real-world reliability.
- Use Validation Dossiers on labeled real-world datasets before changing
  thresholds or adding analyzer families.
- Calibrate TextureAnalyzer against labeled ground truth.
- Resolve the CrystallineFacetingAnalyzer grain 45-55 TP/FP interleaving with
  evidence from a fourth discriminating signal.
- Keep Periodic Frequency Noise postponed until a better discriminator separates
  synthetic contamination from intentional repeated patterns.

---

## Future Vision Only

The following may become valuable only after decision guidance is reliable:

- Non-destructive export of human-approved training sets.
- Repair planning.
- Evidence-backed Improvement Planning.
- Optional cleanup execution after explicit human decisions.
- Deterministic future intervention concepts.
- Additional analyzers.
- Dataset comparison.
- Lightweight review UI.
- LoRA validation feedback loop.

These are not assumed next steps. They require evidence that Dataset Forge can
reliably identify images that deserve intervention.

Any future cleanup work must follow the evidence-backed path:
Inspect -> Recommend -> Explain -> Human Review -> Persistent Decisions ->
Dataset Comparison -> Improvement Planning -> Optional Cleanup Execution. Automatic
cleanup directly after inspect is not allowed.

---

## Why Dataset Forge does not repair images yet

Repair is deferred until the tool can reliably identify images that deserve
intervention. A repair workflow built on weak or uncalibrated recommendations
would damage user trust and risk altering images that should be left alone.

Dataset Forge should first prove that it can reduce uncertainty: find the
images worth reviewing, explain the evidence, and communicate confidence
honestly. Only then should repair, cleanup, or export be reconsidered.

Cleanup planning and cleanup execution, if ever implemented, must be downstream
of persistent human decisions and dataset comparison. They are not replacements
for human judgment.
