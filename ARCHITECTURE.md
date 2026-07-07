# Dataset Forge -- Architecture

> The architecture should anticipate growth.
> The implementation should not.

---

## v0.18.0-alpha Inspect Pipeline

```
Dataset
  └─► DatasetContext          statistical reference frame for the dataset
        └─► Analyzer(s)       independent, calibrated, deterministic
              └─► Finding(s)  universal output contract
                    └─► Report  human-readable, explainable output
```

Every component in the public inspect surface maps to this pipeline. The
current report stage also includes additive post-inspection sections:
Aggregation, Dataset Summary, Review Queue, Recommendation Summary sidecars,
an optional static review gallery, optional recommendation contact sheets, and
optional persistent human review-decision sidecars.
v0.14 also includes an optional local review decision server over those
sidecars. v0.15 adds deterministic comparison between two existing inspect
output folders. v0.17 adds explicit Improvement Planning from existing
sidecars. v0.18 adds execution-free Improvement Preview from an existing
Improvement Plan. Cleanup execution, repair, regeneration, export, hosted UI,
and plugins are future work and are not part of v0.18.0-alpha.

The product direction after v0.6 is a LoRA Dataset Decision Engine: evidence
should help users decide which images have no current review findings, which
need review, and which deserve priority attention before training. Internal
systems exist to improve decision quality, confidence communication,
false-positive reduction, and review efficiency.

The long-term architectural direction is deterministic, evidence-backed dataset
improvement. Dataset Forge may later support cleanup planning and optional
cleanup execution, but only downstream of the decision pipeline:

```text
Inspect
-> Recommend
-> Explain
-> Human Review
-> Persistent Decisions
-> Dataset Comparison
-> Improvement Planning
-> Improvement Preview
-> Optional Cleanup Execution
```

The architecture must never support:

```text
Inspect
-> Automatically Clean
```

This is a future boundary, not current product scope. v0.18 remains a LoRA
Dataset Decision Engine.

v0.19 should not implement deterministic execution. Its architectural purpose
is Real-World Triage Evidence: image-level triage dossiers, image-centered
recommendations with findings nested underneath, analyzer coverage summaries,
clear no-finding semantics, and better wording around crystalline faceting,
high microtexture, Priority Review, and accepted/acceptable style. The full
workflow should be validated against the anthropomorphic LoRA dataset while
remaining read-only, advisory, deterministic, and sidecar-based.

For v0.19, execution, cleanup, export, repair, source-image modification, and
pixel modification remain explicitly out of scope.

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

v0.19.0-alpha outputs:
- `inspection_report.json`  --  machine-readable, complete findings
- `inspection_report.txt`  --  human-readable summary
- `recommendation_summary.json`  --  machine-readable advisory review priorities
- `recommendation_summary.md`  --  plain-language advisory review priorities
- `triage_dossiers.json`  --  machine-readable image-level triage evidence
- `triage_dossiers.md`  --  human-readable image-level triage dossiers
- `review_decisions_template.json`  --  starter human review sidecar, written only when absent
- `review_gallery.html`  --  optional static visual review surface
- `priority_review_contact_sheet.png`  --  optional Priority Review contact sheet
- `needs_review_contact_sheet.png`  --  optional Needs Review contact sheet
- `inspection_gallery.png`  --  optional visual review contact sheet
- `comparison_summary.json`  --  optional sidecar-only comparison between inspect outputs
- `comparison_summary.md`  --  optional human-readable comparison summary
- `improvement_plan.json`  --  optional advisory Improvement Plan over existing sidecars
- `improvement_plan.md`  --  optional human-readable Improvement Plan
- `improvement_preview.json`  --  optional execution-free Improvement Preview
- `improvement_preview.md`  --  optional human-readable Improvement Preview

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

Future decision guidance should be layered over this evidence. It may label
images as Ready to train, Needs review, or Priority review /
Exclude-from-training candidate, but it must cite the underlying Findings and
must treat exclusion as training-set advice, not file deletion.

---

## Benchmarks

Location: `benchmarks/`

```
benchmarks/
    benchmark_manifest.json
    synthetic_defects/         committed synthetic PNG fixtures
    real_world/                validation corpus framework and labels
    real_samples/              local/private calibration images, gitignored
    results/                   benchmark run outputs, gitignored
```

Every analyzer ships with a benchmark that validates its thresholds.

---

## Calibration Evidence

Calibration Evidence is the v0.3 bridge between inspect-only findings and
trustworthy decision guidance. It measures existing analyzer output against
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

Review Decisions are the human-intent layer for preserving review knowledge
across inspect runs and improving future recommendation quality. They record
human intent over existing inspected images and finding categories. They do not
run analyzers, change thresholds, modify images, or plan cleanup/export work.

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
    },
    {
      "image_path": "image_003.png",
      "recommendation": "Needs Review",
      "decision": null,
      "notes": ""
    }
  ]
}
```

Supported decision values are `CONFIRMED_ARTIFACT`, `FALSE_POSITIVE`,
`ACCEPTABLE_STYLE`, `NEEDS_REVIEW`, `IGNORE`, and `LOCKED`. Template entries
may use `decision: null` to mean no human decision has been recorded yet.

The review-decision layer provides deterministic summaries and helper queries
for future planning code, such as whether an image is locked, whether a finding
was confirmed, whether a finding was rejected as a false positive, and whether
an image/category should be excluded from future action. It is internal and
additive; it does not alter `inspection_report.json`.

In v0.13, `dataset-forge inspect` writes `review_decisions_template.json` only
when the template does not already exist. If `review_decisions.json` exists in
the output folder, inspect loads it and annotates `recommendation_summary.md`
and optional `review_gallery.html` with Already Reviewed / Pending Review
status. Existing review decision files and templates are never overwritten.

In v0.14, `dataset-forge review <inspect_output>` starts an optional local-only
review server. The server binds only to `127.0.0.1`, reads existing
`inspection_report.json`, `recommendation_summary.json`, and optional
`review_decisions.json`, and writes only `review_decisions.json` using atomic
replace. It does not modify source images, inspection reports, recommendation
summaries, contact sheets, static gallery output, analyzers, or recommendation
rules. The browser surface is not canonical; sidecar JSON remains the source of
truth.

---

## Dataset Comparison

Dataset Comparison is the v0.15 sidecar comparison layer. It compares two
existing inspect output folders and answers: "What deserves attention because
something changed?"

Public command:

```text
dataset-forge compare <before_inspect_output> <after_inspect_output> --output <comparison_output>
```

Required inputs:
- `inspection_report.json` with schema `dataset-forge/inspection/v1`
- `recommendation_summary.json` with schema `dataset-forge/recommendation-summary/v1`

Optional input:
- `review_decisions.json` with schema `dataset-forge/review-decisions/v1`

Outputs:
- `comparison_summary.json` with schema `dataset-forge/comparison-summary/v1`
- `comparison_summary.md`

The comparison layer reports recommendation count changes, finding category
changes, analyzer output count changes, images whose recommendation changed,
findings present after but not before, findings present before but not after,
and review-decision availability/counts only.

Finding identity is deterministic and uses normalized image path, category,
analyzer, and severity. Path normalization changes path separators only. There
is no fuzzy matching and duplicate findings are treated as multisets.

Dataset Comparison must not inspect images, compare pixels, rerun analyzers,
modify source images, modify existing reports, modify recommendations, modify
review decisions, classify changes as better/worse, produce scores, generate
charts, or create browser UI.

---

## Improvement Planning

Improvement Planning is the v0.17 sidecar planning layer. It consumes existing
inspection evidence and review intent to answer: "If I chose to improve this
dataset later, what abstract operations would be worth considering, and why?"

Public command:

```text
dataset-forge plan <inspect_output>
```

Required inputs:
- `inspection_report.json` with schema `dataset-forge/inspection/v1`
- `recommendation_summary.json` with schema `dataset-forge/recommendation-summary/v1`

Optional inputs:
- `review_decisions.json` with schema `dataset-forge/review-decisions/v1`
- `comparison_summary.json` with schema `dataset-forge/comparison-summary/v1`

Outputs:
- `improvement_plan.json` with schema `dataset-forge/improvement-plan/v1`
- `improvement_plan.md`

Improvement Planning emits:
- Improvement Candidates
- Deferred Improvement Candidates
- Suppressed Improvement Candidates
- Suggested Improvements summary

Suggested Improvements are abstract planning concepts only, such as
Microtexture Normalization, Oversharpening Mitigation, Speck Reduction, Noise
Consistency Review, Texture Consistency Review, and Edge Consistency Review.
They are not algorithms and are not executed.

Review decisions control planning:
- `CONFIRMED_ARTIFACT` remains eligible for planning.
- `FALSE_POSITIVE`, `ACCEPTABLE_STYLE`, and `IGNORE` suppress planning.
- `LOCKED` prevents an Improvement Candidate.
- `NEEDS_REVIEW` defers planning.

Improvement Planning must not inspect images, rerun analyzers, generate new
evidence, modify source images, modify reports, modify recommendations, modify
review decisions, copy files, move files, rename files, delete files, export
datasets, create browser UI, or execute improvements.

---

## Improvement Preview

Improvement Preview is the v0.18 traceability layer after Improvement Planning
and before any future deterministic execution. It consumes an existing
`improvement_plan.json` and explains what would be considered later, without
performing any operation.

Public command:

```text
dataset-forge preview <improvement_plan.json>
```

Required input:
- `improvement_plan.json` with schema `dataset-forge/improvement-plan/v1`

Optional inputs in the same folder:
- `review_decisions.json` with schema `dataset-forge/review-decisions/v1`
- `comparison_summary.json` with schema `dataset-forge/comparison-summary/v1`

Outputs:
- `improvement_preview.json` with schema `dataset-forge/improvement-preview/v1`
- `improvement_preview.md`

Each preview entry explains:
- the Improvement Candidate
- the Suggested Improvement
- existing evidence and triggering findings
- review decision state
- planning status
- execution availability
- expected outcome

Execution availability is always `Not Implemented` in v0.18. Improvement
Preview must not inspect images, process pixels, rerun analyzers, modify plans,
modify source images, modify reports, modify review decisions, export datasets,
or execute improvements.

---

## Validation Dossiers

Validation Dossiers are the v0.5 reliability gate before stronger public
decision guidance. They combine existing inspection reports, calibration labels,
and optional Review Decisions into a deterministic analyzer-reliability summary.
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
- conservative readiness statuses per category
- explicit `insufficient_evidence` statuses when label counts are too low
- threshold-review candidates

Readiness is conservative. A category is not considered ready for stronger
recommendation language unless it has enough labeled positive/negative
examples, high precision and recall, low false-positive rate, and no
false-positive Review Decisions. Readiness is evidence for future design only;
it is not a repair plan and does not authorize automated changes.

---

## Real-World Validation Corpus

The Real-World Validation Corpus is the v0.6 methodology layer for labeled
real-world validation data. It defines how future public and private datasets
should be organized before Dataset Forge claims analyzer reliability on
real-world LoRA/image corpora.

Location: `benchmarks/real_world/`

Schema: `dataset-forge/real-world-validation-corpus/v1`

The corpus framework supports:
- real image fixture groups
- schema-compatible Calibration Evidence labels
- optional Review Decisions
- expected validation outputs
- public fixture rules for legally safe, reproducible assets
- optional private/local datasets that are skipped when absent

The committed public group is a synthetic placeholder used only to prove corpus
wiring, label compatibility, and Validation Dossier compatibility. It is not
real-world calibration evidence.

The corpus layer does not run analyzers, change thresholds, modify images,
create reports, plan repair, export datasets, or alter `inspection_report.json`.
It is internal and additive.

---

## Recommendation Summary

Recommendation Summary is the v0.9 user-visible decision-summary sidecar layer.

Schema: `dataset-forge/recommendation-summary/v1`

It consumes only:

- existing `Finding` objects
- `DatasetContext.image_paths`
- source report schema metadata

Its core recommendation engine does not inspect images, run analyzers, generate
new evidence, modify Findings, read Review Decisions, read Validation Dossiers,
interpret Calibration Evidence, or alter `inspection_report.json`.

The v0.9 engine is deliberately boring:

- analyzer error -> `PRIORITY_REVIEW`
- HIGH or CRITICAL finding -> `PRIORITY_REVIEW`
- findings from multiple categories -> `PRIORITY_REVIEW`
- any other finding -> `NEEDS_REVIEW`
- no findings -> `READY_FOR_TRAINING` internally, displayed as `No Findings Emitted`

The JSON output includes schema, source report schema, summary counts, analyzer
coverage, one recommendation per image, display labels, primary reasons, reason
codes, finding references, nested finding evidence, guidance, and an advisory
confidence note. Finding references contain analyzer, category, and severity;
nested finding evidence carries measurements and explanations for image-level
triage.

It must not emit numeric quality scores or serialized priority fields. Sorting
is deterministic, but ordering is not a score.

In v0.10, `dataset-forge inspect` writes `recommendation_summary.json` and
`recommendation_summary.md` alongside inspection reports and prints aggregate
recommendation counts. There is no public `dataset-forge recommend` command, no
embedding into `inspection_report.json`, no cleanup, no repair, no export, and
no validation coupling.

The recommendation JSON and recommendation labels must be reproducible from
`inspection_report.json` alone. `No Findings Emitted` means no current findings
requiring review were emitted; it does not guarantee the image is
artifact-free, caption-ready, or suitable for LoRA training.

v0.19 makes the recommendation surface image-centered. `recommendation_summary.md`
is a human-facing review report: summary counts, analyzer coverage, Priority
Review first, Needs Review second, No Findings Emitted summarized rather than
listed image-by-image, important notes, and next steps.

v0.19 also writes `triage_dossiers.json` and `triage_dossiers.md`. Triage
dossiers are image-level review artifacts with findings nested underneath each
image, review status, suggested human action, analyzer coverage, and explicit
read-only scope. They do not execute cleanup, export datasets, modify source
images, or modify pixels.

v0.20 should consolidate review UX into a local browser-based review desk over
the same sidecars. The review desk should show image cards grouped by Priority
Review, Needs Review, and No Findings Emitted; support filters by status,
analyzer/finding category, severity, and confidence; link back to detailed
triage dossier entries; and persist human decisions to `review_decisions.json`.
It is an interface layer only. It must remain local, deterministic, and
sidecar-based, with no network dependencies, cleanup execution, export,
automatic repair, source-image modification, or pixel modification.

v0.10 adds `dataset-forge inspect --review-gallery`, which writes
`review_gallery.html` from the existing `inspection_report.json` and
`recommendation_summary.json` sidecars. The gallery is plain deterministic HTML
with embedded CSS and no front-end framework, server, buttons, checkboxes, or
review state. It is a review surface only; the JSON sidecars remain the source
of truth.

v0.11 adds `dataset-forge inspect --contact-sheets`, which writes
`priority_review_contact_sheet.png` and `needs_review_contact_sheet.png` from
the existing `inspection_report.json` and `recommendation_summary.json`
sidecars. Empty groups produce deterministic empty-state sheets. Ready for
Training images do not get contact sheets by default. The sheets use fixed
thumbnail sizing, Recommendation Summary ordering, and at most the first 100
images per sheet.

v0.12 improves explainability in `recommendation_summary.md` and
`review_gallery.html` only. Each Priority Review and Needs Review item shows
the existing recommendation label, primary reason, finding categories, severity,
analyzer names, and finding count. It does not add new analysis, confidence
tiers, scores, schemas, review state, validation coupling, or recommendation
rules.

v0.13 adds persistent review status presentation only. Recommendations remain
derived from `inspection_report.json`; `recommendation_summary.json` remains
unchanged. Existing review decisions annotate Markdown and optional HTML output,
but they do not affect recommendation rules, finding generation, analyzer
behavior, contact sheets, or inspection report schema.

v0.14 adds interactive review-decision capture only. The local server consumes
the same sidecars and writes the existing Review Decisions schema. It does not
change `recommendation_summary.json`, `inspection_report.json`,
`review_gallery.html`, contact sheets, analyzers, thresholds, or recommendation
rules.

v0.15 adds sidecar-only Dataset Comparison. It consumes two existing inspect
output folders and writes `comparison_summary.json` and `comparison_summary.md`.
It does not rerun analyzers, inspect source images, modify sidecars, compare
pixels, or add scores.

---

## Why Dataset Forge does not repair images yet

Repair is deferred until Dataset Forge can reliably identify images that deserve
intervention. A repair workflow built on weak or uncalibrated findings would
damage trust and risk changing images that should be left alone.

The current architecture therefore optimizes for evidence-backed decisions:
measure, explain, prioritize review, validate against labels, and communicate
confidence honestly. Cleanup, repair, and export remain future-only because the
decision layer must be trustworthy first.

If cleanup planning and cleanup execution are ever implemented, they must sit
after Inspect, Recommend, Explain, Human Review, Persistent Decisions, and
Dataset Comparison. Cleanup must be evidence-backed, explicitly reviewed, and
optional. The direct path from Inspect to Automatically Clean is forbidden.

---

## Future-Only / Not Implemented in v0.18.0-alpha

The following exist in the codebase but are out of scope for the public
v0.18.0-alpha release. They should not be modified, expanded, or
depended on by inspect code.

| Module | Status |
|---|---|
| `cleanup/` | Future only; not public in v0.18.0-alpha |
| `plugins/` | Future only; not public in v0.18.0-alpha |
| `execution/` | Future only; not public in v0.18.0-alpha |
| `transforms/` | Future only; not public in v0.18.0-alpha |
| `exporters/` | Future only; not public in v0.18.0-alpha |
| `review/` | Future only; not public in v0.18.0-alpha |
| `recommendations/engine.py` | Future only; not public in v0.18.0-alpha |

These modules represent future phases. They are preserved, not deleted,
because they may be valuable later. They are not part of the public
v0.18.0-alpha CLI or report behavior.

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
evidence schema, benchmark, and decision guidance.

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
                    └─► recommendation  family-specific guidance
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
- Future decision guidance must use each Finding independently. A
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

### Archived Future Repair Research (not current roadmap)

> This section is an archived design note, not the current roadmap. Dataset
> Forge v0.18.0-alpha does not expose cleanup, repair planning, repair,
> regeneration, or export commands. Repair, cleanup, and export should not be
> reconsidered until decision guidance is reliable on labeled real-world data.

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
with a future `artifact.high_frequency_isolated` improvement candidate would
receive isolated-component cleanup, not microtexture cleanup.

**Possible cleanup routing flow if repair is ever justified:**

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

The preferred long-term path is:

```text
Inspect
-> Recommend
-> Explain
-> Human Review
-> Persistent Decisions
-> Dataset Comparison
-> Cleanup Planning
-> Optional Cleanup Execution
```

The forbidden path is:

```text
Inspect
-> Automatically Clean
```

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

## Archived Batch Exclusion and Export Research (future only)

> This section describes a possible non-destructive export mechanism.
> It is not yet implemented. Nothing in v0.18.0-alpha should be designed around
> it or expose it through the public CLI. Export is not an assumed next step.

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

If this workflow is ever revived, it may support a single explicit flag with a
recommended threshold, producing the exclusion list in one command without
requiring a review pass.
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
> Each artifact family is a first-class citizen with its own detector, evidence, and decision path.
