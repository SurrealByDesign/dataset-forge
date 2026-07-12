# Benchmark Inventory

This document maps the current validation assets. Analyzer status remains
advisory even when regression fixtures exist.

## Public Benchmark Suite

Run from a fresh clone:

```powershell
uv run python scripts/run_benchmarks.py
```

The public manifest is `benchmarks/benchmark_manifest.json`. Committed fixtures
under `benchmarks/synthetic_defects/` cover positive and negative cases for
microtexture, crystalline faceting, oversharpening/halo evidence, and isolated
high-frequency artifacts.

Analyzer-specific pytest fixtures also cover image encoding, caption metadata,
exact duplicates, and conservative perceptual near-duplicates.

## Optional Private Validation

`benchmarks/local_benchmark_manifest.json`, `benchmarks/real_samples/`, and
`benchmarks/real_world/private/` are local and ignored. They may reference
private datasets but must never be committed.

```powershell
uv run python scripts/run_benchmarks.py `
  --manifest benchmarks/local_benchmark_manifest.json
```

Missing optional private cases are skipped rather than failed.

## Real-World Corpus Framework

`benchmarks/real_world/manifest.json` defines public placeholder and optional
private validation groups. Placeholder fixtures prove wiring and schema
compatibility; they are not evidence of broad real-world reliability.

## Generated Results

Benchmark and research output belongs under `benchmarks/results/`, which is
ignored. Do not cite a local result as public calibration evidence unless its
inputs, labels, licensing, and reproduction steps are committed.

## Known Limits

- Public synthetic fixtures cannot represent the diversity of real artwork.
- Private anthropomorphic-dataset review is useful product validation but is
  not independent calibration evidence.
- False-positive contexts remain important even for fixture-backed analyzers.
- Threshold or confidence changes require dedicated validation, not merely a
  passing regression suite.

See [../benchmarks/README.md](../benchmarks/README.md) for fixture details and
[internal_calibration_notes.md](internal_calibration_notes.md) for clearly
labeled internal history.
