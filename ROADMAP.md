# Dataset Forge -- Roadmap

This roadmap reflects the v1.x read-only curation workstation direction.

Dataset Forge is a read-only dataset curation workstation. The architecture is
kept stable around inspect, Review Desk, sidecars, comparison, planning, and
improvement preview.

---

## v1.0: Stable Read-Only Curation Workstation

Goal: ship a trustworthy local workflow for LoRA/image dataset review before
training.

v1.0 includes:

- `inspect`
- localhost `review` Review Desk
- persistent `review_decisions.json`
- `compare`
- advisory `plan`
- execution-free `preview`
- current four advisory analyzers
- Inspection Manifest provenance
- policy-aware sidecar semantics
- Dataset Intelligence inside the Review Desk
- clear non-destructive guarantees

v1.0 does not include:

- cleanup
- execution
- export
- repair
- image modification
- file movement
- quarantine folders
- perceptual near-duplicate analyzer
- JPEG cleanup, denoising, upscaling, or repair
- profile UI
- analyzer toggles
- plugin system
- database or cloud features
- quality scores, readiness scores, grades, or pass/fail labels

v1.0 succeeds when a first-time LoRA creator can run inspect, open the Review
Desk, understand which images need attention, record decisions, and trust that
source images were not touched.

---

## v1.0 Hardening Priorities

1. Documentation clarity.
   User docs should describe the current workflow first, not alpha history.

2. Analyzer trust wording.
   Findings must be described as advisory review signals. Known false-positive
   contexts should be visible: JPEG compression/ringing, natural grain,
   watercolor/pencil texture, intentional highlights/glitter, and hard-edge
   line art.

3. Real-dataset validation notes.
   Document what has been validated by automated tests, what has been exercised
   on private/real datasets, and what remains uncalibrated.

4. Review Desk wording polish.
   Ensure the interface does not imply file movement, deletion, automatic
   exclusion, cleanup, quality scoring, or training readiness.

5. Public surface hygiene.
   The public CLI remains limited to inspect/review/compare/plan/preview and
   explicit isolated `preview-import`.

6. Release checks.
   Run the targeted CLI and Review Desk tests, the full suite, and
   `git diff --check`.

---

## v1.1: Exact Duplicate Detection

v1.1 adds advisory exact duplicate detection:

- byte-identical duplicate files
- decoded pixel-identical duplicate images
- deterministic duplicate group IDs
- evidence-based suggested representative
- no near-duplicate, crop, or resize matching
- no cleanup, export, file movement, deletion, quarantine, or automatic
  exclusion

The Review Desk continues to use the existing review queues and image-centered
finding details.

---

## v1.2: Image Encoding Analyzer

v1.2 adds `image_encoding_analyzer/v1` as conservative source-encoding
context:

- obvious JPEG compression context
- 8x8 blocking
- edge ringing or mosquito-noise evidence
- chroma artifacts where practical
- banding/posterization evidence
- tiny compressed source characteristics

JPEG presence alone is not a finding. High-quality JPEGs should not be flagged
only because they are JPEG files. Encoding findings are advisory context that
may explain texture, halo, crystalline, or high-frequency findings; they are
not quality scores, repair instructions, cleanup recommendations, or automatic
exclusion decisions.

---

## Post-v1.2 Direction

Post-v1.2 work should be driven by evidence and user review friction, not by
architecture expansion.

## v1.3: Caption / Metadata Analyzer

v1.3 adds `caption_metadata_analyzer/v1` as conservative metadata consistency
inspection:

- missing image-adjacent `.txt` caption sidecars
- empty caption files
- exact duplicate caption text
- very short captions
- very long captions
- repeated caption boilerplate such as `masterpiece`, `best quality`, or `8k`

This is not caption quality analysis. Dataset Forge does not judge writing
quality, infer image content, optimize prompts, rewrite captions, generate
captions, use ML/LLMs, or make training-readiness claims.

---

## v1.4: Conservative Perceptual Near-Duplicate Analyzer

v1.4 adds `perceptual_duplicate_analyzer/v1` as the final planned analyzer
release.

It detects conservative perceptual near-duplicate groups that are extremely
likely to be the same training example after small edits:

- mild JPEG recompression
- tiny resize
- slight crop
- tiny color shift
- small edit variants that pass multiple deterministic verification signals

It does not perform semantic duplicate detection, character recognition, style
matching, pose matching, prompt matching, face recognition, image search, ML,
embeddings, CLIP, neural network matching, automatic deletion, or automatic
removal recommendations.

---

## Post-v1.4 Direction

The analyzer roadmap is complete.

---

## v1.5: Improvement Preview Framework

v1.5 adds planning infrastructure for future preview generation.

`dataset-forge preview <inspect_output>` writes:

- `improvement_preview.json`
- `improvement_preview.md`

The sidecar records planning metadata only:

- image
- review decision
- current findings
- recommended operation
- operation rationale
- confidence
- required provider type
- preview status
- approval state

Provider types are capability descriptors only. v1.5 does not implement
ComfyUI, Krea, local classical/OpenCV preview generation, manual preview
import, API calls, networking, image processing, prompt generation, preview
image generation, dataset modification, or improvement execution.

Cleanup, repair, and execution remain future-only and should not be treated as
the natural next step after v1.0.

---

## v1.6: Review Desk Preview Workspace

v1.6 adds browser support for reviewing Improvement Preview planning records.

The Review Desk consumes `improvement_preview.json` when present and displays:

- original image
- recommended operation
- operation rationale
- evidence summary
- confidence
- required provider type
- preview status
- approval state

If no preview image exists, the Review Desk shows a clear placeholder. Preview
approval changes update approval-state metadata in `improvement_preview.json`
only.

v1.6 does not generate preview images, perform image processing, integrate
ComfyUI or Krea, call APIs, render providers, execute improvements, modify
datasets, or modify source images.

---

## v1.7: Preview Provider Contract and Capability Model

v1.7 adds provider-neutral preview contracts and capability matching.

The internal contract describes static provider metadata, supported planning
operations, capability claims, provider-neutral request/result records,
isolated preview artifact references, reproducibility metadata, and explicit
execution safety policy. The Review Desk displays derived capability
compatibility and execution-unavailable status.

`dataset-forge/improvement-preview/v1` remains compatible and unchanged.
Capability matching is deterministic and uses static descriptors only; it does
not perform live availability checks.

v1.7 does not add provider implementations, plugin discovery, credentials,
configuration, networking, external API calls, subprocesses, image processing,
preview generation, candidate import, cleanup, export, dataset modification,
or improvement execution.

---

## v1.8: Manual Preview Import and Browser A/B Comparison

v1.8 proves the preview-review loop with a candidate created outside Dataset
Forge. `dataset-forge preview-import <inspect_output> <image-reference>
<candidate-image>` validates and copies one candidate image into the isolated
inspect-output `preview_artifacts/` directory.

`preview_artifacts.json` uses `dataset-forge/preview-artifact/v1` and records
deterministic artifact identity, relative artifact reference, hashes,
dimensions, format, provenance, and metadata warnings. The existing
`dataset-forge/improvement-preview/v1` sidecar remains compatible. The Review
Desk joins the artifact sidecar at load time and provides original/candidate
side-by-side, original-only, and candidate-only A/B views.

Manual import is not provider execution. v1.8 does not generate, process,
edit, resize, crop, repair, export, replace, or move source images. It does not
add Krea or ComfyUI integration, APIs, networking, subprocesses, credentials,
batch import, drag-and-drop upload, provider retries, or automatic candidate
selection.
