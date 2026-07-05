# Changelog

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
