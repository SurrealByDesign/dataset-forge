# Changelog

## v1.1.0

- Added `duplicate_detection_analyzer/v1` for advisory exact duplicate
  detection.
- Detects byte-identical files and decoded pixel-identical images; perceptual
  near-duplicate, crop, and resize matching remain out of scope.
- Emits one image-centered `dataset.duplicate.exact` finding per image in each
  duplicate group, with deterministic group IDs and suggested representative
  evidence.
- Added Review Desk labels and duplicate evidence wording while preserving the
  existing review workflow and queues.
- Did not add cleanup, export, execution, deletion, file movement, quarantine
  folders, automatic exclusion, new sidecars, or duplicate-management UI.

- Softened Texture and Crystalline Faceting analyzer explanations so findings
  read as advisory review signals rather than calibrated defect diagnoses.
- Expanded analyzer trust documentation with low-resolution JPEG/compression
  artifacts and engraving/etched illustration texture as known false-positive
  contexts.
- Added a docs-only analyzer validation journal template for real-dataset
  reviewer notes.

## v1.0.0

- Rewrote v1.0-facing documentation around the current read-only curation
  workstation workflow instead of the historical alpha roadmap.
- Clarified that the Review Desk is the primary human-facing interface and
  writes only `review_decisions.json`.
- Clarified that findings are advisory review signals, not cleanup,
  exclusion, export, or training-readiness decisions.
- Added explicit analyzer trust wording for known false-positive contexts:
  JPEG compression/ringing, natural grain, watercolor/pencil texture,
  intentional highlights/glitter, and hard-edge line art.
- Added a concise v1.0 release checklist covering tests, CLI surface, expected
  sidecars, Review Desk write scope, source-image hash preservation, and
  execution-free plan/preview behavior.
- Did not add analyzers, sidecars, schemas, architecture, public commands,
  cleanup, execution, export, repair, profile UI, analyzer toggles, quarantine
  folders, or image modification.

## v0.29.0-alpha

- Added policy-aware sidecar semantics as additive contract metadata.
- Kept `inspection_report.json` as the canonical executed-finding record and
  added `finding_policy_semantics`.
- Kept `recommendation_summary.json` triage-based and added
  `policy_semantics` plus executed / visible / triage `finding_set_counts`.
- Added `policy_semantics` to `triage_dossiers.json`.
- Added advisory `comparison_semantics` to comparison output to state that
  finding deltas use executed findings and recommendation deltas use
  triage-included recommendation semantics.
- Preserved current behavior: all current analyzers remain enabled / visible /
  included, so executed, visible, and triage counts are identical.
- Did not add UI, profile editing, profile selection, analyzer toggles, user
  configuration, new analyzers, calibration, analyzer behavior changes,
  threshold changes, recommendation behavior changes, Review Desk behavior
  changes, Dataset Intelligence behavior changes, cleanup, execution, export,
  repair, quarantine folders, image handling changes, or image modification.

## v0.28.0-alpha

- Added an internal Inspection Profile contract.
- Added `inspection_profiles.py` with `InspectionProfile`,
  `AnalyzerPolicyOverride`, the immutable default built-in profile, and profile
  lookup helpers.
- Kept the only built-in profile as `default` / `Default Inspection` / `v1`
  with no analyzer policy overrides.
- Updated Review Signal Policy resolution to resolve effective policy from
  Analyzer Descriptor defaults plus Inspection Profile overrides.
- Preserved current analyzer policy behavior: all current analyzers still
  resolve to enabled / visible / included.
- Updated Inspection Manifest generation to snapshot profile identity and
  profile content additively while continuing to snapshot effective
  per-analyzer policy in analyzer rows.
- Kept Review Desk and Dataset Intelligence consuming manifest snapshots only.
- Did not add UI, profile editing, profile selection, analyzer toggles, user
  configuration, user-authored profiles, new analyzers, threshold policy,
  calibration, analyzer behavior changes, recommendation changes, Review Desk
  changes, comparison changes, Dataset Intelligence changes, cleanup,
  execution, export, repair, quarantine folders, image handling changes, or
  image modification.

## v0.27.0-alpha

- Added an internal Review Signal Policy Resolution foundation.
- Added `review_signal_policy.py` with `ReviewSignalPolicy`,
  `ResolvedReviewSignalPolicy`, and `PolicyResolution`.
- Kept policy fields limited to execution, display, and triage:
  enabled / disabled, visible / hidden, and included / excluded.
- Resolved v0.27 effective policy from Analyzer Descriptor defaults only, so
  all current analyzers remain enabled / visible / included.
- Updated Inspection Manifest generation so analyzer policy values come from
  resolved effective policy while preserving the existing
  `inspection_manifest.json` shape and current values.
- Kept analyzers unaware of policies.
- Did not add profile UI, analyzer toggles, user configuration, Review Profiles,
  new analyzers, calibration, analyzer behavior changes, threshold changes,
  recommendation changes, Review Desk changes, comparison changes, Dataset
  Intelligence changes, cleanup, execution, export, repair, quarantine folders,
  image handling changes, or image modification.

## v0.26.0-alpha

- Added an internal Analyzer Descriptor System.
- Added `analyzer_descriptors.py` as the authoritative metadata source for
  built-in analyzer id, display name, description, version, family, emitted
  categories, calibration status, deterministic behavior, context/measurement
  requirements, and default execution/display/triage policies.
- Kept `analyzers/registry.py` responsible for analyzer execution order and
  fresh analyzer instances.
- Updated Inspection Manifest generation to use descriptor metadata while
  preserving the existing `inspection_manifest.json` shape.
- Added tests that every registered analyzer has one descriptor, every
  descriptor points to a registered analyzer, descriptor identity matches
  analyzer identity, default policies remain enabled / visible / included, and
  current analyzers remain advisory / Technical Quality.
- Did not add analyzer behavior changes, threshold changes, configurable review
  signals, profile UI, review profiles, calibration metrics, plugin support, new
  analyzers, new sidecars, cleanup, execution, export, repair, quarantine
  behavior, or image modification.

## v0.25.0-alpha

- Added Dataset Intelligence to the local Review Desk contract.
- Dataset Intelligence is descriptive, deterministic, evidence-first, and
  sidecar-derived. It organizes existing evidence without scoring or grading
  datasets.
- Added dataset-level review status, evidence summary, analyzer contribution,
  dataset coverage, dataset characteristics, review guidance, and provenance
  sections to the Review Desk payload.
- Used `inspection_manifest.json` and `comparison_summary.json` when present,
  while continuing to work from existing inspect sidecars when optional
  sidecars are absent.
- Kept the image grid and human decision workflow as the primary Review Desk
  work surface.
- Did not add new sidecars, analyzers, analyzer toggles, review profiles,
  scores, pass/fail labels, cleanup, execution, repair, export, quarantine
  folders, file movement, or source image modification.

## v0.24.0-alpha

- Made Dataset Comparison manifest-aware.
- Added advisory `inspection_compatibility` to `comparison_summary.json`.
- Added an Inspection Compatibility section near the top of
  `comparison_summary.md`.
- Comparison now reports compatible manifests, missing manifest provenance, and
  differences in manifest schema, inspection profile, Dataset Forge version,
  analyzer participation, analyzer versions, display policy, and triage policy.
- Kept comparison non-blocking and sidecar-only. It does not rerun analyzers,
  reinterpret findings, inspect source images, modify inputs, or change
  existing comparison fields.
- Kept analyzer behavior, thresholds, recommendations, Review Desk behavior,
  review decision schema, existing sidecar schemas, cleanup, execution, export,
  repair, transforms, quarantine behavior, image handling, profile UI, analyzer
  toggles, configurable review signals, dataset analytics, and new analyzers
  out of scope.

## v0.23.0-alpha

- Added `inspection_manifest.json` from `dataset-forge inspect`.
- Added schema `dataset-forge/inspection-manifest/v1`.
- Recorded Dataset Forge tool version, default inspection profile, inspect
  inputs, sidecar schema references, analyzer descriptors, analyzer versions,
  analyzer families, advisory calibration status, current enabled / visible /
  included policies, per-analyzer finding counts, and compatibility metadata.
- Kept `disabled_analyzers` empty; configurable review signals are not
  implemented.
- Preserved analyzer execution, analyzer thresholds, recommendation behavior,
  Review Desk behavior, comparison behavior, review decision schema, existing
  sidecar schemas, CLI command surface, and all read-only guarantees.
- Kept cleanup, execution, export, repair, transforms, quarantine behavior,
  profile UI, analyzer toggles, dataset analytics, and new analyzers out of
  scope.

## v0.22.0-alpha

- Split Review Desk sidecar loading and deterministic payload construction into
  `review_desk.py`.
- Kept `review_server.py` focused on localhost HTTP routing, image serving, the
  decision save endpoint, and the browser shell.
- Documented the internal Review Desk data contract:
  `dataset-forge/review-desk-data/v1`.
- Added direct tests for Review Desk payload shape, deterministic overview,
  review progress, top finding categories, analyzer coverage, and next-action
  builders.
- Preserved existing Review Desk behavior, public CLI surface,
  `review_decisions.json` schema v2, and read-only guarantees.
- Kept profiles, configurable review signals, cleanup, execution, export,
  repair, source-image modification, file movement, analyzer threshold changes,
  and new analyzer families out of scope.

## v0.21.0-alpha

- Added a Dataset Overview to the local Review Desk.
- Added computed review progress, triage counts, decision counts, workflow
  counts, top finding categories, and analyzer coverage summaries to the
  Review Desk data payload.
- Added deterministic next-action guidance so the desk can point reviewers to
  undecided Priority Review images first, then Needs Review images, then
  optional No Findings Emitted sampling.
- Added Review Desk controls for applying the next action and clearing filters.
- Clarified that Quarantine Planned is workflow intent only and does not create
  folders, move files, copy files, export datasets, or modify images.
- Kept `review_decisions.json` on schema
  `dataset-forge/review-decisions/v2`.
- Kept execution, cleanup, export, repair, source-image modification, analyzer
  threshold changes, and new analyzer families out of scope.

## v0.20.0-alpha

- Added the local browser-based Review Desk as the primary human-facing review
  workflow from `dataset-forge review <inspect_output>`.
- Made Review Desk data image-centered: one card per image with nested
  findings, evidence summaries, triage status, analyzer coverage, suggested
  review action, and No Findings Emitted entries.
- Added browser filters for decision, workflow state, triage group, finding
  category, severity, confidence, and search text.
- Added Review Decisions schema v2:
  `dataset-forge/review-decisions/v2`.
- Added v1 review decision migration on load.
- Added human decisions: Keep, Accepted Style / False Positive, Improvement
  Candidate, Exclude Candidate, and Undecided.
- Added separate workflow state: In Dataset, Quarantine Planned, and Reviewed.
- Added notes persistence in `review_decisions.json`.
- Added read-only zoom/lightbox viewing with fit, actual size, zoom in/out,
  mouse wheel zoom, drag pan, previous/next, Space, and Escape support.
- Improved `inspect` end-of-run output with a Start Here block pointing to the
  Review Desk command, output directory, and key files.
- Kept execution, cleanup, export, repair, file movement, quarantine folder
  creation, source-image modification, and pixel modification out of scope.

## v0.19.0-alpha

- Replaced user-facing legacy training-ready language with
  `No Findings Emitted`.
- Added image-centered recommendation evidence: each recommendation now nests
  finding evidence under the image while retaining stable finding references.
- Added analyzer coverage summaries to `recommendation_summary.json` and
  `recommendation_summary.md`.
- Added image-level triage dossier sidecars:
  `triage_dossiers.json` and `triage_dossiers.md`.
- Clarified no-finding semantics: no finding means no current deterministic
  analyzer emitted a review signal, not that an image is artifact-free or
  guaranteed suitable for LoRA training.
- Reworded Priority Review guidance as review ordering, not an instruction to
  exclude, clean, export, or modify an image.
- Reworded Improvement Plan suggested improvements for artifact families as
  review-oriented labels.
- Kept execution, cleanup, export, repair, source-image modification, and pixel
  modification explicitly out of scope.

## v0.18.0-alpha

- Added `dataset-forge preview <improvement_plan.json>`.
- Added execution-free Improvement Preview over existing `improvement_plan.json`
  plus optional `review_decisions.json` and optional `comparison_summary.json`.
- Added `improvement_preview.json` with schema
  `dataset-forge/improvement-preview/v1`.
- Added `improvement_preview.md` explaining each Improvement Candidate,
  Suggested Improvement, evidence, triggering findings, review decision,
  planning status, execution availability, and expected outcome.
- Set execution availability to `Not Implemented`.
- Kept analyzer behavior, recommendation behavior, planning behavior, existing
  report schemas, source images, cleanup execution, repair, export, browser UI,
  and image processing unchanged.

## v0.17.0-alpha

- Added `dataset-forge plan <inspect_output>`.
- Added advisory Improvement Planning over existing sidecars:
  `inspection_report.json`, `recommendation_summary.json`, optional
  `review_decisions.json`, and optional `comparison_summary.json`.
- Added `improvement_plan.json` with schema
  `dataset-forge/improvement-plan/v1`.
- Added `improvement_plan.md` with Improvement Candidates, Deferred
  Improvement Candidates, Suppressed Improvement Candidates, and Suggested
  Improvements.
- Integrated existing review decisions into planning: confirmed artifacts
  remain eligible, false positives/acceptable style/ignored scopes suppress
  planning, locked images prevent candidates, and unresolved review defers
  planning.
- Kept analyzer behavior, recommendation rules, comparison behavior, inspect
  output schemas, review server behavior, source images, cleanup execution,
  repair, export, browser UI, and image processing unchanged.

## v0.16.0-alpha

- Improved first-time user onboarding for the LoRA Dataset Decision Engine.
- Reworked the README opening around the normal user workflow:
  inspect a dataset, read recommendations, review flagged images, record human
  decisions, compare runs, then train.
- Added a 60-second Quick Start with concrete commands and expected outputs.
- Updated CLI help text to use user workflow language instead of architecture
  language.
- Made common missing-sidecar errors more actionable by telling users to run
  `dataset-forge inspect <dataset>` first and pass the inspect output folder.
- Kept analyzer behavior, recommendation behavior, report schemas, comparison
  behavior, commands, cleanup, repair, export, browser features, and source
  images unchanged.

## v0.15.0-alpha

- Added `dataset-forge compare <before_inspect_output> <after_inspect_output>
  --output <comparison_output>`.
- Added deterministic sidecar-only Dataset Comparison over existing
  `inspection_report.json`, `recommendation_summary.json`, and optional
  `review_decisions.json`.
- Added `comparison_summary.json` with schema
  `dataset-forge/comparison-summary/v1`.
- Added `comparison_summary.md` ordered for human review: changed
  recommendations, new findings, resolved findings, then count deltas.
- Kept analyzer behavior, recommendation rules, inspect output schemas, review
  decisions, source images, cleanup, repair, export, browser UI, charts,
  scores, and pixel comparison unchanged.

## v0.14.0-alpha

- Added optional `dataset-forge review <inspect_output>`.
- Added a local-only review decision server bound to `127.0.0.1`.
- The review server reads existing inspect sidecars and writes only
  `review_decisions.json` using the existing
  `dataset-forge/review-decisions/v1` schema.
- Existing review decisions are loaded, same image/category/analyzer scopes are
  updated, unrelated decisions are preserved, and duplicate scopes are rejected.
- Kept recommendation rules, `recommendation_summary.json`,
  `inspection_report.json`, analyzer behavior, contact sheets, static gallery,
  cleanup, repair, export, schemas, and source images unchanged.

## v0.13.0-alpha

- Added persistent human review-decision sidecars to inspect runs.
- `dataset-forge inspect` now writes `review_decisions_template.json` only when
  the template does not already exist.
- Existing `review_decisions.json` files are loaded and preserved; existing
  templates and human decision files are never overwritten.
- `recommendation_summary.md` and optional `review_gallery.html` now display
  Already Reviewed / Pending Review status and recorded decision labels.
- Kept recommendation rules, `recommendation_summary.json`,
  `inspection_report.json`, analyzer behavior, contact sheets, cleanup, repair,
  export, schemas, and public CLI command surface unchanged.

## v0.12.0-alpha

- Improved `recommendation_summary.md` and `review_gallery.html` explainability.
- Added visible recommendation explanations using existing finding references:
  primary reason, finding categories, severity, analyzer names, and finding
  count.
- Added Dataset Summary blocks with counts and most common finding categories.
- Kept recommendation rules, `recommendation_summary.json`,
  `inspection_report.json`, analyzer behavior, validation, review decisions,
  contact sheets, cleanup, repair, export, schemas, and public CLI command
  surface unchanged.

## v0.11.0-alpha

- Added optional `dataset-forge inspect --contact-sheets` output.
- Added `priority_review_contact_sheet.png` and
  `needs_review_contact_sheet.png`, read-only visual review aids generated from
  existing `inspection_report.json` and `recommendation_summary.json` sidecars.
- Empty Priority Review or Needs Review groups produce deterministic
  empty-state sheets. Images without emitted findings do not get contact
  sheets by default.
- Kept recommendation rules, `recommendation_summary.json`, inspect schema,
  analyzer behavior, public CLI command surface, review-decision coupling,
  validation coupling, cleanup, repair, export, plugins, web app behavior, and
  analyzer set unchanged.

## v0.10.0-alpha

- Added optional `dataset-forge inspect --review-gallery` output.
- Added `review_gallery.html`, a static read-only visual review surface over
  existing `inspection_report.json` and `recommendation_summary.json` sidecars.
- Kept recommendation rules, `recommendation_summary.json`, inspect schema,
  analyzer behavior, public CLI command surface, review-decision coupling,
  validation coupling, cleanup, repair, export, plugins, UI frameworks, and
  analyzer set unchanged.

## v0.9.0-alpha

- Polished `recommendation_summary.md` into a human-facing review report.
- Added Markdown sections for dataset counts, recommended review order,
  artifact-family grouping, important notes, and next steps.
- Summarized images without emitted findings instead of listing every such
  image.
- Kept recommendation rules, `recommendation_summary.json`, inspect schema,
  CLI surface, analyzer behavior, validation coupling, review-decision
  coupling, repair, cleanup, export, plugins, UI, and analyzer set unchanged.

## v0.8.0-alpha

- Made Recommendation Summary user-visible from `dataset-forge inspect` via
  additive `recommendation_summary.json` and `recommendation_summary.md`
  sidecar outputs.
- Added concise terminal aggregate counts for images without emitted findings,
  Needs Review, and Priority Review.
- Preserved the four-rule recommendation engine exactly and kept
  recommendations reproducible from `inspection_report.json` alone.
- Kept `inspection_report.json`, analyzer behavior, thresholds, public CLI
  command surface, validation coupling, review-decision coupling, repair,
  cleanup, export, plugins, UI, and analyzer set unchanged.

## v0.7.0-alpha

- Added an internal Recommendation Summary layer with schema
  `dataset-forge/recommendation-summary/v1`.
- Added the deliberately small four-rule engine for no-finding, Needs Review,
  and Priority Review guidance over existing findings only.
- Kept CLI behavior, inspect output, analyzer behavior, confidence handling,
  validation coupling, review-decision coupling, repair, cleanup, export,
  plugins, UI, and analyzer set unchanged.

## v0.6.0-alpha

- Added the internal Real-World Validation Corpus framework for organizing
  legally safe labeled validation datasets.
- Added corpus manifest validation, Calibration Evidence label compatibility
  checks, optional private/local fixture skipping, and committed placeholder
  methodology fixtures.
- Kept analyzer thresholds, analyzer behavior, inspect output, public CLI
  surface, repair planning, cleanup, repair, export, plugins, UI, and analyzer
  set unchanged.

## v0.5.0-alpha

- Added internal Validation Dossiers for combining existing inspection reports,
  calibration labels, and optional Review Decisions into analyzer reliability
  summaries.
- Added conservative per-category repair-planning readiness statuses,
  false-positive/false-negative examples, review-disagreement counts, and
  threshold-review candidates.
- Kept analyzer thresholds, calibration logic, inspect behavior, public CLI
  surface, repair planning, cleanup, repair, export, plugins, UI, and analyzer
  set unchanged.

## v0.4.0-alpha

- Added internal Review Decisions helpers for schema-versioned human decisions
  over existing inspection report image paths and finding categories.
- Added deterministic decision summaries and helper queries for locked images,
  confirmed findings, false positives, and future-action exclusions.
- Kept analyzer thresholds, calibration logic, inspect behavior, public CLI
  surface, cleanup, repair, export, plugins, UI, and analyzer set unchanged.

## v0.3.0-alpha

- Added internal Calibration Evidence helpers for comparing existing
  `inspection_report.json` output against schema-versioned ground-truth labels.
- Added per-analyzer and per-category TP/FP/FN/TN, precision, recall, F1, and
  false-positive-rate metrics.
- Kept analyzer thresholds, inspect behavior, public CLI surface, cleanup,
  repair, export, plugins, UI, and analyzer set unchanged.

## v0.2.0-alpha

- Shipped the four-analyzer inspect platform:
  Texture, Crystalline Faceting, Oversharpening/Halo, and High-Frequency
  Isolated Artifact analyzers.
- Added the internal analyzer registry, shared context builder, shared image
  primitives, Dataset Summary, Review Queue, stable reports, and public
  benchmark coverage for committed synthetic fixtures.
- Preserved inspect-only, read-only behavior.

## v0.1.0-alpha

- Established the inspect-only foundation for Dataset Forge.
- Added the stable Finding and Analyzer contracts, `dataset-forge inspect`,
  JSON/TXT inspection reports, optional gallery output, and the first public
  benchmark framework.
