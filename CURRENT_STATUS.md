# Dataset Forge -- Current Status

*Last updated: 2026-07-11. v1.9.3 Review Desk UX Polish.*

---

## Product Identity

Dataset Forge is an evidence-first, deterministic, read-only, sidecar-based
LoRA/image dataset curation workstation.

The primary workflow is:

```text
inspect
-> review in the local Review Desk
-> record human decisions
-> compare runs
-> plan
-> improvement preview
-> preview workspace review
```

Source images are never modified. Cleanup, export, repair, execution,
quarantine folders, image modification, databases, cloud services, profile UI,
and analyzer toggles are out of scope for v1.x.

---

## Public Surface

Supported public commands:

- `dataset-forge inspect <path>`
- `dataset-forge review <inspect_output>`
- `dataset-forge compare <before_inspect_output> <after_inspect_output>
  --output <comparison_output>`
- `dataset-forge plan <inspect_output>`
- `dataset-forge preview <inspect_output>`
- `dataset-forge preview-import <inspect_output> <image-reference> <candidate-image>`
- `dataset-forge preview-generate <inspect_output> <image-reference>`
- `dataset-forge --help`
- `dataset-forge --version`

Public commands are sidecar-driven and non-destructive. Future cleanup,
execution, export, plugin, profile, and analyzer-configuration code paths are
not part of the public v1.x product.

---

## Current Workflow Outputs

`inspect` writes:

- `inspection_report.json`
- `inspection_report.txt`
- `recommendation_summary.json`
- `recommendation_summary.md`
- `triage_dossiers.json`
- `triage_dossiers.md`
- `inspection_manifest.json`
- `review_decisions_template.json`
- optional visual review artifacts when requested

`review` reads generated sidecars and writes:

- `review_decisions.json`
- `improvement_preview.json` approval state only, when that optional sidecar
  exists

`compare` writes:

- `comparison_summary.json`
- `comparison_summary.md`

`plan` writes:

- `improvement_plan.json`
- `improvement_plan.md`

`preview` writes:

- `improvement_preview.json`
- `improvement_preview.md`

`preview-import` writes only within the inspect-output workspace:

- `preview_artifacts.json`
- an isolated copy below `preview_artifacts/`

`preview-generate` writes only within the inspect-output workspace:

- `preview_artifacts.json`
- one deterministic LOCAL_CLASSICAL candidate below `preview_artifacts/`
- `improvement_preview.json` preview status / approval metadata

Plan is advisory and execution-free. Improvement Preview is planning
infrastructure plus isolated preview artifacts; it never applies changes to the
source dataset.

`improvement_preview.json` records image-centered planning metadata only:
recommended operation, rationale, required provider type, preview status, and
approval state. It does not contain image data, prompts, generated outputs, or
provider calls.

The Review Desk displays Improvement Preview records beside the selected
original image, shows a placeholder when no candidate preview exists, and lets
the reviewer update approval state only. Candidate generation is an explicit
CLI action; the browser does not generate candidates, call providers, execute
improvements, or modify source files.

v1.8 accepts one explicitly supplied candidate image for an existing preview
plan, validates it with Pillow, copies its unchanged bytes into an isolated
inspect-output artifact directory, and records provenance in
`dataset-forge/preview-artifact/v1`.

v1.9 adds LOCAL_CLASSICAL preview generation for compatible preview-plan
records. It uses deterministic Pillow/NumPy operations only, currently
`REDUCE_HALO` and `REDUCE_ENCODING_ARTIFACTS`. Generated candidates are
disposable preview artifacts, not source images and not exported dataset
images. The Review Desk can show the original and candidate side by side for
A/B review. Candidate approval or rejection affects preview workflow metadata
only; it cannot execute, export, or replace images.

`improvement_preview.json` remains on its v1 schema. Artifact metadata joins
to it by a deterministic record identifier and does not rewrite legacy preview
records merely to normalize them.

No provider discovery, live availability check, credential storage,
networking, subprocess execution, ComfyUI/Krea integration, dataset export,
source replacement, or improvement execution exists. LOCAL_CLASSICAL is the
only implemented preview generator and writes isolated disposable artifacts
only.

v1.9.1 is a stabilization release. It corrects preview-workspace terminology,
serializes localhost sidecar writes, rejects ambiguous duplicate preview-plan
records, improves browser save-failure feedback, and synchronizes release
documentation. It does not add product capabilities or change schemas.

v1.9.2 reorganizes and rewrites the public documentation, standardizes product
terminology, archives obsolete design specifications, and adds focused user,
Review Desk, preview, provider, schema, developer, FAQ, and troubleshooting
guides. Runtime behavior and public sidecar contracts are unchanged.

v1.9.3 continues the stabilization and polish phase. It shortens the Review
Desk's initial viewport, keeps decisions accessible while reviewing evidence,
clarifies plan and candidate-preview states, separates decision progress from
the Review Complete workflow stage, and orders Priority Review work using
existing evidence deterministically. It also handles malformed legacy ordering
values safely. Schemas, analyzers, providers, workflows, and persistence
semantics are unchanged.

---

## Current Analyzers

| Analyzer | Category | Status |
|---|---|---|
| `texture_analyzer/v1` | `texture.high_microtexture` | Advisory; first-pass calibration. |
| `crystalline_faceting_analyzer/v1` | `artifact.crystalline_faceting` | Advisory; first-pass calibration. |
| `oversharpening_halo_analyzer/v1` | `artifact.oversharpening_halo` | Advisory; synthetic-fixture-backed. |
| `high_frequency_isolated_artifact_analyzer/v1` | `artifact.high_frequency_isolated` | Advisory; synthetic-fixture-backed. |
| `duplicate_detection_analyzer/v1` | `dataset.duplicate.exact` | Advisory; exact/content duplicate only. |
| `image_encoding_analyzer/v1` | `source_encoding.*` | Advisory; source-encoding context only. |
| `caption_metadata_analyzer/v1` | `caption.*` | Advisory; metadata consistency only. |
| `perceptual_duplicate_analyzer/v1` | `duplicate.perceptual` | Advisory; conservative near-duplicate groups only. |

Current analyzers are useful review signals, not final judgments. They are
deterministic and emit evidence, but they are not published real-world
calibrated detectors.

Known false-positive contexts to review carefully:

- JPEG compression, ringing, mosquito noise, chroma artifacts, and banding.
- Low-resolution JPEG/compression artifacts.
- Natural paper, pencil, watercolor, canvas, or scan grain.
- Engraving or etched illustration texture.
- Intentional highlights, glitter, stars, freckles, and decorative specks.
- Hard-edge line art, ink outlines, and crisp transitions.
- Mixed-media or intentionally rough texture.

Image Encoding Analyzer findings are source-context review signals. JPEG
presence alone is not a finding, and high-quality JPEGs should not be flagged
only because they are JPEG files. Encoding findings can help explain texture,
halo, crystalline, or high-frequency findings, but they are not quality scores,
readiness labels, repair instructions, or automatic exclusion decisions.

Caption / Metadata Analyzer findings are metadata consistency review signals.
They inspect common image-adjacent `.txt` caption sidecars for missing, empty,
exact duplicate, very short, very long, or repeated-boilerplate captions. They
do not judge caption writing quality, optimize prompts, rewrite captions,
generate captions, use ML/LLMs, or make training-readiness claims.

Duplicate detection includes exact/content duplicates and conservative
perceptual near-duplicate groups. The perceptual analyzer is precision-first
and requires multiple deterministic classical signals before emitting a
finding. It is meant for images that are extremely likely to be the same
training example after small edits such as mild recompression, tiny resize,
slight crop, or tiny color shift. It does not perform semantic duplicate
detection, character recognition, style matching, pose matching, prompt
matching, face recognition, image search, ML, embeddings, CLIP, or neural
network matching. Suggested representatives are advisory; no files are moved,
deleted, copied, quarantined, excluded, generated, or modified.

---

## Validation Notes

Validated by automated tests:

- inspect pipeline and report writing
- current analyzer contracts and synthetic fixture behavior
- Recommendation Summary and Triage Dossier generation
- Inspection Manifest provenance
- policy-aware sidecar semantics
- Review Desk data contract and localhost server behavior
- Review Decision schema v2 and migration behavior
- manifest-aware comparison
- advisory Improvement Planning, planning-only Improvement Preview, and Review
  Desk preview workspace behavior
- provider contract validation, isolated artifact-reference rules, and
  deterministic capability matching
- manual candidate import, isolated artifact provenance, and Review Desk A/B
  candidate display
- public CLI surface

Validated by project/private review work:

- the workflow has been exercised on the anthropomorphic LoRA dataset
- early analyzer thresholds and wording were informed by private dataset review
- known weak spots such as crystalline grain 45-55 interleaving remain
  documented and advisory

Not yet validated enough to claim calibrated public reliability:

- real-world precision/recall for all analyzers
- JPEG/compression separation beyond conservative v1.2 context signals
- public caption-quality calibration or semantic caption evaluation
- cross-style performance beyond current fixtures and private review data
- perceptual near-duplicate review

---

## v1.x Release Checklist

Before tagging a v1.x release:

- Run `python -m pytest tests/test_cli_surface.py -q`.
- Run `python -m pytest tests/test_review_server.py -q`.
- Run `python -m pytest -q`.
- Run `git diff --check`.
- Confirm public help exposes only intended commands.
- Confirm inspect writes expected sidecars.
- Confirm the Review Desk launches locally.
- Confirm the Review Desk writes `review_decisions.json` and only preview
  approval state in `improvement_preview.json` when that optional sidecar exists.
- Confirm source image hashes are unchanged after inspect/review/compare/plan/preview.
- Confirm plan and preview clearly distinguish implemented LOCAL_CLASSICAL
  candidate generation from unavailable dataset execution and descriptor-only
  external providers.
- Confirm docs do not imply cleanup, export, execution, repair, profile toggles,
  analyzer toggles, or image modification are available.
- Confirm Review Desk wording does not imply file movement, deletion,
  automatic exclusion, training readiness, or quality scoring.

---

## Out Of Scope For v1.x

- cleanup
- execution
- export
- repair
- quarantine folder creation
- source-image modification
- source-dataset file movement or copying
- broad image similarity or semantic duplicate detection
- duplicate cleanup, file movement, or automatic exclusion
- JPEG cleanup, denoising, upscaling, or repair
- profile UI
- analyzer toggles
- plugin system
- database or cloud features
- quality scores, readiness scores, grades, or pass/fail labels
