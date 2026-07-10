# Dataset Forge

Dataset Forge is a read-only LoRA/image dataset curation workstation.

It helps you inspect image datasets, review deterministic evidence, record
human decisions, compare inspection runs, prepare advisory improvement plans,
write planning-only Improvement Preview sidecars, and review those preview
plans in the browser before training. Source images are never modified.

The primary workflow is:

```text
inspect
-> review in the local Review Desk
-> record human decisions
-> compare runs
-> plan
-> improvement preview
-> preview workspace review
-> train with the images you choose
```

Dataset Forge does not clean, repair, export, move, delete, quarantine, or edit
images. It does not train models. Findings are advisory review signals, not
automatic judgments.

---

## Quick Start

Install:

```text
git clone https://github.com/surrealbydesign/dataset-forge.git
cd dataset-forge
uv sync
```

Inspect a dataset:

```text
uv run dataset-forge inspect my_dataset/
```

Open the Review Desk:

```text
uv run dataset-forge review my_dataset/inspect_output/
```

The Review Desk is the primary human-facing workflow. It shows images,
evidence, triage groups, Dataset Intelligence, decision controls, and
Improvement Preview planning records when `improvement_preview.json` exists.
Decisions save locally to:

```text
review_decisions.json
```

---

## Public Commands

| Command | Purpose |
|---|---|
| `dataset-forge inspect <dataset>` | Inspect images and write deterministic sidecars. |
| `dataset-forge review <inspect_output>` | Open the localhost Review Desk and save decisions. |
| `dataset-forge compare <before> <after> --output <dir>` | Compare two existing inspect outputs. |
| `dataset-forge plan <inspect_output>` | Write an advisory Improvement Plan from sidecars. |
| `dataset-forge preview <inspect_output>` | Write planning-only Improvement Preview sidecars from existing sidecars. |

There is no public cleanup, repair, export, execution, profile selection,
analyzer toggle, plugin, database, cloud, or hosted-review command.

---

## Outputs

Common files in `inspect_output/`:

| Output | Meaning |
|---|---|
| `inspection_report.json` | Machine-readable executed findings and evidence. |
| `inspection_report.txt` | Plain-text inspection report. |
| `recommendation_summary.json` | Triage-based No Findings Emitted / Needs Review / Priority Review sidecar. |
| `recommendation_summary.md` | Human-readable review-order report. |
| `triage_dossiers.json` | Image-level triage evidence built from triage-included findings. |
| `triage_dossiers.md` | Human-readable image-level dossiers. |
| `inspection_manifest.json` | Provenance for how inspect ran. |
| `review_decisions_template.json` | Starter review-decision sidecar. |
| `review_decisions.json` | Local Review Desk decisions, workflow state, and notes. |
| `comparison_summary.json` / `.md` | Optional comparison output. |
| `improvement_plan.json` / `.md` | Optional advisory plan. |
| `improvement_preview.json` / `.md` | Optional planning infrastructure for future preview generation. |

Optional visual aids:

```text
uv run dataset-forge inspect my_dataset/ --review-gallery --contact-sheets
```

These can write `review_gallery.html`, `priority_review_contact_sheet.png`, and
`needs_review_contact_sheet.png`. They are read-only artifacts.

---

## What The Review Labels Mean

`Priority Review`: review these images first. They have analyzer errors, high
severity findings, or findings across multiple categories.

`Needs Review`: at least one advisory finding was emitted.

`No Findings Emitted`: no current analyzer emitted a review finding for the
image. This does not prove the image is artifact-free, caption-ready, or
suitable for training.

The recommendation summary is intentionally simple and deterministic. It has no
quality score, readiness score, grade, pass/fail result, or hidden priority
model.

---

## Current Analyzers

| Analyzer | Detects | Status |
|---|---|---|
| `texture_analyzer/v1` | Elevated microtexture density relative to the dataset baseline. | Advisory; first-pass calibration. |
| `crystalline_faceting_analyzer/v1` | Angular micro-polygon / crystalline surface faceting. | Advisory; first-pass calibration. |
| `oversharpening_halo_analyzer/v1` | Edge-localized residuals consistent with oversharpening or halos. | Advisory; synthetic-fixture-backed. |
| `high_frequency_isolated_artifact_analyzer/v1` | Sparse isolated high-frequency residual components such as bright or dark specks. | Advisory; synthetic-fixture-backed. |
| `duplicate_detection_analyzer/v1` | Byte-identical and decoded pixel-identical duplicate images. | Advisory; exact/content duplicates only. |
| `image_encoding_analyzer/v1` | Source-encoding context such as obvious JPEG compression, blocking, ringing, chroma artifacts, banding, or tiny compressed sources. | Advisory; context only. |
| `caption_metadata_analyzer/v1` | Image-adjacent `.txt` caption sidecar presence and consistency. | Advisory; metadata consistency only. |
| `perceptual_duplicate_analyzer/v1` | Conservative perceptual near-duplicate groups after small edits. | Advisory; precision-first. |

All current analyzers are deterministic and read-only. They emit evidence,
severity, confidence, false-positive-rate estimates, and plain-language
recommendations. They remain review signals, not final judgments.

### Known False-Positive Contexts

Review findings carefully when images contain:

- JPEG compression, ringing, mosquito noise, or chroma artifacts.
- Low-resolution JPEG/compression artifacts.
- Natural paper, pencil, watercolor, canvas, or scan grain.
- Engraving or etched illustration texture.
- Intentional glitter, stars, freckles, sparkles, highlights, or decorative
  specks.
- Hard-edge line art, ink outlines, or naturally crisp transitions.
- Mixed media, textured brushes, or intentionally rough surfaces.

### Image Encoding

Dataset Forge v1.2 includes `image_encoding_analyzer/v1` as an advisory source
context signal. JPEG presence alone is not a finding, and high-quality JPEGs
should not be flagged just because they are JPEG files.

The analyzer may emit findings for obvious compression context, 8x8 blocking,
edge ringing or mosquito-noise evidence, chroma artifacts, banding, or tiny
compressed source characteristics. These findings can help explain texture,
halo, crystalline, or high-frequency findings from other analyzers, but they
are not quality scores or automatic defects.

Dataset Forge does not repair, denoise, upscale, clean, exclude, export, move,
or modify images.

---

### Caption / Metadata

Dataset Forge v1.3 includes `caption_metadata_analyzer/v1` as an advisory
metadata consistency signal. It inspects common image-adjacent `.txt` caption
sidecars such as `image.png` plus `image.txt`.

It may emit findings for missing caption sidecars, empty caption files, exact
duplicate caption text, very short captions, very long captions, or repeated
caption boilerplate such as `masterpiece`, `best quality`, or `8k`.

It does not judge writing quality, optimize prompts, suggest captions, rewrite
captions, use ML/LLMs, or make training-readiness claims.

---

### Duplicate Detection

Dataset Forge includes exact duplicate detection and conservative perceptual
near-duplicate detection as advisory review signals.

Exact duplicate detection finds byte-identical files and decoded
pixel-identical images, including images with the same pixels but different
filenames or metadata.

Perceptual near-duplicate detection is intentionally stricter than general
image matching. It requires multiple deterministic classical signals before
emitting `duplicate.perceptual`, and is intended for cases that are extremely
likely to be the same training example after small edits such as mild JPEG
recompression, tiny resize, slight crop, or tiny color shift.

It does not perform semantic duplicate detection, character recognition, style
matching, pose matching, prompt matching, face recognition, image search, ML,
embeddings, CLIP, or neural network matching. Suggested representatives are
based on deterministic evidence such as dimensions, pixel count, format,
compression risk, bytes per pixel, and path tie-breaks. Dataset Forge never
moves, deletes, copies, quarantines, excludes, generates, or modifies source
files.

---

## Safety Guarantees

- Source images are never modified, moved, renamed, deleted, exported, or
  quarantined.
- `inspect` writes reports and sidecars only.
- `review` serves a local browser workflow, writes human decisions to
  `review_decisions.json`, and can update preview approval state in
  `improvement_preview.json` when that sidecar exists.
- `compare` reads existing sidecars and writes comparison summaries only.
- `plan` writes advisory Improvement Plan files only.
- `preview` writes planning-only Improvement Preview files only.
- Dataset Forge does not execute cleanup, repair images, export datasets, train
  models, contact cloud services, or use a database.

## Improvement Preview

`dataset-forge preview <inspect_output>` writes `improvement_preview.json` and
`improvement_preview.md` from existing inspection, recommendation, and review
decision sidecars.

The preview sidecar describes planning records: image, review decision, current
findings, recommended operation, operation rationale, confidence, required
provider type, preview status, and approval state.

The Review Desk can display these planning records beside the original image,
show a placeholder when no preview image exists, and update the record's
approval state in `improvement_preview.json`. Approval changes do not execute
improvements.

v1.7 adds provider-neutral preview contracts and deterministic capability
matching. Static descriptors record supported operations, capability claims,
local/remote and reproducibility metadata, and implementation status. The
Review Desk derives compatibility from those descriptors and the existing
planning record; `improvement_preview.json` remains on its v1 schema.

Provider execution remains unavailable. Dataset Forge does not implement
ComfyUI, Krea, local OpenCV/classical preview generation, manual import,
credentials, API calls, networking, subprocess execution, image processing,
prompt generation, preview image generation, dataset modification, or
improvement execution.

---

## Validation Status

Automated tests cover the inspect pipeline, analyzer contracts, reports,
Review Desk payloads and server behavior, review decisions, comparison,
planning, preview, manifests, policy semantics, and public CLI surface.

Committed synthetic fixtures validate the shape of current analyzer signals.
Private/real-world validation has informed early thresholds and wording, but
the current analyzers are still advisory. Public real-world calibration
evidence is not yet sufficient to claim calibrated precision/recall for all
dataset styles.

Users should interpret findings as evidence-backed review prompts.

### Analyzer Validation Journal Template

When validating findings on real datasets, keep notes in a simple reviewer
journal. This is optional documentation, not a Dataset Forge sidecar.

| filename | analyzer | category | human judgment | likely cause | reviewer note |
|---|---|---|---|---|---|
| `example.jpg` | `texture_analyzer/v1` | `texture.high_microtexture` | Correct useful signal / Accepted style / Source artifact / Ambiguous | watercolor texture / JPEG compression / natural grain / intentional highlights | Short note explaining the decision. |

---

## Running Tests

```text
uv run pytest tests/
```

Release hardening should also run:

```text
python -m pytest tests/test_cli_surface.py -q
python -m pytest tests/test_review_server.py -q
python -m pytest -q
git diff --check
```

---

## Project Docs

| Document | Contents |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Current read-only architecture and contracts. |
| [CURRENT_STATUS.md](CURRENT_STATUS.md) | Current product/release state. |
| [ROADMAP.md](ROADMAP.md) | v1.x scope and future direction. |
| [CLI_OUTPUT.md](CLI_OUTPUT.md) | Public CLI wording expectations. |
| [CHANGELOG.md](CHANGELOG.md) | Release changes. |
| [WHY.md](WHY.md) | Design rationale. |
| [benchmarks/README.md](benchmarks/README.md) | Benchmark fixture inventory. |

---

## License

MIT. See [LICENSE](LICENSE).
