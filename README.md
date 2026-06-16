# Dataset Forge

**Build better datasets.**

Dataset Forge is a modular, deterministic dataset engineering platform for
preparing, analyzing, cleaning, validating, benchmarking, and exporting
datasets for generative AI.

LoRA dataset preparation is the first primary use case. Dataset Forge also
supports broader generative AI and ML dataset workflows. LoRA support is a
workflow, not the whole identity of the project.

Dataset Forge does not overwrite, move, or delete source images. Derived
outputs are written separately and guarded by review and approval controls.
Analysis scores are practical heuristics for review and comparison, not
definitive judgments about image quality or provenance.

The project is organized as a modular dataset optimization framework. Analysis,
review, recommendations, presets, future transforms, and future exporters have
separate extension points. Transform and exporter interfaces are foundation
only: the current CLI never executes them.

## Requirements

- Python 3.11 or newer

## Setup

```powershell
cd dataset-forge
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install -e .
```

## Usage

Run the default Forge Pipeline:

```powershell
dataset-forge run --pipeline default --profile balanced --input C:\images --output C:\dataset-report
```

Preview every stage, estimate resources, and write nothing:

```powershell
dataset-forge run --pipeline default --input C:\images --output C:\dataset-report --dry-run
```

Simulate pipeline and resource decisions without writing files:

```powershell
dataset-forge simulate --pipeline default --profile balanced --input C:\images --output C:\dataset-report
```

Resume an interrupted or partially completed pipeline:

```powershell
dataset-forge resume --output C:\dataset-report
```

Force one otherwise reusable stage to run again:

```powershell
dataset-forge run --pipeline default --input C:\images --output C:\dataset-report --force-stage analysis
```

When `--input` is omitted, the pipeline scans the current directory. When
`--output` is omitted, it writes generated artifacts under `output/`.

Create a basic read-only manifest:

```powershell
dataset-forge --input C:\images --output C:\dataset-report
```

Run the Dataset Analysis Engine:

```powershell
dataset-forge --input C:\images --output C:\dataset-report --analyze
```

Generate a dataset health assessment and image-level recommendations:

```powershell
dataset-forge --input C:\images --output C:\dataset-report --health-report
```

`--health-report` automatically runs the analysis required for quality scoring.

Generate an offline visual review gallery:

```powershell
dataset-forge --input C:\images --output C:\dataset-report --review-gallery
```

`--review-gallery` automatically runs analysis and health assessment. By
default it creates compact 256-pixel thumbnails. Change the maximum dimensions:

```powershell
dataset-forge --input C:\images --output C:\dataset-report --review-gallery --thumbnail-size 384
```

Reference the original image locations instead of creating thumbnails:

```powershell
dataset-forge --input C:\images --output C:\dataset-report --review-gallery --no-thumbnails
```

This only creates links to source files. It does not copy them into the output.

Analyze subfolders:

```powershell
dataset-forge --input C:\images --output C:\dataset-report --recursive true --analyze
```

Preview output paths without writing files:

```powershell
dataset-forge --input C:\images --output C:\dataset-report --analyze --dry-run
```

Limit analysis to a deterministic subset:

```powershell
dataset-forge --input C:\images --output C:\dataset-report --analyze --limit 500
```

Generate a read-only texture normalization evaluation:

```powershell
dataset-forge texture-report --input C:\images --output C:\texture-report
```

Add `--recursive true`, `--limit 500`, `--thumbnail-size 384`, or
`--no-thumbnails` as needed. The command measures microtexture density, local
contrast, edge sharpness, highlight specks, texture consistency, watercolor
smoothness, and pencil grain. It writes `texture_report.json`,
`texture_report.csv`, and a sortable offline `texture_report.html`.

Recommendations are `KEEP`, `TEXTURE_NORMALIZE_LIGHT`,
`TEXTURE_NORMALIZE_MEDIUM`, or `MANUAL_REVIEW`. They are analysis guidance
only: this command does not run cleanup filters, call AI services, or modify
source images.

List the included future-processing presets:

```powershell
dataset-forge --list-presets
```

Record a preset alongside the analysis:

```powershell
dataset-forge --input C:\images --output C:\dataset-report --analyze --preset general_artifact_cleanup
```

The module can also be run directly:

```powershell
python -m dataset_forge --input C:\images --output C:\dataset-report --analyze
```

## Dataset Health Report

The Dataset Health Report is the primary dashboard for LoRA dataset readiness.
It answers: **"If I trained a LoRA on this dataset today, how confident should
I feel that the dataset itself is well prepared?"**

Run it after texture analysis:

```powershell
dataset-forge health-report --input C:\images --output C:\dataset-report
```

The command runs texture analysis internally, then generates three files:

- `dataset_health_report.json` — machine-readable, full detail
- `dataset_health_report.html` — offline dashboard (open in any browser)
- `dataset_health_report.txt` — terminal-friendly plain-text summary

Output includes:

- **Dataset Health Score (0–100)** — texture-aware measure of dataset completeness and consistency
- **Estimated LoRA Readiness (0–100)** — heuristic preparation readiness with penalty breakdown *(estimate only; does not predict model performance)*
- **Decision Engine summary** — LEAVE_ALONE / DETERMINISTIC_ONLY / AI_CONSERVATION_CANDIDATE / MANUAL_REVIEW counts with an intervention ratio bar
- **Consistency scores** — texture, style, and cleanup consistency
- **Actionable recommendations** — prioritized, positive-first; explicitly acknowledges when restraint is the best decision
- **Export guidance** — projected training set composition

Optional flags:

```powershell
dataset-forge health-report --input C:\images --output C:\dataset-report --duplicate-count 2 --near-duplicate-count 4
```

The report never modifies source images and does not replace existing reports.

## Analysis

For each supported image, `--analyze` records:

- dimensions, aspect ratio, megapixels, file size, and color mode
- average brightness, saturation, and contrast
- SHA-256 file hash for exact duplicate detection
- perceptual difference hash for probable duplicate detection
- texture score from Laplacian variance, edge density, and local variance
- artifact score from high-frequency detail, isolated highlights, excessive
  edge density, and local contrast noise

Texture and artifact scores range from 0 through 100. They are intended to help
prioritize manual review. Content, style, compression, and scanning methods can
all affect these scores.

## Quality Assessment

`--health-report` adds per-image quality scores to `manifest.csv`:

- overall quality
- duplicate risk
- resolution
- brightness consistency
- contrast
- the existing artifact and texture scores

It then generates recommendations such as keep as-is, review, cleanup,
duplicate review/removal, or regeneration/exclusion. Recommendations are
advisory only. Dataset Forge does not execute them or alter image files.

The dataset health score considers exact and probable duplicates, artifact and
texture burden, and consistency of resolution, brightness, contrast, and aspect
ratio.

Scoring weights can be customized with a JSON file:

```powershell
dataset-forge --input C:\images --output C:\dataset-report --health-report --quality-config C:\configs\quality_weights.json
```

The bundled default is
`src/dataset_forge/config/quality_weights.json`. A custom file must contain all
keys in both `image_weights` and `dataset_weights`. Weights must be
non-negative, and each section must have a positive total.

## Outputs

An analysis run writes only generated metadata under the selected output folder:

```text
output/
|-- manifest.csv
|-- dataset_report.json
|-- evidence.json          # with analysis
|-- dataset_health.json    # with --health-report
|-- recommendations.csv   # with --health-report
|-- review_gallery/       # with --review-gallery
|   |-- index.html
|   `-- thumbnails/       # omitted with --no-thumbnails
`-- logs/
    `-- run-YYYYMMDD-HHMMSS-ffffff.log
```

A standalone `texture-report` run writes:

```text
output/
|-- texture_report.json
|-- texture_report.csv
|-- texture_report.html
|-- evidence.json
`-- texture_thumbnails/   # omitted with --no-thumbnails
```

The Forge Pipeline uses immutable, versioned manifests and adds execution
metadata:

```text
output/
|-- source_index.json
|-- manifest_v1.csv
|-- manifest_v2.csv
|-- manifest_v3.csv
|-- manifest_latest.json
|-- dataset_report.json
|-- evidence.json
|-- dataset_health.json
|-- recommendations.csv
|-- review_gallery/
|   `-- index.html
|-- pipeline_state.json
`-- pipeline_report.json
```

`manifest_latest.json` points to the newest manifest version. Existing
manifest versions are not overwritten by later stages.

`manifest.csv` contains per-image metrics and links each detected duplicate to
the first matching image. Exact duplicates use identical file hashes. Probable
duplicates use perceptual hashes within a small Hamming distance.

`dataset_report.json` includes:

- total image count
- exact and probable duplicate counts
- average width, height, and megapixels
- average texture and artifact scores
- images with the highest artifact scores
- recommendations for artifact burden, duplicates, aspect-ratio variation,
  low resolution, and brightness variation

`dataset_health.json` includes the dataset health score, issue counts, average
artifact and texture scores, top problem images, component scores, and summary
recommendations.

`recommendations.csv` contains:

```text
filename,severity,issue,recommended_action,reason,suggested_preset,suggested_strength
```

Suggested presets and strengths are future-processing guidance only.

## Review Gallery

The self-contained review gallery is written to:

```text
output/review_gallery/index.html
```

Open `index.html` in a browser to inspect thumbnails alongside quality,
artifact, texture, duplicate-risk, severity, action, reason, preset, and
strength information.

The gallery works offline with embedded CSS and JavaScript. It supports:

- sorting by artifact score, quality score, or severity
- severity filters for CRITICAL, WARNING, and INFO
- filters for cleanup recommendations and duplicates
- dataset health and issue counts at the top

With thumbnails enabled, only bounded JPEG previews are written under
`output/review_gallery/thumbnails/`. Full-size images are never copied.

Supported extensions are `.jpg`, `.jpeg`, `.png`, and `.webp`. Invalid or
unreadable images remain in the manifest with an `error` status.

## Preset Format

Presets currently record future processing intent only. They do not alter images.

```json
{
  "name": "watercolor_pencil_cleanup",
  "description": "Preserve washes and linework during future cleanup.",
  "transforms": [
    {
      "name": "reduce_microtexture",
      "strength": 35
    },
    {
      "name": "preserve_lineart",
      "strength": 80
    }
  ],
  "prompt": "future positive processing guidance",
  "negative_prompt": "future negative processing guidance"
}
```

Each transform entry requires a non-empty `name`. A transform `strength`, when
present, must be a number from 0 through 100. Transform names are declarative in
this release: loading a preset does not run or require a registered transform.

Legacy presets remain supported. They may omit `transforms` and use the earlier
`strengths` object with `light`, `medium`, and `strong` values from 0 through 1,
plus optional `notes`.

Included placeholder chains:

- `watercolor_pencil_cleanup`
- `anime_lineart_cleanup`
- `general_ai_artifact_cleanup`
- `photoreal_cleanup`

The legacy `general_artifact_cleanup` preset remains available for existing
recommendations and workflows.

## Architecture

```text
dataset_forge/
|-- core/
|   |-- manifest.py
|   |-- paths.py
|   |-- logging.py
|   `-- config.py
|-- analysis/
|   |-- metrics.py
|   |-- duplicates.py
|   |-- texture.py
|   `-- quality.py
|-- presets/
|   |-- loader.py
|   `-- schema.py
|-- review/
|   `-- gallery.py
|-- recommendations/
|   `-- engine.py
|-- transforms/
|   |-- base.py
|   `-- registry.py
|-- exporters/
|   |-- base.py
|   `-- registry.py
|-- execution/
|   |-- base.py
|   |-- registry.py
|   |-- hashing.py
|   |-- state.py
|   |-- pipeline.py
|   `-- default.py
|-- resources/
|   |-- manager.py
|   `-- __init__.py
`-- cli.py
```

`Transform` and `Exporter` define names, descriptions, input requirements,
output types, parameters, and a `run()` contract. Their registries support
explicit discovery by name and reject duplicate registrations. No concrete
transform or exporter is included yet.

Existing public imports remain compatible. For example,
`dataset_forge.analysis`, `dataset_forge.presets`, `dataset_forge.gallery`, and
`dataset_forge.quality` continue to expose their previous entry points while
the implementation lives in the modular packages.

The active pipeline remains inspection-only. It does not call transform or
exporter registries, modify source files, or duplicate full-size images.

## Forge Pipeline

A `Pipeline` is an ordered collection of registered `PipelineStage` plugins.
Each stage declares:

- `id`, `name`, and `description`
- required and produced artifact names
- estimated runtime, RAM, VRAM, and disk writes
- expected output paths
- a `run()` implementation

The executor validates artifact dependencies before work begins. Its preview
shows stages that will run or skip, resource estimates, and expected files.

After every stage, Dataset Forge atomically updates
`pipeline_state.json`. `dataset-forge resume` reconstructs the saved default
pipeline and continues failed or pending stages. Completed stages are reused
only when all declared outputs exist and these fingerprints remain unchanged:

- ordered source-image list
- SHA-256 hashes of source files
- selected preset content
- pipeline configuration
- stage configuration, including custom quality-config content
- dependency-stage fingerprints

`pipeline_report.json` records the final status, stage durations, total
runtime, fingerprints, outputs, details, and errors. `--force-stage` bypasses
reuse for one named stage.

The bundled `default` pipeline contains four read-only plugins: `scan`,
`analysis`, `recommend`, and `review`. Future transforms, validators,
captioners, reviewers, and exporters can implement the same stage contract;
the executor does not contain category-specific logic.

## Resource Manager

All pipeline resource decisions are centralized in `ResourceManager`. Stages
declare estimates but do not choose their own worker count, CPU target, RAM
budget, I/O policy, cache policy, temporary-storage policy, or future GPU
scheduling.

Built-in profiles:

- `eco`: one worker, low CPU and I/O targets, minimal cache, aggressive cleanup
- `balanced`: moderate workers and resource limits; the default
- `max`: all detected CPU workers, high limits, performance-oriented caching
- `overnight`: conservative adaptive processing for unattended runs
- `custom`: balanced starting values intended for file-based configuration

Select a profile:

```powershell
dataset-forge run --pipeline default --profile eco --input C:\images
dataset-forge run --pipeline default --profile balanced --input C:\images
dataset-forge run --pipeline default --profile max --input C:\images
dataset-forge run --pipeline default --profile overnight --input C:\images
```

Override individual settings:

```powershell
dataset-forge run --pipeline default --profile eco --input C:\images `
  --max-workers 3 `
  --cpu-limit 60 `
  --ram-limit 4096 `
  --io-throttle medium `
  --cache-policy standard `
  --adaptive
```

The preview and simulation display the effective worker count, CPU target, RAM
limit, cache and temporary-storage policies, adaptive-mode status, estimated
runtime, peak RAM and VRAM, disk writes, and temporary storage.

Adaptive mode accepts a system-load provider and reduces the effective worker
budget when load exceeds the profile CPU target. The current implementation is
deliberately conservative and provides an extension point for future real-time
CPU and GPU monitoring. Current built-in stages run serially, but future
parallel stages must use the manager's worker budget rather than creating their
own scheduling policy.

Profiles can be loaded from JSON:

```json
{
  "profiles": {
    "quiet": {
      "max_workers": 2,
      "cpu_target_percent": 40,
      "ram_limit_mb": 2048,
      "io_throttle": "low",
      "cache_policy": "minimal",
      "temporary_storage_policy": "cleanup",
      "adaptive_mode": true,
      "disk_limit_mb": 1024
    }
  }
}
```

Or equivalent YAML:

```yaml
profiles:
  quiet:
    max_workers: 2
    cpu_target_percent: 40
    ram_limit_mb: 2048
    io_throttle: low
    cache_policy: minimal
    temporary_storage_policy: cleanup
    adaptive_mode: true
    disk_limit_mb: 1024
```

Use a custom profile file with:

```powershell
dataset-forge simulate --pipeline default --profile quiet `
  --profile-config C:\configs\profiles.yaml `
  --input C:\images
```

Before execution, the manager refuses plans whose estimated disk write or peak
RAM exceeds the selected profile limit. `--force` explicitly bypasses this
safety check. Simulation and dry-run remain read-only and show the estimates
without creating output or temporary files.

The effective profile is stored in `pipeline_state.json` and
`pipeline_report.json`, so resumed work retains its scheduling policy.

## Plugin SDK

Dataset Forge provides abstract plugin interfaces for analyzers, transforms,
validators, captioners, exporters, importers, and review providers. Every
plugin declares stable metadata, artifact dependencies, configurable
parameters, resource estimates, and a `run()` implementation.

Manage discovered plugins:

```powershell
dataset-forge plugins list
dataset-forge plugins info lora.dataset_analyzer
dataset-forge plugins disable lora.dataset_analyzer
dataset-forge plugins enable lora.dataset_analyzer
```

Built-in discovery scans `dataset_forge.plugins.builtin`. The registry accepts
other Python package names, preserving a path to future external package
discovery without changing the pipeline engine.

Plugin failures are logged and returned as failed results by default. Through
`PluginStageAdapter`, a failed plugin writes a small failure artifact and can be
isolated from the rest of the pipeline. Fail-fast behavior remains available
for workflows that require it.

Included proof plugins:

- `lora.dataset_analyzer`
- `lora.artifact_risk_analyzer`
- `lora.duplicate_risk_analyzer`
- `lora.caption_placeholder`
- `lora.export_placeholder`
- `cleanup.watercolor_placeholder`
- `cleanup.anime_placeholder`

These plugins emit JSON plans or reports only. They do not clean images,
generate captions, copy datasets, or train models.

See [PLUGIN_DEVELOPMENT.md](PLUGIN_DEVELOPMENT.md) for the SDK contract,
lifecycle, configuration format, pipeline adapter, and LoRA plugin guidance.

The governing rule is:

> Core should orchestrate. Plugins should specialize.

## Cleanup Planning

Generate an explainable, non-destructive cleanup plan from an existing Dataset
Forge output folder:

```powershell
dataset-forge plan --output C:\dataset-report
```

This reads the latest manifest, dataset health report, recommendations, enabled
plugin metadata, selected resource profile, and cleanup rules. It writes only:

```text
output/cleanup_plan.json
output/cleanup_plan.csv
```

Summarize a saved plan:

```powershell
dataset-forge summarize-plan --output C:\dataset-report
```

Explain one image by ID or filename:

```powershell
dataset-forge explain castle.png --output C:\dataset-report
```

The planner supports these actions:

- `KEEP`
- `CLEAN_LIGHT`
- `CLEAN_MEDIUM`
- `CLEAN_STRONG`
- `MANUAL_REVIEW`
- `DUPLICATE_REVIEW`
- `EXCLUDE`
- `REGENERATE`
- `CAPTION_ONLY`

Each image decision includes confidence, measured evidence, expected quality
benefit, projected quality, a capability-matched plugin recommendation, preset,
strength, resource estimates, and warnings.

Default thresholds and mappings are stored in
`src/dataset_forge/config/cleanup_rules.json`. Supply replacement JSON or YAML:

```powershell
dataset-forge plan --output C:\dataset-report --rules C:\configs\cleanup.yaml
```

User preferences can also be supplied as JSON or YAML:

```json
{
  "default_preset": "watercolor_pencil_cleanup",
  "preferred_plugins": ["cleanup.watercolor_placeholder"],
  "caption_healthy_images": false,
  "allow_gpu": true
}
```

```powershell
dataset-forge plan --output C:\dataset-report --config C:\configs\planning.json
```

Plugin routing uses capabilities such as `artifact_cleanup`,
`watercolor_cleanup`, `anime_lineart_cleanup`, `photoreal_cleanup`, and
`captioning`. Core does not reference or call specific cleanup models.

The orchestrator decides what should happen. It never invokes the recommended
plugin, edits an image, generates a caption, trains a LoRA, or calls an external
model. See [ARCHITECTURE.md](ARCHITECTURE.md) for the decision lifecycle and
capability-routing design.

## User Control and Approval

The generated `cleanup_plan.json` is a recommendation and is never edited by
approval commands. User choices are stored separately in:

```text
output/user_overrides.json
output/decision_audit_log.jsonl
```

Override, lock, approve, or reject individual images:

```powershell
dataset-forge override castle.png --action KEEP --reason "Good target style already"
dataset-forge lock banana_knight.png --action CLEAN_LIGHT
dataset-forge unlock banana_knight.png
dataset-forge approve castle.png
dataset-forge reject bad_sample.png --reason "Wrong subject"
```

Bulk controls support simple, extensible filters:

```powershell
dataset-forge approve --severity WARNING
dataset-forge override --action CLEAN_LIGHT --where artifact_score_gt=70
dataset-forge override --action KEEP --where filename_contains=banana
dataset-forge lock --where action=EXCLUDE
dataset-forge approve-all
```

Inspect, reset, or interactively review controls:

```powershell
dataset-forge show-overrides
dataset-forge reset-overrides
dataset-forge review-plan
```

Interactive review displays the measured scores, explanation, plugin
recommendation, and estimated benefit before accepting a choice.

Every change regenerates:

```text
output/approved_cleanup_plan.json
output/approved_cleanup_plan.csv
```

These files merge the generated recommendation with overrides, locks,
approvals, and rejections. Each decision exposes `status`, `approval_status`,
`override_status`, `locked`, and `execution_eligible`. Future cleanup,
captioning, exporting, or GPU-heavy stages must read only the approved plan.

The safety-gate API is `require_approved_plan(output_path)`. It refuses
expensive or destructive execution until every decision is approved, rejected,
or locked. A future command may bypass the gate only through an explicit
`--yes` or `--force` choice.

When a cleanup plan is regenerated, the raw recommendation may change, but
saved locks and overrides remain separate and continue to determine the
effective approved plan. Review-gallery cards display proposed action,
approval, override, and lock state when plan metadata is available.

## Plan Execution

Process approved decisions through a safe placeholder transform:

```powershell
dataset-forge execute-plan --output C:\dataset-report
```

`execute-plan` requires `approved_cleanup_plan.json` and calls the same
`require_approved_plan()` safety gate as any other execution stage. Execution
fails safely with a clear error if the approved plan is missing, incomplete,
or blocked.

Only decisions with one of these effective actions, that are approved or
locked (and not rejected), are processed:

- `CLEAN_LIGHT`
- `CLEAN_MEDIUM`
- `CLEAN_STRONG`
- `CAPTION_ONLY`

`KEEP`, `MANUAL_REVIEW`, `DUPLICATE_REVIEW`, `EXCLUDE`, `REGENERATE`, rejected
decisions, and unapproved decisions are skipped.

Each eligible image is processed by `PlaceholderCleanupTransform`, a safety
test transform only. It does not call external models, clean images, caption
images, or train anything. It copies the source image unchanged into
`output/processed/` with an action suffix, for example:

```text
output/processed/castle_clean_light.png
output/processed/castle_clean_light.png.json
```

The `.json` sidecar records that the file is a placeholder copy. Existing
files in `output/processed/` are never overwritten; if a name collides, a
numeric suffix is appended. Source images are never modified.

Useful flags:

```powershell
dataset-forge execute-plan --output C:\dataset-report --dry-run
dataset-forge execute-plan --output C:\dataset-report --limit 10
dataset-forge execute-plan --output C:\dataset-report --force
dataset-forge execute-plan --output C:\dataset-report --profile eco
```

- `--dry-run` previews what would be processed and writes nothing.
- `--limit` caps the number of images executed in this run.
- `--force` re-processes images even if a prior run already completed them.
- `--profile` / `--profile-config` select the resource profile used to
  estimate the worker budget.
- `--resume` is accepted for explicitness; resuming from
  `output/execution_report.json` is the default behavior unless `--force` is
  used.

Execution writes:

```text
output/processed/
output/execution_report.json
output/execution_report.csv
```

Each report record includes `image_id`, `filename`, `action`, `source_path`,
`output_path`, `plugin_id`, `status`, `started_at`, `completed_at`,
`duration`, `skipped_reason`, and `error`. Re-running `execute-plan` skips
images whose output file from a prior `completed` run still exists, unless
`--force` is passed.

The command prints a summary:

```text
Approved items: <count>
Executed: <count>
Skipped: <count>
Failed: <count>
Output folder: output/processed/
Total disk written: <size>
```

## Traditional Cleanup (Placeholder)

`TraditionalCleanupTransform` is the infrastructure for future deterministic
(non-AI) cleanup filters. It defines a configurable operation pipeline driven
by named cleanup profiles, but does **not** yet execute any filtering. Each
eligible image is copied unchanged into `output/precleanup/`, alongside a
`.json` sidecar describing which operations *would* run.

Supported operation names (config-only for now):

- `median_filter`
- `bilateral_filter`
- `adaptive_bilateral`
- `isolated_pixel_removal`
- `speck_removal`
- `local_contrast_normalization`
- `edge_preserving_smoothing`
- `frequency_smoothing`
- `morphology_cleanup`

Built-in profiles live under `presets/cleanup_profiles/`:

- `watercolor_light`
- `watercolor_medium`
- `colored_pencil_light`
- `colored_pencil_medium`
- `anime_lineart_preserve`
- `photoreal_microcleanup`
- `watercolor_microcleanup_light`

Run it directly:

```powershell
dataset-forge traditional-cleanup --output C:\dataset-report --profile watercolor_light
```

Run conservative watercolor and colored-pencil microcleanup:

```powershell
dataset-forge traditional-cleanup --input C:\images --output C:\dataset-report --profile watercolor_microcleanup_light
```

The former profile name remains available as a deprecated compatibility alias.

Useful flags:

```powershell
dataset-forge traditional-cleanup --output C:\dataset-report --profile watercolor_light --preview
dataset-forge traditional-cleanup --output C:\dataset-report --profile watercolor_light --dry-run
dataset-forge traditional-cleanup --output C:\dataset-report --profile watercolor_light --limit 10
```

- `--preview` prints the selected profile, its operation chain, and
  estimated resource/disk usage, without modifying any images.
- `--dry-run` previews what would be processed and writes nothing.
- `--limit` caps the number of images processed in this run.

The same dispatch is available from `execute-plan`:

```powershell
dataset-forge execute-plan --output C:\dataset-report --transform traditional_cleanup --cleanup-profile watercolor_light
```

Each processed image's sidecar (`output/precleanup/<file>.json`) records
`plugin_id`, `profile`, `requested_operations`, `parameters`, `timestamp`,
`source_hash`, `output_hash`, and `placeholder: true`. The execution report
additionally records the selected `transform`, `cleanup_profile`,
`requested_operations`, `placeholder_execution`, and `output_location`. No
real filtering, AI model calls, or pixel edits are performed by this step.

## Private Synthetic Benchmarks

Dataset Forge includes a local benchmark generator for testing cleanup quality
across general dataset workflows, not only LoRA preparation. Benchmark images
are private and local by default. Users provide their own clean reference image
under `benchmarks/reference/`, then run:

```powershell
python scripts/generate_benchmark_defects.py `
  --input benchmarks/reference/my_clean_reference.png `
  --output benchmarks/synthetic_defects `
  --seed 1234 `
  --strength medium
```

The command preserves the input and generates a reference PNG, deterministic
glitter, microtexture, oversharpening, color-noise, and mixed-artifact variants,
plus `benchmark_manifest.json`. Both private references and generated images
are ignored by Git and should not be committed. See
[benchmarks/README.md](benchmarks/README.md).

## Tests

```powershell
$env:PYTHONPATH="src"
python -m unittest discover -s tests
```
