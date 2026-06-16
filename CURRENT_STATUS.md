# Dataset Forge – Current Status

*Update this file after every major implementation milestone.*

---

## Current Milestone

**Version 1: Dataset Forge Inspect**

Pipeline: `Dataset → DatasetContext → Analyzer → Finding → Report`

---

## Completed

- `src/dataset_forge/finding.py` — `Finding` dataclass (frozen) and `Severity` enum.
  This is the universal output contract. Treat as stable public API.
  11/11 tests passing (`tests/test_finding.py`).
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
  before analyzer thresholds can be trusted. No benchmark exists yet for glitter,
  periodic noise, oversharpening, speckling, or halo detection.

---

## Missing Core Abstractions (v1 gap)

| Type | Status |
|---|---|
| `Finding` | **Done** — `src/dataset_forge/finding.py` |
| `DatasetContext` | Not yet created |
| `Analyzer` base class | Not yet created |
| Glitter analyzer | Not yet created |
| Frequency/noise analyzer | Partial — `analysis/metrics.py` |
| Sharpness/halo analyzer | Not yet created |
| JSON report writer | Not yet created |
| CLI `inspect` command | Not yet created |

---

## Next Recommended Task

**Create `src/dataset_forge/context.py` — the `DatasetContext` dataclass.**

This is the statistical reference frame that all analyzers consume.
It should be built once per dataset run, before any analyzer executes.

v1 fields (from ARCHITECTURE.md):
- `schema_version: int`
- `analyzer_versions: dict[str, str]`
- `image_paths: list[Path]`
- `total_images: int`
- `resolution_stats` — min/max/mean/stddev of width and height
- `aspect_ratio_stats` — distribution
- `texture_distributions` — microtexture mean/stddev/p10/p90
- `frequency_distributions` — periodic noise baseline
- `duplicate_hashes: set[str]`

Keep it minimal. Do not pre-compute per-image results here.
DatasetContext is a read-only reference frame, not an accumulator.
