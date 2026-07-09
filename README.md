# Dataset Forge

Dataset Forge is a read-only LoRA/image dataset curation workstation.

It helps you inspect image datasets, review deterministic evidence, record
human decisions, compare inspection runs, and prepare advisory improvement
plans before training. Source images are never modified.

The primary workflow is:

```text
inspect
-> review in the local Review Desk
-> record human decisions
-> compare runs
-> plan / preview
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
evidence, triage groups, Dataset Intelligence, and decision controls. Decisions
save locally to:

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
| `dataset-forge preview <improvement_plan.json>` | Write an execution-free preview of a plan. |

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
| `improvement_preview.json` / `.md` | Optional execution-free preview. |

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

Dataset Forge does not currently include a JPEG/compression analyzer. Existing
analyzers may flag symptoms that compression contributes to, so human review
remains required.

---

## Safety Guarantees

- Source images are never modified, moved, renamed, deleted, exported, or
  quarantined.
- `inspect` writes reports and sidecars only.
- `review` serves a local browser workflow and writes only
  `review_decisions.json`.
- `compare` reads existing sidecars and writes comparison summaries only.
- `plan` writes advisory Improvement Plan files only.
- `preview` writes execution-free preview files only.
- Dataset Forge does not execute cleanup, repair images, export datasets, train
  models, contact cloud services, or use a database.

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
| [ROADMAP.md](ROADMAP.md) | v1.0 scope and post-v1 direction. |
| [CLI_OUTPUT.md](CLI_OUTPUT.md) | Public CLI wording expectations. |
| [CHANGELOG.md](CHANGELOG.md) | Release changes. |
| [WHY.md](WHY.md) | Design rationale. |
| [benchmarks/README.md](benchmarks/README.md) | Benchmark fixture inventory. |

---

## License

MIT. See [LICENSE](LICENSE).
