# Dataset Forge -- Architecture

v1.9.2 is a documentation and product-language release. The architecture and
runtime workflow remain unchanged from v1.9.1.

Dataset Forge is an evidence-first, deterministic, read-only, sidecar-based
LoRA/image dataset curation workstation.

The v1.x architecture remains read-only and review-first. New analyzer
capabilities must preserve the existing sidecar and Review Desk workflow.

---

## Product Boundary

Dataset Forge supports:

```text
inspect
-> review in the local Review Desk
-> record human decisions
-> compare runs
-> plan
-> improvement preview
```

Dataset Forge does not support cleanup, export, execution, repair, quarantine
folder creation, source-image modification, source-dataset file movement,
cloud state, databases,
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
| `duplicate_detection_analyzer/v1` | `dataset.duplicate.exact` | Advisory; exact/content duplicate only. |
| `image_encoding_analyzer/v1` | `source_encoding.jpeg_compression`, `source_encoding.jpeg_blocking`, `source_encoding.jpeg_ringing`, `source_encoding.chroma_artifact`, `source_encoding.banding`, `source_encoding.low_source_quality` | Advisory; source-encoding context only. |
| `caption_metadata_analyzer/v1` | `caption.missing`, `caption.empty`, `caption.duplicate`, `caption.short`, `caption.long`, `caption.token_imbalance` | Advisory; metadata consistency only. |
| `perceptual_duplicate_analyzer/v1` | `duplicate.perceptual` | Advisory; conservative perceptual near-duplicate groups only. |

Known false-positive contexts include JPEG compression/ringing, low-resolution
JPEG artifacts, natural paper or pencil grain, watercolor/canvas texture,
engraving or etched illustration texture, intentional highlights or glitter,
hard-edge line art, and deliberately rough mixed-media surfaces.

Image encoding analysis is intentionally contextual. JPEG presence alone is not
a finding, and high-quality JPEGs should not be flagged only because they are
JPEG files. Encoding findings may explain what other analyzers are seeing, but
they are not quality scores, readiness labels, repair instructions, or cleanup
recommendations.

Caption metadata analysis is intentionally non-semantic. It reads common
image-adjacent `.txt` caption sidecars and reports observable metadata
consistency evidence. It does not judge caption writing quality, infer image
content, optimize prompts, rewrite captions, generate captions, use ML/LLMs,
or make training-readiness claims.

Duplicate detection is intentionally narrow. It emits advisory findings for
byte-identical files, decoded pixel-identical images, and conservative
perceptual near-duplicate groups. The perceptual analyzer requires multiple
deterministic classical image signals before emitting a finding. It is not
semantic duplicate detection, character recognition, style matching, pose
matching, prompt matching, face recognition, image search, ML, embeddings,
CLIP, or neural network matching. Suggested representatives are evidence-based
review prompts, not automatic exclusion decisions.

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

`review_decisions.json` records human decisions, workflow state, and notes.
The Review Desk writes it when users save review decisions. It does not move,
delete, export, or modify source images.

`improvement_preview.json` and `.md` are planning infrastructure for future
preview generation. They are built from existing sidecars and record image,
review decision, current findings, recommended operation, operation rationale,
confidence, required provider type, preview status, and approval state.

`preview_artifacts.json` is an optional v1.8+ sidecar with schema
`dataset-forge/preview-artifact/v1`. It is the single authoritative record for
one preview candidate per deterministic preview-plan record. Candidates may be
manual imports or deterministic LOCAL_CLASSICAL preview artifacts. It stores
only relative artifact references below the inspect-output `preview_artifacts/`
workspace, plus hashes, dimensions, format, provider provenance, generation
parameters when present, and descriptive mismatch warnings. It does not change
`dataset-forge/improvement-preview/v1`.

Improvement Preview provider types are `LOCAL_CLASSICAL`, `COMFYUI`, `KREA`,
`MANUAL`, and `UNKNOWN`. LOCAL_CLASSICAL is the only implemented preview
generator. ComfyUI and Krea remain descriptor-only and unavailable.

`preview_provider_contract.py` owns the immutable, provider-neutral v1.7
contract: provider descriptors, capability metadata, request/result records,
isolated artifact references, execution safety policy, and deterministic
capability matching. It contains no executable provider base class, plugin
discovery, live availability checks, networking, subprocess, credential, or
future-provider implementation path.

`local_classical_preview.py` owns the narrow v1.9 LOCAL_CLASSICAL preview
generator. It uses deterministic Pillow/NumPy operations for compatible
Improvement Preview records and writes candidates only through
`preview_artifacts.py`. It is not a cleanup engine, repair pipeline, export
path, provider framework, or source-image writer.

The existing `dataset-forge/improvement-preview/v1` sidecar remains unchanged.
`improvement_preview.py` retains its compatible embedded descriptor snapshot,
while the Review Desk derives richer capability compatibility at load time
from static contract descriptors. This derived browser data is not persisted
to the planning sidecar.

The Review Desk consumes `improvement_preview.json` and optional
`preview_artifacts.json` when present. It displays a selected-image workspace
with the original source image, planning operation, provenance, candidate
metadata, and side-by-side A/B view when a candidate artifact is
available. Candidate images are served only by allow-listed artifact ID, never
by a browser-supplied filesystem path. The only Review Desk write to the plan
sidecar is approval-state workflow metadata. Candidate generation remains an
explicit CLI action outside the browser server.

Provider compatibility means only that a static descriptor claims the
operation and required capabilities. For LOCAL_CLASSICAL, v1.9 provides a
local deterministic preview generator. It still never means source-dataset
modification, export, cleanup execution, external provider access, or training
readiness.

---

## Policy-Aware Contracts

Analyzer metadata is owned by `analyzer_descriptors.py`.

Inspection profiles are owned by `inspection_profiles.py`. v1.x ships only the
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

`review_server.py` owns localhost routing, allow-listed source/candidate image
serving, browser shell, the `review_decisions.json` save endpoint, and the
Improvement Preview approval-state save endpoint. `preview_artifacts.py` owns
the narrow CLI import/generation artifact services and atomic artifact-sidecar
writes. The localhost server serializes its read-modify-write sidecar updates
within one process so overlapping autosaves cannot silently overwrite each
other.

The Review Desk must:

- bind locally
- consume generated sidecars
- write only `review_decisions.json` plus approval-state metadata in
  `improvement_preview.json` when that optional sidecar exists
- read optional artifact metadata and candidate bytes without accepting
  arbitrary artifact paths from the browser
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

Before a v1.x release:

- run the full test suite
- run `git diff --check`
- confirm CLI public surface
- confirm expected sidecars are written
- confirm Review Desk launches locally
- confirm Review Desk writes `review_decisions.json` and only preview approval
  state in `improvement_preview.json` when that optional sidecar exists
- confirm source image hashes are preserved
- confirm plan/preview remain execution-free
- confirm docs do not imply unavailable features

---

## Future Work Boundary

Semantic caption evaluation, broad image similarity, public configurable review
signals, profile editing, export, cleanup, repair, and dataset execution are not
current product capabilities or roadmap commitments. JPEG cleanup, denoising,
upscaling, image repair, caption rewriting, prompt generation, automatic
duplicate removal, and image search remain out of scope.
