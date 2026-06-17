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

- `scripts/compute_metrics.py` — calibration metrics from inspection report +
  decision review. Outputs: agreement summary, finding/clean review, missed-
  detection table (sorted by z-score), false-positive table, threshold
  diagnostics. Optional `--dataset` flag re-runs `evaluate_texture` on missed
  detections to fill in metrics not stored in the report. Optional `--output`
  writes `metrics_report.json`. No core contracts changed.
  30/30 tests passing (`tests/test_compute_metrics.py`).

- `scripts/review_decisions.py` — interactive decision-review tool.
  Shows each image alongside Dataset Forge's current decision (FINDING/CLEAN),
  severity, and texture metrics. Reviewer marks AGREE / DISAGREE / UNSURE.
  Writes resumable `decision_review.json` (saved after every review).
  Excludes `inspect_output/`, `output/`, `_report/` subdirectories.
  Opens images in system viewer by default; `--no-preview` to disable.
  Schema: `dataset-forge/decision-review/v1`.
  42/42 tests passing (`tests/test_review_decisions.py`).

---

## Completed (continued)

- `src/dataset_forge/analyzers/crystalline.py` — `CrystallineFacetingAnalyzer`.
  First-pass uncalibrated detector for the crystalline faceting artifact family.
  Category: `artifact.crystalline_faceting`. Detection rule (from calibration
  diagnostic): `pencil_grain >= 45 AND watercolor_smoothness < 52 AND micro >= 20`.
  Confidence capped at 0.45 (uncalibrated). FP rate conservative at 0.28.
  Wired into `run_inspect()` alongside TextureAnalyzer.
  35/35 tests passing (`tests/test_analyzer_crystalline.py`).

  Live run on anthropomorph dataset (100 images):
  - Group A (TextureAnalyzer already found): 18 images — crystalline also flags all 18
  - Group B (missed by TextureAnalyzer): 9/11 caught ← new signal
  - Group C (agreed clean → false positives): 13 images
  - Group U (unsure — needs re-review): 14 images flagged
  - abesteak.jpg (grain=43.3) and appledoctor.jpg (grain=33.1) remain uncaught —
    both below grain threshold; may require frequency-domain signal

  Precision against labeled data (B vs B+C): 9 / (9+13) = 40.9%  ← matches diagnostic
  Recall against Group B: 9 / 11 = 81.8%  ← matches diagnostic

---

- `scripts/review_decisions.py` — updated for multi-analyzer reports.
  - `_build_findings_index` now keeps the **first** finding per image (TextureAnalyzer),
    preventing the crystalline finding from silently overwriting it in the stored record.
  - `_build_crystalline_index` — new function; indexes `artifact.crystalline_faceting`
    findings by filename for separate display and storage.
  - `_extract_crystalline_evidence` — new function; extracts `grain`, `smooth`, `micro`
    from a crystalline finding's evidence dict.
  - `_extract_metrics` now returns a `category` field (primary finding category).
  - `_print_image_header` now shows:
    - Primary finding category next to DF decision
    - Crystalline evidence line (`grain`, `smooth`, `micro`, `[uncalibrated]`) when present
  - Stored review record now includes `category` and `grain` fields (additive; old records
    remain valid).
  - `--focus` flag and file-based focus list already existed; no new CLI flags needed.
  - Focus list for the 13 FP + 14 UNSURE re-review at:
    `scripts/crystalline_focus_review.txt`
  - 70/70 tests passing (`tests/test_review_decisions.py`).
  - 22 new tests added (total 548 passing across all suites).

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
| Crystalline faceting analyzer | **Done** — `src/dataset_forge/analyzers/crystalline.py` |
| Glitter analyzer | Not yet created |
| Frequency/noise analyzer | Not yet created |
| Sharpness/halo analyzer | Not yet created |
| JSON + TXT report writer | **Done** — `src/dataset_forge/report.py` |
| Inspect runner | **Done** — `src/dataset_forge/inspect.py` |
| CLI `inspect` command | **Done** — `dataset-forge inspect <path>` |

---

## Next Recommended Task

**CrystallineFacetingAnalyzer is live.** First-pass precision: 40.9%, recall: 81.8%.
13 false positives against agreed-clean group; 14 UNSURE images also flagged.

Suggested next steps (pick one):

1. **Re-review the 13 false positives** — run `scripts/review_decisions.py`
   with `--focus` on the 13 Group C images that crystalline now flags. Some may
   be genuine faceting that was reviewed as AGREE-clean but actually have faceting
   artifacts. This would adjust the effective precision upward.

2. **Review the 14 UNSURE catches** — the 14 Group U images that crystalline flags
   were marked UNSURE in the original decision review. Re-reviewing them with the
   crystalline finding visible may break the UNSURE tie.

3. **Synthetic benchmark** — create benchmark images with known crystalline faceting
   to calibrate the pencil_grain / smoothness thresholds properly. This is required
   before the uncalibrated flags are removed.

4. **Threshold tightening experiment** — try `pencil_grain >= 50` to reduce FP to
   ~5 while keeping recall at ~72%. Run pencil_grain_diagnostic.py to evaluate.
