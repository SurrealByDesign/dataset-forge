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
  returns `InspectResult`. 23/23 tests passing (`tests/test_inspect.py`).
- `src/dataset_forge/report.py` — JSON and TXT report writers.
  `write_json_report()`, `write_txt_report()`, `write_inspection_report()`.
  Output matches CLI_OUTPUT.md schema. Deterministic sort order.
  40/40 tests passing (`tests/test_report.py`).
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

**v1 milestone complete.** The vertical slice ships.

Suggested next steps (pick one):

1. **Run against the real anthropomorphic dataset** and evaluate finding quality.
   This is the primary validation test for v1.

2. **Calibration benchmarks** — create synthetic images with known artifact levels
   to validate and tighten TextureAnalyzer thresholds. Required before findings
   can be treated as calibrated evidence rather than uncalibrated opinions.

3. **Second analyzer** — glitter or frequency/periodic noise. The Analyzer
   contract is proven; adding a second analyzer validates it generalizes.
