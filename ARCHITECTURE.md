# Dataset Forge -- Architecture

> The architecture should anticipate growth.
> The implementation should not.

---

## v0.5.0-alpha Inspect Pipeline

```
Dataset
  └─► DatasetContext          statistical reference frame for the dataset
        └─► Analyzer(s)       independent, calibrated, deterministic
              └─► Finding(s)  universal output contract
                    └─► Report  human-readable, explainable output
```

Every component in the public inspect surface maps to this pipeline. The
current report stage also includes additive post-inspection sections:
Aggregation, Dataset Summary, and Review Queue. Cleanup, repair, regeneration,
export, UI, and plugins are future work and are not part of v0.5.0-alpha.

---

## DatasetContext

The statistical understanding of the dataset.

Built once before any analyzer runs. Read-only during analysis.

**v1 contents:**

```python
@dataclass
class DatasetContext:
    schema_version: int
    analyzer_versions: dict[str, str]
    image_paths: list[Path]
    image_count: int
    error_count: int
    resolution_stats: ResolutionStats       # min/max/mean/stddev w/h
    aspect_ratio_stats: AspectRatioStats    # distribution
    texture_distributions: TextureDists     # microtexture mean/stddev/p10/p90
    frequency_distributions: FreqDists      # periodic noise baseline
    duplicate_hashes: set[str]
```

DatasetContext must not be inflated with per-image results, cleanup decisions,
or anything that belongs in Finding.

---

## Finding

The universal output contract. Every analyzer emits Findings.
Everything downstream consumes Findings.

```python
@dataclass
class Finding:
    image_path: Path
    analyzer: str                   # e.g. "crystalline_faceting_analyzer/v1"
    category: str                   # e.g. "artifact.crystalline_faceting"
    severity: Severity              # NONE / LOW / MEDIUM / HIGH / CRITICAL
    confidence: float               # 0.0-1.0
    false_positive_rate: float      # estimated from benchmark
    benchmark_version: str          # benchmark that calibrated this threshold
    evidence: dict[str, Any]        # raw measurements
    explanation: str                # human-readable why
    recommendation: str             # human-readable what to do
```

**Stability rule:** if a new analyzer can be added without changing `Finding`,
the architecture is succeeding. Extensions go in `evidence`, not new top-level fields.

---

## Analyzers

Each analyzer is an independent module:

```
src/dataset_forge/analyzers/
    base.py                    -- abstract Analyzer with analyze() contract
    texture.py                 -- dataset-relative microtexture
    crystalline.py             -- crystalline faceting
    oversharpening.py          -- oversharpening / edge halos
    high_frequency_isolated.py -- sparse isolated high-frequency artifacts
```

**Analyzer contract:**

```python
class Analyzer(ABC):
    @abstractmethod
    def analyze(
        self,
        image_path: Path,
        context: DatasetContext,
        measurements: ImageMeasurements | None = None,
    ) -> list[Finding]: ...
```

`measurements` is optional so analyzers can consume shared per-image measurements
computed by the inspect runner. Today this is used for texture measurements
shared by TextureAnalyzer and CrystallineFacetingAnalyzer. Some first-pass
analyzers still perform their own read-only measurements internally.

Analyzers must:
- operate independently
- consume DatasetContext (read-only)
- emit Findings only
- be benchmarked against synthetic data
- be individually testable

Analyzers must not:
- modify images
- call other analyzers
- make cleanup decisions
- maintain cross-image state outside DatasetContext

---

## Report

The report layer consumes Findings plus additive post-inspection sections and
produces human-readable output.

v0.5.0-alpha outputs:
- `inspection_report.json`  --  machine-readable, complete findings
- `inspection_report.txt`  --  human-readable summary
- `inspection_gallery.png`  --  optional visual review contact sheet

Reports must not re-run analysis, modify images, or make cleanup/repair/export
decisions. They present findings and advisory review organization.

---

## Post-Inspection Layer

The post-inspection layer is additive. It runs after Findings are produced and
before reports are written:

```
Findings -> Aggregation -> Dataset Summary -> Review Queue -> Report
```

Aggregation is internal only. It groups findings by image, counts findings by
category and severity, counts analyzer errors, tracks images with and without
findings, tracks images with multiple finding families, and separates
calibrated from uncalibrated findings.

Dataset Summary answers: "What did we find across the dataset?"
`dataset_summary` is emitted as an additive top-level JSON section with schema
`dataset-forge/dataset-summary/v1`. It does not change or replace existing
report fields.

Review Queue answers: "Which images deserve human attention first?"
`review_queue` is emitted as an additive top-level JSON section with schema
`dataset-forge/review-queue/v1`. Its only outcomes are
`no_attention_needed`, `review_recommended`, and `priority_review`.

Review Queue is advisory only. It never rejects, regenerates, repairs,
exports, deletes, moves, renames, or modifies images. It must never hide the
underlying Findings that caused an image to appear in the queue.

---

## Benchmarks

Location: `benchmarks/`

```
benchmarks/
    benchmark_manifest.json
    synthetic_defects/         committed synthetic PNG fixtures
    real_samples/              local/private calibration images, gitignored
    results/                   benchmark run outputs, gitignored
```

Every analyzer ships with a benchmark that validates its thresholds.

---

## Calibration Evidence

Calibration Evidence is the v0.3 bridge between inspect-only findings and any
future repair/export planning. It measures existing analyzer output against
ground-truth labels. It does not run analyzers, edit thresholds, modify images,
or make human-review decisions.

Inputs:
- `inspection_report.json` with schema `dataset-forge/inspection/v1`
- Ground-truth labels with schema `dataset-forge/calibration-labels/v1`

Ground-truth labels are intentionally small:

```json
{
  "schema": "dataset-forge/calibration-labels/v1",
  "labels": [
    {
      "image_path": "image_001.png",
      "categories": ["artifact.crystalline_faceting"]
    },
    {
      "image_path": "image_002.png",
      "categories": []
    }
  ]
}
```

An empty `categories` list means the image is labeled clean for the current
calibration categories.

Output schema: `dataset-forge/calibration-evidence/v1`

The output includes per-analyzer and per-category TP/FP/FN/TN, precision,
recall, F1, and false-positive rate. Error findings are counted as ignored
error findings; they are not treated as artifact positives.

Calibration Evidence is internal for now. It should inform future threshold
review, but it must not silently change analyzer behavior.

---

## Review Decisions

Review Decisions are the v0.4 bridge between Calibration Evidence and future
human-approved Repair Planning. They record human intent over existing inspected
images and finding categories. They do not run analyzers, change thresholds,
modify images, or plan cleanup/export work.

Input schema: `dataset-forge/review-decisions/v1`

```json
{
  "schema": "dataset-forge/review-decisions/v1",
  "decisions": [
    {
      "image_path": "image_001.png",
      "category": "artifact.crystalline_faceting",
      "decision": "CONFIRMED_ARTIFACT"
    },
    {
      "image_path": "image_002.png",
      "decision": "LOCKED",
      "reason": "Preserve original approved style."
    }
  ]
}
```

Supported decision values are `CONFIRMED_ARTIFACT`, `FALSE_POSITIVE`,
`ACCEPTABLE_STYLE`, `NEEDS_REVIEW`, `IGNORE`, and `LOCKED`.

The review-decision layer provides deterministic summaries and helper queries
for future planning code, such as whether an image is locked, whether a finding
was confirmed, whether a finding was rejected as a false positive, and whether
an image/category should be excluded from future action. It is internal and
additive; it does not alter `inspection_report.json`.

---

## Validation Dossiers

Validation Dossiers are the v0.5 reliability gate before future Repair
Planning. They combine existing inspection reports, calibration labels, and
optional Review Decisions into a deterministic analyzer-reliability summary.
They do not run analyzers, change thresholds, modify images, or plan
cleanup/repair/export work.

Input artifacts:
- `inspection_report.json` with schema `dataset-forge/inspection/v1`
- Ground-truth labels with schema `dataset-forge/calibration-labels/v1`
- Optional Review Decisions with schema `dataset-forge/review-decisions/v1`

Output schema: `dataset-forge/validation-dossier/v1`

The output includes:
- per-analyzer metrics
- per-category metrics
- false-positive and false-negative examples
- confirmed artifact counts
- false-positive review-decision counts
- conservative `ready_for_repair_planning` statuses per category
- explicit `insufficient_evidence` statuses when label counts are too low
- threshold-review candidates

Readiness is conservative. A category is not considered ready for future repair
planning unless it has enough labeled positive/negative examples, high
precision and recall, low false-positive rate, and no false-positive Review
Decisions. Readiness is evidence for future design only; it is not a repair
plan and does not authorize automated changes.

---

## Future-Only / Not Implemented in v0.5.0-alpha

The following exist in the codebase but are out of scope for the public
v0.5.0-alpha inspect release. They should not be modified, expanded, or
depended on by inspect code.

| Module | Status |
|---|---|
| `cleanup/` | Future only; not public in v0.5.0-alpha |
| `plugins/` | Future only; not public in v0.5.0-alpha |
| `execution/` | Future only; not public in v0.5.0-alpha |
| `transforms/` | Future only; not public in v0.5.0-alpha |
| `exporters/` | Future only; not public in v0.5.0-alpha |
| `review/` | Future only; not public in v0.5.0-alpha |
| `recommendations/engine.py` | Future only; not public in v0.5.0-alpha |

These modules represent future phases. They are preserved, not deleted,
because they may be valuable later. They are not part of the public
v0.5.0-alpha CLI or report behavior.

---

## Relationship to Legacy Modules

| Bible concept | Legacy equivalent | Notes |
|---|---|---|
| DatasetContext | implemented in `context.py` | Current inspect statistical reference frame |
| Finding | implemented in `finding.py` | Stable report/output contract |
| Analyzer | implemented in `analyzers/` | Texture legacy measurements are wrapped by v1 analyzers |
| Report | implemented in `report.py` | JSON and TXT inspect report writers |

---

## Artifact Family Architecture

> GPT-style image contamination is not a single phenomenon.
> Each artifact family requires its own detection signal.
> A single generic texture score cannot reliably distinguish between them.

This was established empirically during calibration review of the anthropomorph
dataset. Eleven missed detections were investigated; diagnostic analysis showed
that `highlight_speck` (isolated near-white pixel detection) had Cohen's d = -0.01
against the clean population for crystalline faceting images  --  no discriminating
power at all. Different artifact families require different metrics.

---

### Artifact Families

Each family is a distinct contamination phenomenon requiring its own analyzer,
evidence schema, benchmark, and (eventually) cleanup strategy.

| Family | Description | Primary Signal | Status |
|---|---|---|---|
| **Texture / Microtexture** | Elevated high-frequency noise across image surfaces; GPT rendering fingerprint | `microtexture_density`, z-score vs dataset | First-pass implemented (`analyzers/texture.py`); uncalibrated |
| **High-Frequency Isolated Artifacts** | Sparse isolated bright/dark high-frequency specks | local residual connected components | First-pass implemented (`analyzers/high_frequency_isolated.py`); uncalibrated |
| **Crystalline Faceting** | Angular micro-polygon shading; surfaces appear carved from facets; distributed mid-frequency texture | `pencil_grain`, `watercolor_smoothness`, `microtexture_density` | First-pass implemented (`analyzers/crystalline.py`); uncalibrated |
| **Recursive Detail Overload** | Compulsive synthetic detail in every region; no restful areas; entire surface treated as foreground | Frequency distribution, detail density | Not yet implemented |
| **Oversharpening / Halos** | Edge ringing, halo artifacts around transitions, over-accentuated outlines | edge-localized USM residuals | First-pass implemented (`analyzers/oversharpening.py`); uncalibrated |

---

### Detection Architecture

Each artifact family maps to an independent detection path:

```
Artifact Family
  └─► Analyzer          one per family; consumes DatasetContext
        └─► Evidence    raw measurements from evaluate_texture or other signals
              └─► Finding
                    ├─► category      e.g. "artifact.crystalline_faceting"
                    ├─► confidence    calibrated against benchmark
                    ├─► false_positive_rate  from labeled review data
                    └─► recommendation  family-specific action
```

**Current finding categories:**

- `texture.high_microtexture` for the texture artifact family (`artifact.texture`
  in planning language; runtime name preserved for compatibility)
- `artifact.crystalline_faceting`
- `artifact.oversharpening_halo`
- `artifact.high_frequency_isolated`
- `artifact.recursive_detail` (future)

Analyzers for different families may run in the same pipeline pass and emit
Findings independently. No analyzer should attempt to detect more than one
family. If signals overlap, that is the Findings consumer's problem, not the
analyzer's.

---

### Severity Philosophy

Every artifact family supports the same four active severity levels. Thresholds
for each level are set per family, calibrated against labeled review data and
synthetic benchmarks. They are never shared between families.

| Severity | Meaning | Action implied |
|---|---|---|
| `LOW` | Weak signal; likely within normal variation | Note only; human review if useful |
| `MEDIUM` | Measurable artifact; above dataset baseline | Candidate for human review |
| `HIGH` | Strong artifact; clear outlier in dataset context | Prioritize for review |
| `CRITICAL` | Severe contamination; dominant visual artifact | Review before including in dataset |

`NONE` is not emitted as a finding. An image with no issues produces no Findings.

**Severity is per-family, not per-image.** An image can simultaneously hold a
`HIGH artifact.crystalline_faceting` finding and a
`LOW artifact.high_frequency_isolated` finding.
Neither severity rolls up to a combined image score. The report presents each
Finding independently; the human reviewer decides what action to take for each.

Confidence is distinct from severity. Severity describes how bad the artifact is;
confidence describes how certain the analyzer is. An uncalibrated analyzer should
cap confidence conservatively (<= 0.70) regardless of the severity it emits.

---

### Multi-Finding Model

A single image may carry zero, one, or many Findings from different analyzers:

```
image: onionwizard.jpg
  Finding 1:  MEDIUM  texture.high_microtexture    confidence=0.65  (uncalibrated)
  Finding 2:  HIGH    artifact.crystalline_faceting confidence=0.45  (uncalibrated)
  Finding 3:  LOW     artifact.high_frequency_isolated confidence=0.30  (uncalibrated)
```

Rules that must hold:

- Each Finding is emitted by exactly one analyzer.
- No analyzer emits more than one Finding per image per category.
- Findings are independent. One Finding does not suppress or modify another.
- The report layer presents all Findings for an image without merging them.
- Future cleanup routing must use each Finding independently. A
  `HIGH artifact.crystalline_faceting` finding and a co-occurring
  `MEDIUM texture.high_microtexture` finding would remain separate artifact
  families, not a merged generic texture decision.

The report JSON preserves all Findings in a flat list. Consumers that need
per-image grouping build the index themselves (`findings_index` in the review
tooling is an example).

**Primary finding convention:** When a report is displayed to a human and only
one finding can be shown per image in summary view, the first finding in the list
is treated as primary. Within the v1 pipeline, `TextureAnalyzer` runs before
`CrystallineFacetingAnalyzer`, so microtexture findings appear first. This order
should be preserved as new analyzers are added.

---

### Evidence Model

Every Finding carries an `evidence` dict. Its contents are family-specific but
must always include the following keys:

| Key | Type | Meaning |
|---|---|---|
| `calibrated` | `bool` | Whether thresholds have been validated against a benchmark |

Family-specific evidence examples:

```python
# texture.high_microtexture
evidence = {
    "microtexture_density": 58.2,
    "dataset_mean": 38.6,
    "dataset_stddev": 11.6,
    "z_score": 1.69,
    "dataset_p10": 21.0,
    "dataset_p90": 56.0,
    "watercolor_smoothness": 44.1,
    "highlight_speck": 3.2,
    "calibrated": False,
}

# artifact.crystalline_faceting
evidence = {
    "pencil_grain_score": 60.1,
    "watercolor_smoothness_score": 47.3,
    "microtexture_density_score": 47.6,
    "grain_threshold": 45.0,
    "smoothness_ceiling": 52.0,
    "micro_floor": 20.0,
    "calibrated": False,
}
```

Evidence values must be the raw measurements, not the derived decision. The
decision (emit / suppress) lives in the analyzer logic. The evidence records
what was measured so the decision can be audited or replayed.

When an analyzer is uncalibrated:
- `calibrated: False` must be in evidence
- `confidence` must be capped conservatively (<= 0.70 in practice, lower for
  first-pass detectors)
- `false_positive_rate` must be set to the observed rate from labeled review
  data, or a conservative estimate if no labeled data exists yet

---

### Cleanup Routing (future only -- not implemented in v0.5.0-alpha)

> This section is design guidance for a future release. Dataset Forge
> v0.5.0-alpha does not expose cleanup, repair planning, repair, regeneration, or export
> commands.

Cleanup must be artifact-specific. A single generic smoothing filter applied
to all findings would:

- destroy legitimate pencil grain while removing GPT microtexture
- blur intentional watercolor edges while removing halos
- damage genuine specular highlights while removing speck artifacts

Each artifact family requires a cleanup strategy tuned to that family's
characteristics. The correspondence is:

| Artifact Family | Candidate Cleanup Strategy |
|---|---|
| Texture / Microtexture | Edge-preserving denoise (detail-aware, not Gaussian) |
| High-Frequency Isolated Artifacts | Isolated bright/dark component suppression with local inpainting |
| Crystalline Faceting | Mid-frequency band suppression; texture field smoothing |
| Recursive Detail Overload | Frequency-domain attenuation; semantic detail reduction (AI phase) |
| Oversharpening / Halos | Unsharp-mask reversal; edge deconvolution |

Cleanup families inherit their scope from the corresponding Finding. An image
with a future `artifact.high_frequency_isolated` cleanup candidate would receive
isolated-component cleanup, not microtexture cleanup.

**Cleanup routing flow (v2 target):**

```
Finding (per family, per image)
  └─► Severity gate       LOW findings are skipped; MEDIUM+ are candidates
        └─► Cleanup pass  family-specific deterministic operation
              └─► Comparison gallery  original | cleaned side-by-side contact sheet
                    └─► Human approval  per-image ACCEPT / REJECT
                          └─► Final export  only ACCEPT images written to output folder
```

Severity gates are advisory, not mandatory. The reviewer may override a LOW
finding for manual cleanup, or skip a HIGH finding on artistic grounds. The gate
just determines the default path.

Cleanup is never automatic. Every finding-triggered cleanup must pass through
the human approval step before it affects any exported file.

---

### Non-Destructive Requirement

This is absolute and applies to all future cleanup work:

1. **Originals are never modified.** Source images are read-only at all times.
2. **Cleanup candidates are written to a separate output folder.** Never adjacent
   to originals.
3. **Human review is required before export.** Side-by-side comparison (original
   vs. cleaned) must be presented to the reviewer. No batch approval.
4. **Final export is assembled from individually approved results.** The export
   folder contains only images the reviewer explicitly accepted.

These rules exist because the dataset is the ground truth for LoRA training.
Silent or automatic modification would corrupt it with no recovery path.

---

## Batch Exclusion and Export Workflow (future  --  v2+)

> This section describes the planned non-destructive export mechanism.
> It is not yet implemented. Nothing in v0.5.0-alpha should be designed around
> it or expose it through the public CLI.

---

### Purpose

After a full inspect run and human review, the user may want to produce a
curated final dataset. Two complementary outputs serve this purpose:

1. **Exclusion list**  --  a text file naming images that should be excluded from
   training. The source images are never touched.
2. **Final dataset copy**  --  an optional folder of included images assembled
   by copying (never moving) from the source dataset.

Both outputs are derived from Findings and reviewer decisions. Neither modifies,
moves, or deletes any source image.

---

### Guiding Constraints

These are absolute. They extend the Non-Destructive Requirement to the
export layer.

1. **Source images are read-only throughout.** No rename, no move, no
   modification of any file in the original dataset folder.
2. **Exclusion lists record intent, not action.** An exclusion list says which
   images to leave out; downstream tooling (trainer, data loader) acts on it.
   Dataset Forge never enforces it by deleting files.
3. **Final dataset is assembled by copy.** `final_dataset/` contains
   hard-copies of approved images. It is a derived artifact, not a view or
   a symlink tree.
4. **Human review is the gate before export.** The workflow surfaces a review
   step. Batch auto-approval must not be offered as a default path.
5. **Export is repeatable.** Given the same inspection report and review file,
   re-running the export produces the same final dataset. It is deterministic
   and idempotent.

---

### Filtering Contract

The export workflow must support all of the following filter dimensions,
composable with AND logic by default:

| Dimension | Filter examples | Notes |
|---|---|---|
| Severity | `>= MEDIUM`, `== HIGH`, `!= LOW` | Compared against the highest severity across all findings for the image |
| Category | `artifact.crystalline_faceting`, `artifact.high_frequency_isolated`, `texture.*` | Glob-style or exact match; multiple categories are OR'd within this dimension |
| Confidence | `>= 0.50` | Compared against the highest confidence finding matching the category filter |
| Finding count | `>= 2`, `== 0` | Number of distinct findings on an image (0 = clean images only) |
| Analyzer | `texture_analyzer/v1` | Filter by which analyzer emitted the finding |
| Review decision | `AGREE`, `DISAGREE`, `UNSURE` | From `decision_review.json` if available |

**Excluded images** are those matching the filter criteria  --  i.e., images the
filter says are problematic. **Included images** are the complement.

Both sides of the split must be inspectable before the export is committed.

---

### File Contracts

#### Exclusion list  --  `exclusion_list.txt`

Plain text, one absolute or relative path per line. UTF-8.

```
# Dataset Forge exclusion list
# Generated: 2026-06-18T14:22:00Z
# Source: C:/Users/someo/Desktop/ANTHROPOMORPHS
# Filter: severity>=MEDIUM OR finding_count>=2
# Total excluded: 34 / 100

C:/Users/someo/Desktop/ANTHROPOMORPHS/yagahut.jpg
C:/Users/someo/Desktop/ANTHROPOMORPHS/olivespartans.jpg
...
```

The header block is always emitted. Lines beginning with `#` are comments and
are ignored by any consumer that processes the list programmatically.

Alternative format: `exclusion_list.json` for machine consumers, containing
the filter parameters, timestamp, source path, and a structured list of
excluded files with the findings that caused their exclusion.

#### Final dataset  --  `final_dataset/`

A flat folder (or optionally mirroring the source subdirectory structure) of
copied images. The copy operation preserves the original filename. If two
source paths produce the same filename (recursive scan across subdirectories),
the conflict must be surfaced to the user before any copy proceeds.

```
final_dataset/
  lemonknight.jpg          # copy of source
  private_sample_01.jpg
  candycornjason.jpg
  ...
  export_manifest.json     # records what was copied and why
```

`export_manifest.json` records:
- Source dataset path
- Filter parameters used
- Total images in source
- Total images included (copied)
- Total images excluded
- Per-image decision (included / excluded) with the findings and filter match
  that drove each exclusion
- Timestamp and Dataset Forge version

The manifest is the audit trail. It makes every export reproducible and
explainable.

---

### Workflow Steps

```
1. Run inspect
      dataset-forge inspect <path>
      -> inspection_report.json

2. (Optional) Human review
      scripts/review_decisions.py
      -> decision_review.json

3. Configure export filter
      Severity gate, category filter, confidence threshold, etc.
      Preview: show counts of included / excluded before committing.

4. Review exclusion preview
      Contact sheet of excluded images (thumbnails + finding summary)
      Contact sheet of included images
      Human confirms or adjusts filter.

5. Write exclusion list
      exclusion_list.txt  (always written)
      exclusion_list.json (optional)

6. (Optional) Copy included images
      final_dataset/  populated by copy
      export_manifest.json  written alongside

7. Final check
      Verify final_dataset/ count matches expected.
      Verify no source files were modified (hash check optional).
```

Steps 1--4 are the recommended path. Steps 5--6 are the commit step. The
workflow must never allow skipping step 4 silently  --  the preview is the gate.

---

### Severity-Only Fast Path

The most common use case is a simple severity gate with no category filter:

> "Exclude all images with any finding at MEDIUM or above."

This must work with a single flag, defaulting to a recommended threshold, and
producing the exclusion list in one command without requiring a review pass.
The review pass is still recommended but not mandatory for this path.

The fast path must display a summary (N images excluded, N included, severity
distribution of excluded set) before writing any file.

---

### Integration with Review Tooling

If `decision_review.json` exists for the dataset, the export workflow can
use reviewer decisions as an additional filter dimension:

- Exclude images where the reviewer **AGREED** with a finding (confirmed
  artifacts).
- Exclude images where the reviewer **DISAGREED** with a clean decision
  (missed detections surfaced by reviewer).
- Hold images where the reviewer marked **UNSURE** for a second pass rather
  than silently including or excluding them.

If no review file exists, the export workflow falls back to findings-only
filtering with a warning that unreviewed findings may have a higher false-
positive rate than the calibrated estimate.

---

### What the Export Workflow Must Not Do

- Auto-approve any exclusion without surfacing a preview.
- Delete, rename, or move any file in the source dataset.
- Create symlinks in place of copies (symlinks break when the source moves).
- Silently skip images with I/O errors  --  they must be listed in the manifest
  under an `errors` key.
- Apply cleanup to images before export. Export is post-inspection,
  post-review. Cleanup is a separate pipeline (cleanup routing, v2+).
  An export of uncleaned originals is a valid and common workflow.

---

## Guiding Rule

> Core should orchestrate. Analyzers should specialize. Finding is the contract.
> Each artifact family is a first-class citizen with its own detector, evidence, and cleanup path.
