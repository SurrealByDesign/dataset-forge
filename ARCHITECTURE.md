# Dataset Forge -- Architecture

Dataset Forge is an evidence-first, deterministic, read-only, sidecar-based
LoRA/image dataset curation workstation.

The v1.0 architecture is frozen unless a concrete release blocker appears.

---

## Product Boundary

Dataset Forge supports:

```text
inspect
-> review in the local Review Desk
-> record human decisions
-> compare runs
-> plan / preview
```

Dataset Forge does not support cleanup, export, execution, repair, quarantine
folder creation, image modification, file movement, cloud state, databases,
profile editing, analyzer toggles, quality scores, readiness scores, grades, or
pass/fail labels.

Source images are read-only inputs.

---

## Inspect Pipeline

```text
Dataset
-> DatasetContext
-> Analyzer(s)
-> Finding(s)
-> Reports and sidecars
```

`DatasetContext` is the shared read-only statistical reference frame for the
run. It includes image paths, counts, resolution/aspect statistics, texture
distributions, frequency distributions, and duplicate hash context.

Analyzers consume `DatasetContext` and optional shared image measurements. They
emit `Finding` objects only. They must not modify images, call other analyzers,
make cleanup decisions, or maintain hidden mutable state.

---

## Finding Contract

Every analyzer emits the same evidence contract:

```python
Finding(
    image_path=...,
    analyzer="texture_analyzer/v1",
    category="texture.high_microtexture",
    severity=Severity.MEDIUM,
    confidence=0.45,
    false_positive_rate=0.15,
    benchmark_version="uncalibrated",
    evidence={...},
    explanation="...",
    recommendation="...",
)
```

Extensions should live in `evidence`, not new top-level fields, unless there is
a proven cross-analyzer need.

Findings are advisory review signals. They are not automated removal,
cleanup, export, or training-readiness decisions.

---

## Current Analyzers

| Analyzer | Categories | Status |
|---|---|---|
| `texture_analyzer/v1` | `texture.high_microtexture`, `texture.error` | Advisory; first-pass calibration. |
| `crystalline_faceting_analyzer/v1` | `artifact.crystalline_faceting`, error category | Advisory; first-pass calibration. |
| `oversharpening_halo_analyzer/v1` | `artifact.oversharpening_halo`, error category | Advisory; synthetic-fixture-backed. |
| `high_frequency_isolated_artifact_analyzer/v1` | `artifact.high_frequency_isolated`, error category | Advisory; synthetic-fixture-backed. |

Known false-positive contexts include JPEG compression/ringing, low-resolution
JPEG artifacts, natural paper or pencil grain, watercolor/canvas texture,
engraving or etched illustration texture, intentional highlights or glitter,
hard-edge line art, and deliberately rough mixed-media surfaces.

There is no JPEG/compression analyzer in v1.0.

---

## Sidecar Semantics

`inspection_report.json` is the canonical executed-finding record.

`recommendation_summary.json` is triage-based. It organizes images into:

- `No Findings Emitted`
- `Needs Review`
- `Priority Review`

`triage_dossiers.json` is image-centered triage evidence with findings nested
under each image.

`inspection_manifest.json` records provenance: tool version, profile snapshot,
dataset inputs, sidecar schema references, analyzer descriptor snapshots,
effective analyzer policies, counts, and compatibility metadata.

`comparison_summary.json` and `.md` compare existing sidecars and include
advisory manifest compatibility when provenance is available.

`review_decisions.json` is the only file written by the Review Desk. It records
human decisions, workflow state, and notes. It does not move, delete, export,
or modify source images.

---

## Policy-Aware Contracts

Analyzer metadata is owned by `analyzer_descriptors.py`.

Inspection profiles are owned by `inspection_profiles.py`. v1.0 ships only the
default profile with no overrides.

Effective review signal policy is resolved by `review_signal_policy.py`:

```text
AnalyzerDescriptor defaults
-> InspectionProfile overrides
-> ResolvedReviewSignalPolicy
```

Current analyzers resolve to:

```text
execution: enabled
display: visible
triage: included
```

The manifest snapshots effective policy. The Review Desk and Dataset
Intelligence consume generated sidecars and manifest snapshots only; they do
not call analyzers or live descriptor/profile registries.

---

## Review Desk Boundary

`review_desk.py` builds deterministic sidecar-derived payloads.

`review_server.py` owns localhost routing, image serving, browser shell, and
the `review_decisions.json` save endpoint.

The Review Desk must:

- bind locally
- consume generated sidecars
- write only `review_decisions.json`
- preserve the review decision schema
- keep image review as the primary workflow
- make read-only scope visible

It must not run analyzers, inspect pixels, modify reports, modify source
images, move files, create quarantine folders, export datasets, execute
cleanup, or score dataset quality.

---

## Dataset Intelligence

Dataset Intelligence is computed inside the Review Desk contract layer from
existing sidecars. It is descriptive evidence organization only.

It may summarize review status, evidence categories, analyzer contribution,
dataset coverage, dataset characteristics, guidance, and provenance.

It must not create a new sidecar, inspect pixels, run analyzers, score quality,
grade the dataset, produce readiness labels, or generate subjective summaries.

---

## Comparison Boundary

Comparison reads existing inspect outputs. It may read optional
`inspection_manifest.json` files and explain whether provenance differs.

Comparison must not rerun analyzers, inspect images, compare pixels, reinterpret
findings, block by default, modify inputs, or classify changes as better/worse
without explicit sidecar evidence.

---

## Release Hardening Checklist

Before v1.0:

- run the full test suite
- run `git diff --check`
- confirm CLI public surface
- confirm expected sidecars are written
- confirm Review Desk launches locally
- confirm Review Desk writes only `review_decisions.json`
- confirm source image hashes are preserved
- confirm plan/preview remain execution-free
- confirm docs do not imply unavailable features

---

## Future Work Boundary

Duplicate detection, JPEG/compression analysis, metadata/caption review, public
configurable review signals, profile editing, export, cleanup, repair, and
execution are post-v1 possibilities only. They should be considered only after
the v1.0 read-only workstation is stable and trusted.
