# Changelog

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
  empty-state sheets. Ready for Training images do not get contact sheets by
  default.
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
- Summarized Ready for Training images instead of listing every ready image.
- Kept recommendation rules, `recommendation_summary.json`, inspect schema,
  CLI surface, analyzer behavior, validation coupling, review-decision
  coupling, repair, cleanup, export, plugins, UI, and analyzer set unchanged.

## v0.8.0-alpha

- Made Recommendation Summary user-visible from `dataset-forge inspect` via
  additive `recommendation_summary.json` and `recommendation_summary.md`
  sidecar outputs.
- Added concise terminal aggregate counts for Ready for Training, Needs Review,
  and Priority Review.
- Preserved the four-rule recommendation engine exactly and kept
  recommendations reproducible from `inspection_report.json` alone.
- Kept `inspection_report.json`, analyzer behavior, thresholds, public CLI
  command surface, validation coupling, review-decision coupling, repair,
  cleanup, export, plugins, UI, and analyzer set unchanged.

## v0.7.0-alpha

- Added an internal Recommendation Summary layer with schema
  `dataset-forge/recommendation-summary/v1`.
- Added the deliberately small four-rule engine for Ready for Training,
  Needs Review, and Priority Review guidance over existing findings only.
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
