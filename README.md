# Dataset Forge

Dataset Forge is an evidence-first toolkit for understanding AI training
datasets.

The current milestone is **Dataset Forge Inspect**: a read-only v1 workflow that
builds dataset context, runs analyzers, emits findings, and writes reports.

```text
Dataset -> DatasetContext -> Analyzer -> Finding -> Report
```

Dataset Forge is being built for LoRA and generative-AI dataset quality work,
with the first reference use case focused on watercolor and colored-pencil
anthropomorphic character datasets that may contain GPT-style artifacts such as
glitter, crystalline microtexture, periodic noise, oversharpening, speckle, and
edge halos.

The project goal is not to make images prettier. The goal is to understand a
dataset well enough to recommend the smallest useful action, including the
possibility that healthy images should be left alone.

## Project Status

Dataset Forge is under active development and is not ready for general users
yet.

The v1 Inspect spine is the active direction. Some older or future-facing
modules may exist in the repository, but they are not the current product
surface unless they participate in the v1 pipeline above.

## Current Milestone: Dataset Forge Inspect

Version 1 is analysis only.

The v1 pipeline is:

- `Dataset`: the image folder being inspected.
- `DatasetContext`: dataset-level statistics such as image dimensions, aspect
  ratios, texture distributions, frequency distributions, and duplicate hashes.
- `Analyzer`: an independent, deterministic checker that reads the context and
  evaluates images.
- `Finding`: the universal output contract for analyzer results.
- `Report`: JSON and text output that explains what was found and why.

The target command is:

```powershell
dataset-forge inspect C:\images
```

The v1 report should explain findings clearly, include calibrated evidence, and
make it valid for a dataset to produce zero recommended changes.

## What v1 Includes

- `Finding` as the universal analyzer output contract.
- `DatasetContext` as the statistical reference frame for the dataset.
- An `Analyzer` base class and initial analyzers.
- JSON and TXT inspection reports.
- A CLI entry point for `dataset-forge inspect <path>`.
- Calibration benchmarks for analyzer thresholds.

## What v1 Does Not Include

Cleanup is the long-term product goal, but it is not implemented in v1.

The following are out of scope for Dataset Forge Inspect:

- image cleanup or pixel modification
- AI cleanup or external model calls
- UI
- caption generation or caption auditing
- plugin systems
- exporters
- training a LoRA or evaluating trained model output

Existing future-facing code is preserved, but v1 should not expand or depend on
cleanup, AI, UI, captioning, plugin, or exporter systems.

## Safety Principles

- Analyze before modifying.
- Preserve source images.
- Prefer deterministic and explainable methods.
- Use dataset-relative evidence instead of judging every image in isolation.
- Treat uncalibrated findings as provisional.
- Leave healthy images alone.

Dataset Forge Inspect does not overwrite, move, delete, or edit source images.
Generated reports are written separately.

## Setup

Requirements:

- Python 3.11 or newer

```powershell
cd dataset-forge
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install -e .
```

## Expected Inspect Output

The intended v1 command is:

```powershell
dataset-forge inspect C:\images --output C:\dataset-report
```

Expected generated files:

```text
dataset-report/
|-- inspection_report.json
`-- inspection_report.txt
```

The report should include:

- dataset summary statistics
- analyzer versions
- findings grouped by image
- severity, confidence, benchmark version, and evidence for each finding
- plain-language explanations
- a summary of images with findings and images with no issues

See [CLI_OUTPUT.md](CLI_OUTPUT.md) for the target command output and report
shape.

## Benchmarks

Benchmarks are mandatory for trusted analyzer thresholds.

Synthetic benchmark coverage is planned for:

- glitter contamination
- periodic noise
- oversharpening halos
- speckle noise
- duplicate detection

Current benchmark inventory is documented in
[docs/benchmark_inventory.md](docs/benchmark_inventory.md). Local benchmark
images are private by default and should not be committed unless their
provenance and license status are known.

## Repository Guides

Start with these documents when changing the project:

- [PROJECT_BIBLE.md](PROJECT_BIBLE.md) - project constitution
- [DIRECTION.md](DIRECTION.md) - current milestone and scope
- [WHY.md](WHY.md) - rationale behind the architecture
- [ARCHITECTURE.md](ARCHITECTURE.md) - v1 pipeline structure
- [ROADMAP.md](ROADMAP.md) - milestone plan
- [CURRENT_STATUS.md](CURRENT_STATUS.md) - current implementation status
- [CLI_OUTPUT.md](CLI_OUTPUT.md) - expected CLI/report output

## Tests

```powershell
$env:PYTHONPATH="src"
python -m unittest discover -s tests
```
