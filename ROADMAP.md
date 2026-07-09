# Dataset Forge -- Roadmap

This roadmap reflects the v1.x read-only curation workstation direction.

Dataset Forge is a read-only dataset curation workstation. The architecture is
kept stable around inspect, Review Desk, sidecars, comparison, planning, and
preview.

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
   The public CLI remains limited to inspect/review/compare/plan/preview.

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

## Post-v1.3 Direction

Post-v1.3 work should be driven by evidence and user review friction, not by
architecture expansion.

Likely v1.4 priorities:

- strengthen analyzer validation and calibration notes
- add legally safe real-world validation fixtures if available
- improve Review Desk ergonomics only where real review sessions show friction
- conservative perceptual near-duplicate review only after exact duplicate and
  encoding-context validation

Later possibilities:

- public configurable review signals and profile selection, using the existing
  descriptor/profile/policy/manifest foundation
- diversity/style-consistency review signals
- non-destructive export or copy workflows only after human-review trust is
  strong

Cleanup, repair, and execution remain future-only and should not be treated as
the natural next step after v1.0.
