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

## Crystalline Calibration — Post-Focused-Review Results

Focused review pass: 27 images (13 former Group C + 14 former Group U) re-reviewed
with crystalline evidence displayed. Full calibration computed in
`scripts/_crystalline_calibration_report.py`.

**Crystalline flags (54 total):**
| Class | Count | Meaning |
|---|---|---|
| A — co-detected, reviewer AGREE | 19 | Both analyzers + human agree: confirmed artifact |
| B — crystalline-only, reviewer DISAGREE | 11 | Missed detections caught by crystalline |
| C — crystalline-only, reviewer AGREE | 24 | Confirmed false positives |
| U — UNSURE | 0 | Fully resolved by focused review |

**Precision:**
- Crystalline-only (B / B+C): **31.4%** (revised; was 40.9% pre-review)
  — Dropped because 14 formerly-UNSURE resolved to AGREE (FP), not TP
- All crystalline flags (A+B / A+B+C): **55.6%**

**Recall vs confirmed-missed population (all DISAGREE images, DF called CLEAN):**
- 11/13 = **84.6%** (was 81.8%; 2 more disagreements confirmed after focused review)
- Remaining uncaught: abesteak.jpg (grain=43.3) and appledoctor.jpg (grain=33.1)

**Artifact detector vs GPT detector:**  
Correctly described as an artifact detector. One non-GPT image confirmed to have
crystalline faceting; the analyzer flagged it correctly. This is expected behaviour —
the signal measures pixel-level mid-frequency structure, not GPT provenance.
Whether non-GPT images with this artifact belong in the dataset is a curation
decision, not a detection error.

**Status:** First-pass validated, uncalibrated. Produces meaningful signal.
Should not be used as a final gate (human review required for all findings).

**Remaining UNSURE (11 images):** all DF-FINDING via TextureAnalyzer only;
crystalline adds no ambiguity. Address in a separate TextureAnalyzer calibration pass.

---

## Crystalline FP Characterization (24 disagreements)

Script: `scripts/crystalline_fp_characterization.py`
Contact sheet: `inspect_output/crystalline_fp_characterization.png` (24 images, sorted by grain desc)

The 24 FP images cluster into four distinct patterns:

| Cluster | Count | Pattern | Root Cause |
|---|---|---|---|
| A | 5 | grain >= 55, moderate smooth | Severity disagreement: real faceting, reviewer tolerates it |
| B | 2 | grain 50-52, smooth 41-43 | Same as A: real but tolerable |
| C | 15 | grain 45-55, smooth >= 45 | Signal gap: TP and FP populations interleave |
| D | 2 | smooth < 34 (very low) | Family mismatch: dense subject texture (porcupine, scales) |

**KEY FINDING: Threshold adjustment cannot solve the FP problem.**
TP (missed artifacts) and FP (clean images) grain values are deeply interleaved in the 45-55 range:
- FP grain: 45.3-64.7 (18/24 FPs fall in grain 45-55)
- TP grain: 45.96-67.6 (8/11 TPs fall in grain 45-55)

At no integer threshold does precision improve without significant recall loss:
- grain>=46: loses 1 TP, removes only 3 FP (precision 32%, recall 77%)
- grain>=52: loses 6 TP, removes 12 FP (precision 29%, recall 39%)

**Recommended actions (ordered):**
1. Do NOT raise the grain threshold. The interleaving makes it counterproductive.
2. Design a **fourth discriminating signal** to separate Cluster C (spatial coherence,
   directional frequency content, or micro-edge profile). This is the main unblocking step.
3. Add a severity split: grain 45-55 with moderate smooth emits LOW not MEDIUM severity.
   This correctly labels Clusters A and B as tolerable findings rather than suppressing them.
4. Investigate Cluster D (cthulhudiver, witchkingporcupine) visually — subject-texture
   (porcupine spines, wetsuit scales) masquerading as crystalline signal.

---

## Crystalline Severity Calibration

Script: `scripts/crystalline_severity_calibration.py`

**Question:** Is the current MEDIUM-for-everything severity assignment partly causing the disagreements?

**Answer: Yes, for two distinct populations.**

Population 1 — Severity overstatement on Cluster A+B (7 FP images, grain 50-65):
Real artifact signal, but reviewer considers it within-range for this artistic style.
MEDIUM label overstates urgency. LOW would be correct.

Population 2 — Severity overstatement on low-grain TPs (10 images, grain 46-55):
Confirmed missed artifacts but mild signal. Currently MEDIUM alongside images at grain=76.
LOW would correctly communicate "present but subtle."

**Four models evaluated:**

| Model | LOW | MEDIUM | HIGH | Description |
|---|---|---|---|---|
| 0 (current) | 0 | 54 | 0 | MEDIUM for everything |
| 1 (grain tiers) | 26 | 21 | 7 | grain<55=LOW, 55-65=MEDIUM, 65+=HIGH |
| 2 (co-detect) | 35 | 19 | 0 | co-detected=MEDIUM, cryst-only=LOW |
| 3 (combined) | 34 | 20 | 0 | co-detect>=55 OR cryst-only>=65=MEDIUM; else LOW |

**Key finding from grain tier analysis:**
- grain 45-54: cryst-only precision 28% (7 TP / 25 total cryst-only)
- grain 55-64: cryst-only precision 33% (3 TP / 9 total cryst-only)
- grain 65+:   cryst-only precision 100% (1 TP / 1 total cryst-only — no FPs in this tier)
- Co-detected (grain 55+): 100% confirmed artifacts (19/19)

**Recommended model: Model 3 (combined grain + co-detection)**
- co-detected with TextureAnalyzer AND grain >= 55 → MEDIUM (dual signal, confirmed)
- crystalline-only AND grain >= 65 → MEDIUM (100% precision tier)
- all other crystalline findings → LOW (weak or uncorroborated; present but mild)

Under Model 3:
- MEDIUM: 20 findings (100% correct — 19 co-detected confirmed + 1 cryst-only at grain>65)
- LOW: 34 findings (29% correct — 10 confirmed TPs at low grain, 24 FPs)
- LOW does not suppress findings; it correctly labels them as mild/uncertain

**Simplest viable implementation: Model 1 (grain-only)**
- grain >= 65 → HIGH
- grain >= 55 → MEDIUM
- grain < 55 → LOW
Does not require DatasetContext changes or inter-analyzer communication.
Model 3 requires knowing whether TextureAnalyzer also fired — needs post-analyze
step in run_inspect() or evidence field set by the orchestrator.

**What severity calibration does NOT fix:**
- The 24-image FP population (signal gap in grain 45-55, Cluster C) still produces findings.
  Severity change moves them from MEDIUM to LOW, which is more accurate, but doesn't suppress them.
- A fourth discriminating signal is still required for the signal-gap problem.

---

## Crystalline Severity Calibration — Implemented

**Grain-only severity model live in `src/dataset_forge/analyzers/crystalline.py`.**

Rules:
- `grain >= 65` → HIGH (100% crystalline-only precision in calibration set)
- `grain >= 55` → MEDIUM (co-detected images; 33% cryst-only precision)
- `grain < 55`  → LOW (weak or borderline signal; 28% cryst-only precision)

New exports: `_SEVERITY_MEDIUM_GRAIN = 55.0`, `_SEVERITY_HIGH_GRAIN = 65.0`
New private helper: `_severity_for_grain(grain)` — clean separation of severity logic.
New evidence fields: `severity_medium_grain`, `severity_high_grain` (for auditability).

**Severity distribution on anthropomorph dataset (54 crystalline findings):**

| Severity | Old | New | Changed |
|---|---|---|---|
| HIGH | 0 | 7 | +7 (grain 65-76.7; all confirmed artifacts) |
| MEDIUM | 54 | 21 | -33 |
| LOW | 0 | 26 | +26 (grain 45-55; weak/borderline signal) |

The 7 HIGH findings are the most confidently confirmed crystalline artifacts
(grain 65+). All were previously MEDIUM alongside grain=45 borderline cases.

**Tests: 49/49 passing (`tests/test_analyzer_crystalline.py`)**
New test class: `TestCrystallineFacetingSeverityTiers` (12 tests):
- LOW/MEDIUM/HIGH tier assignment at and around each boundary
- Constant ordering invariant
- Tier contiguity (no gap at boundary)
- Updated: `test_finding_severity_is_medium` → `test_finding_severity_is_low_for_grain_below_medium_threshold`

**Full suite: 562/562 passing (was 548 before this session, +14 new tests total)**

---

## Benchmark Framework (v1)

**`src/dataset_forge/benchmark.py`** — core benchmark module.
- `BenchmarkExpectation`, `BenchmarkCase`, `ExpectationResult`, `BenchmarkRun` dataclasses
- `load_manifest(path)` — parses `benchmark_manifest.json`; validates schema version
- `run_benchmark(manifest_path, project_root, registry)` — resolves image paths,
  builds per-group `DatasetContext`, runs each analyzer expectation
- `write_json_results(run, path)` / `write_txt_results(run, path)` — structured outputs
- Private images / missing images: skipped (not failed) regardless of `private` flag
- Groups: cases sharing a `context_group` share a `DatasetContext` so TextureAnalyzer
  z-scores are meaningful within the group
- Registry: `texture_analyzer/v1` and `crystalline_faceting_analyzer/v1` pre-registered

**`benchmarks/benchmark_manifest.json`** — 6 cases, 8 expectations (public, no private images required):
- `synth_reference_negative`: texture=no-find, crystalline=no-find (grain=35.7) [synthetic-generated]
- `synth_color_noise_negative`: texture=no-find, crystalline=no-find (grain=36.3) [synthetic-generated]
- `synth_mixed_artifacts_crystalline_negative`: crystalline=no-find (grain=38.5) [synthetic-generated]
- `synth_crystalline_low`: crystalline=find LOW (grain=45.1, smooth=47.3) [**committed**]
- `synth_crystalline_medium`: crystalline=find MEDIUM (grain=64.2, smooth=36.6) [**committed**]
- `synth_crystalline_negative_smooth_guard`: crystalline=no-find (grain=62.0, smooth=53.2) [**committed**]

**`benchmarks/local_benchmark_manifest.json`** (gitignored) — 3 private real-sample cases:
- Positive MEDIUM: snakemountain.jpg (grain=62.4, smooth=36.6)
- Positive LOW: picklewizard.jpg (grain=50.9, smooth=46.9)
- Negative: vtp4jc1040s51.jpg (grain=35.7)

**`scripts/run_benchmarks.py`** — CLI runner.
- `uv run python scripts/run_benchmarks.py` — runs all 8 public expectations, 0 skipped
- `uv run python scripts/run_benchmarks.py --manifest benchmarks/local_benchmark_manifest.json`
- Exit 0 = all non-skipped passed; exit 1 = any failure; exit 2 = manifest error

**`benchmarks/synthetic_defects/06_crystalline_low.png`** — committed fixture (git-tracked)
- Crosshatch spacing=4 amplitude=15. grain=45.1, smooth=47.3, micro=53.0. Fires LOW.

**`benchmarks/synthetic_defects/07_crystalline_medium.png`** — committed fixture (git-tracked)
- Crosshatch spacing=6 amplitude=30. grain=64.2, smooth=36.6, micro=65.8. Fires MEDIUM.
- Grain matches real calibration anchor (snakemountain grain=62.4, smooth=36.6).

**`benchmarks/synthetic_defects/08_crystalline_negative_smooth.png`** — committed fixture (git-tracked)
- Crosshatch spacing=12 amplitude=30. grain=62.0, smooth=53.2, micro=43.3. Does NOT fire.
- Validates watercolor_smoothness < 52 guard: high grain, high micro, but smooth=53.2 > ceiling.

**`scripts/generate_crystalline_fixtures.py`** — regenerates the 3 committed fixtures deterministically.
- Fully documented crosshatch parameters in source.

**Live benchmark run (2026-06-18): 8/8 PASS, 0 skipped, 0 failed.**

**`tests/test_crystalline_fixtures.py`** — 32 regression tests for committed fixtures.
- Score stability tests (exact values ± 0.5 tolerance)
- Detection tests (fires/doesn't fire)
- Severity tier tests (LOW, MEDIUM)
- Guard validation (smooth_above_ceiling confirmed for negative)
- Monotonicity tests (medium > low grain, negative smooth highest)

**Tests: 29/29 (`tests/test_benchmark.py`) + 32/32 (`tests/test_crystalline_fixtures.py`)**
Full suite: **623/623 passing** (was 591; +32 new tests)

---

## TextureAnalyzer Public Benchmark (2026-06-18)

**Committed synthetic fixtures for TextureAnalyzer positive detection.**

**Approach:** Two-image committed context group (`texture_committed`).
- Clean anchor (`09_texture_clean.png`): flat grey 128. micro=0.0. No finding (micro < absolute floor 15).
- Noise positive (`10_texture_positive.png`): seeded uniform noise [68,189) seed=42. micro=88.7. Fires MEDIUM.
- Z-score math: for group [0, X], mean=X/2, pstdev=X/2, z=1.0 exactly (structurally pinned).
- z=1.0 maps to Severity.MEDIUM (_Z_MEDIUM = 1.0). Stable regardless of noise amplitude.

**Files:**
- `benchmarks/synthetic_defects/09_texture_clean.png` — committed fixture (git-tracked)
- `benchmarks/synthetic_defects/10_texture_positive.png` — committed fixture (git-tracked)
- `scripts/generate_texture_fixtures.py` — deterministic generator (seeded RNG)
- `tests/test_texture_fixtures.py` — 21 regression tests

**Benchmark manifest additions (2 new cases, 2 new expectations):**
- `synth_texture_clean_negative`: texture=no-find [committed]
- `synth_texture_medium_positive`: texture=find MEDIUM [committed]

**Live benchmark run (2026-06-18): 10/10 PASS, 0 skipped, 0 failed.**
**Tests: 21/21 (`tests/test_texture_fixtures.py`)**
**Full suite: 644/644 passing** (was 623; +21 new tests)

---

## Public Benchmark Release Fix (2026-06-18)

Release audit found that `09_texture_clean.png`, `10_texture_positive.png`,
`scripts/generate_texture_fixtures.py`, and `tests/test_texture_fixtures.py`
were created but never staged — making the public manifest unreproducible from
a fresh clone.

**Fix:** Staged and committed all four files. Updated `benchmarks/README.md` to:
- Document which fixture files are committed vs generated
- Correct the quick-start command (`uv run python scripts/run_benchmarks.py`)
- Remove the stale claim that all synthetic_defects must be generated

**Post-fix state:**
- Public benchmark runnable immediately after `git clone` — no generation step required
- 10/10 expectations PASS, 0 skipped
- Full suite: 644/644 passing

---

## Release Preparation (2026-06-18)

- **LICENSE** added: MIT, `Copyright (c) 2026 surrealbydesign`
- **README** rewritten: user-facing intro, first-run walkthrough, safety guarantees,
  current limitations near the top, accurate install/benchmark/test commands,
  architecture docs linked in a table rather than summarized inline
- **pyproject.toml**: `license = {text = "MIT"}` added

---

## Research: Speck / Glitter Artifact Family (2026-06-18)

Probe: `scripts/_probe_speck_glitter.py` — 100 images × 15 signals.
Report: `benchmarks/results/probe_speck_glitter/SPECK_GLITTER_RESEARCH_REPORT.md`

**Recommendation: DEFER.**

**Key findings:**
- Cohen's d = −0.181 (inverted): clean images score higher than artifact images on highlight_speck
- Root cause: microtexture raises local blur baseline → isolated-bright condition harder to satisfy in
  artifact images. Clean watercolor has isolated whites against smooth washes → scores high.
- r(highlight_speck, microtexture) = −0.089: near-zero. Independent phenomena.
- vtp4jc (clean reference) ranks 13th in dataset (speck=69.8) — detector would trigger on clean art.
- New signals (component count, scatter index, brightness excess) all correlate with highlight_speck
  at r > 0.93 and inherit the same failure.
- 70% of top-30 speck images are crystalline-flagged; glitter-like facets are already caught.
- Estimated independent speck-only prevalence: ~3% — below threshold for a dedicated family.

**`highlight_speck` role:** Appropriate as a component of `watercolor_smoothness` (weight=0.15).
Not suitable as a primary artifact classifier.

---

## Research: Oversharpening / Halo Artifact Family (2026-06-18)

Probe: `scripts/_probe_oversharpening.py` — 100 images × 6 signals.
Report: `benchmarks/results/probe_oversharpening/OVERSHARPENING_RESEARCH_REPORT.md`

**Recommendation: DEFER.**

Key findings: ringing_score has stddev=2.19 (no variance). halo_score inverts — clean images
score higher than artifact images (same mechanism as speck). 60% overlap with crystalline.
Better signal requires USM residual approach or directional undershoot measurement.

---

## Performance: Phase 1 — evaluate_texture() caching (2026-06-18)

**`@functools.lru_cache(maxsize=None)` added to `evaluate_texture()` in
`src/dataset_forge/analysis/texture.py`.**

**Change:** 2 lines (add `import functools`, add `@functools.lru_cache(maxsize=None)` decorator).
No contract changes. No test changes. All 644 tests pass.

**Measured on anthropomorph dataset (100 images, 2 analyzers):**

| | Texture-pass time | Per image |
|---|---|---|
| Before (3 uncached calls per image) | 7.43s | 74.3ms |
| After (1 miss + 2 hits per image) | 2.44s | 24.4ms |
| **Speedup** | **3.04×** | |

End-to-end `run_inspect()` wall clock: 10.15s (was ~15s estimated before cache).
Cache profile: 100 misses + 200 hits = 67% hit rate (correct: 1 miss + 2 hits per image × 2 analyzers).

**Extrapolated savings (texture passes only):**

| Dataset size | Before | After | Saved |
|---|---|---|---|
| 100 images | 7.4s | 2.5s | 5.0s |
| 1,000 images | 74s | 25s | 50s |
| 10,000 images | 743s | 248s | 495s |

**Behavior:** Cache persists within a Python process. For the CLI (one process per invocation),
this is correct — no staleness risk. Phase 2 (`ImageMeasurements` dataclass + explicit cache
routing) will replace the `lru_cache` with a proper measurements cache and remove this decorator.

---

## In Progress

Nothing currently in flight.

---

## Known Blockers

*(none)*

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

**Benchmark framework is live (644/644 tests).** All 10 public expectations pass from fresh clone.

Two artifact family research probes complete (oversharpening and speck/glitter) — both DEFERRED.

Suggested next steps (pick one):

1. **Fourth discriminating signal for crystalline** — the 24 Cluster C FPs (grain 45-55) can only
   be reduced by a signal that separates their spatial pattern from confirmed TPs.
   Candidates: spatial coherence, directional frequency energy, micro-edge profile.

2. **TextureAnalyzer calibration** — separate pass for the 11 remaining UNSURE images
   (all TextureAnalyzer-only findings). Current z-score thresholds are uncalibrated.

3. **Recursive detail overload** — next artifact family from ARCHITECTURE.md not yet investigated.
   No existing partial signal; would require a fresh probe before any implementation.
