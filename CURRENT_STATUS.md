# Dataset Forge – Current Status

*Update this file after every major implementation milestone.*

---

## Current Milestone

**Version 1: Dataset Forge Inspect**

Pipeline: `Dataset → DatasetContext → Analyzer → Finding → Report`

---

## Completed

- `src/dataset_forge/cli.py` — `inspect` subcommand wired.
  `dataset-forge inspect <path>` works end-to-end. Terminal output matches
  CLI_OUTPUT.md. `--output`, `--recursive`, `--limit` flags supported.
- `src/dataset_forge/inspect.py` — full v1 spine runner. Discovers images,
  builds `DatasetContext`, runs `TextureAnalyzer`, writes JSON + TXT reports,
  optionally writes inspection gallery PNG. Returns `InspectResult`
  (includes `gallery_path: Path | None`).
  23/23 tests passing (`tests/test_inspect.py`).
- `src/dataset_forge/inspect_gallery.py` — PNG contact-sheet writer.
  Four groups: HIGH findings, MEDIUM findings, threshold boundary, clean
  reference. Receives `image_scores` from `run_inspect()` — no extra I/O.
  Exposed helpers: `build_image_records()`, `select_gallery_groups()`.
  45/45 tests passing (`tests/test_inspect_gallery.py`).
- CLI `--gallery` flag: `dataset-forge inspect <path> --gallery` writes
  `inspection_gallery.png` to the inspect output folder and prints the path.
- `src/dataset_forge/report.py` — JSON and TXT report writers.
  `write_json_report()`, `write_txt_report()`, `write_inspection_report()`.
  Output matches CLI_OUTPUT.md schema. Deterministic sort order.
  Score table (all images ranked by microtexture, [FINDING]/[clean] tagged).
  50/50 tests passing (`tests/test_report.py`).
- `src/dataset_forge/analyzers/texture.py` — first concrete `Analyzer`.
  Wraps `analysis/texture.py`'s `evaluate_texture()`. Emits
  `texture.high_microtexture` and `texture.error` Findings.
  Uncalibrated (benchmark pending); confidence capped at 0.70.
  24/24 tests passing (`tests/test_analyzer_texture.py`).
- `src/dataset_forge/analyzers/base.py` — abstract `Analyzer` base class.
  Defines the `analyze()` contract, `analyzer_id`, `supported_categories`,
  `benchmark_version`. 12/12 tests passing (`tests/test_analyzer_base.py`).
- `src/dataset_forge/context.py` — `DatasetContext` dataclass (frozen) and four
  sub-dataclasses: `ResolutionStats`, `AspectRatioStats`, `TextureDistributions`,
  `FrequencyDistributions`. Statistical reference frame for all analyzers.
  32/32 tests passing (`tests/test_context.py`).
- `src/dataset_forge/finding.py` — `Finding` dataclass (frozen) and `Severity` enum.
  This is the universal output contract. Treat as stable public API.
  18/18 tests passing (`tests/test_finding.py`).
- Repository hygiene audit: `.gitignore` now excludes Python caches, local
  runtimes, generated reports, benchmark outputs, private datasets, temporary
  files, and model/checkpoint artifacts. No files were deleted.
- Local/runtime artifact tracking cleanup approved: `.runtime-deps/` and
  `.claude/settings.local.json` should be removed from Git tracking only and
  kept locally. `benchmarks/real_samples_manifest.proposal.json` records the
  metadata needed before replacing tracked real sample images.
- `docs/benchmark_inventory.md` documents current benchmark folders, synthetic
  defect assets, real sample assets, category coverage, and benchmark gaps.
- `analysis/texture.py` — microtexture density, speck density, watercolor smoothness,
  dataset-relative statistics (legacy; not yet wired to Finding)
- Deterministic cleanup V1 (`presets/cleanup_profiles/watercolor_microcleanup_light.json`) —
  frozen, out of scope for v1 inspect pipeline
- Decision Engine (`decisions.py`) — frozen, out of scope for v1 inspect pipeline
- Dataset Health Report (`analysis/health.py`) — 47/47 tests passing; out of scope for v1 inspect
- Project constitution: `PROJECT_BIBLE.md`, `DIRECTION.md`, `WHY.md`, `ARCHITECTURE.md`,
  `ROADMAP.md`, `CURRENT_STATUS.md`, `CLI_OUTPUT.md`, `CLAUDE.md`

---

- `scripts/label_ground_truth.py` — interactive CLI labeling tool.
  Walks dataset images, shows texture metrics from inspection_report.json,
  accepts ARTIFACT / CLEAN / UNCERTAIN labels with optional notes.
  Writes resumable `ground_truth.json` (saved after every label).
  Skips already-labeled images unless `--review` is passed.
  Excludes `inspect_output/`, `output/`, `_report/` subdirectories.
  Opens each image in the system viewer before the prompt by default
  (`os.startfile` on Windows, `open`/`xdg-open` elsewhere). Disable with
  `--no-preview`. Preview failures are silently swallowed; session continues.
  42/42 tests passing (`tests/test_label_ground_truth.py`).

---

- `scripts/review_decisions.py` — interactive decision-review tool.
  Shows each image alongside Dataset Forge's current decision (FINDING/CLEAN),
  severity, and texture metrics. Reviewer marks AGREE / DISAGREE / UNSURE.
  Writes resumable `decision_review.json` (saved after every review).
  Excludes `inspect_output/`, `output/`, `_report/` subdirectories.
  Opens images in system viewer by default; `--no-preview` to disable.
  Schema: `dataset-forge/decision-review/v1`.
  42/42 tests passing (`tests/test_review_decisions.py`).

---

## In Progress

Nothing currently in flight.

---

## Known Blockers

- **Calibration benchmarks** — synthetic images with known artifact levels required
  before analyzer thresholds can be trusted. Local generated assets now cover
  glitter, recursive microtexture/periodic texture, oversharpening, color noise,
  and mixed artifacts, but duplicate detection, halo-only samples, multi-strength
  calibration sets, and real-sample provenance are still missing.

---

## Missing Core Abstractions (v1 gap)

| Type | Status |
|---|---|
| `Finding` | **Done** — `src/dataset_forge/finding.py` |
| `DatasetContext` | **Done** — `src/dataset_forge/context.py` |
| `Analyzer` base class | **Done** — `src/dataset_forge/analyzers/base.py` |
| Texture analyzer | **Done** — `src/dataset_forge/analyzers/texture.py` |
| Glitter analyzer | Not yet created |
| Frequency/noise analyzer | Not yet created |
| Sharpness/halo analyzer | Not yet created |
| JSON + TXT report writer | **Done** — `src/dataset_forge/report.py` |
| Inspect runner | **Done** — `src/dataset_forge/inspect.py` |
| CLI `inspect` command | **Done** — `dataset-forge inspect <path>` |

---

## Next Recommended Task

**v1 milestone complete.** Gallery and score table added. Visual validation confirmed.

Real-dataset run (100 images): 19 findings (2 HIGH, 17 MEDIUM), 81 clean.
Contact sheet review confirmed analyzer signal is meaningful, not random noise.

Suggested next steps (pick one):

1. **Run the labeling session** — execute `scripts/label_ground_truth.py` against
   the real anthropomorph dataset now, while the contact sheet review is fresh.
   This produces `ground_truth.json`, the input for all calibration work.

2. **Calibration metrics** — build `scripts/compute_metrics.py` to read
   `ground_truth.json` + `inspection_report.json` and print precision/recall/F1.
   Required before any threshold can be adjusted with evidence.

3. **Calibration policy doc** — write `docs/calibration_policy.md` to lock down
   amendment rules before running the threshold sweep.
