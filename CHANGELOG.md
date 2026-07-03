# Changelog

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
