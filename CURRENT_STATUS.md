# Dataset Forge -- Current Status

*Last updated: 2026-07-10. v1.7.0 Preview Provider Contract and Capability Model.*

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

Plan is advisory and execution-free. Improvement Preview is planning
infrastructure for future preview generation and is also execution-free.

`improvement_preview.json` records image-centered planning metadata only:
recommended operation, rationale, required provider type, preview status, and
approval state. It does not contain image data, prompts, generated outputs, or
provider calls.

The Review Desk displays Improvement Preview records beside the selected
original image, shows a placeholder when no preview image exists, and lets the
reviewer update approval state only. It does not generate previews, process
images, call providers, execute improvements, or modify source files.

v1.7 defines provider-neutral preview contracts and static capability
matching. Provider descriptors can describe operation support, local/remote
metadata, network or credential requirements, reproducibility characteristics,
and implementation status. Request, result, artifact-reference, and execution
policy models are contracts only. The Review Desk may display derived
compatibility, required capabilities, and execution-unavailable status without
changing `improvement_preview.json` v1.

No provider implementation, discovery, live availability check, credential
storage, networking, subprocess execution, image processing, candidate import,
preview generation, dataset export, or improvement execution exists.

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
- Confirm plan and preview clearly state execution and provider implementations
  are not implemented.
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
- file movement or copying
- broad image similarity or semantic duplicate detection
- duplicate cleanup, file movement, or automatic exclusion
- JPEG cleanup, denoising, upscaling, or repair
- profile UI
- analyzer toggles
- plugin system
- database or cloud features
- quality scores, readiness scores, grades, or pass/fail labels
