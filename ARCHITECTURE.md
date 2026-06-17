# Dataset Forge – Architecture

> The architecture should anticipate growth.
> The implementation should not.

---

## Version 1 Pipeline

```
Dataset
  └─► DatasetContext          statistical reference frame for the dataset
        └─► Analyzer(s)       independent, calibrated, deterministic
              └─► Finding(s)  universal output contract
                    └─► Report  human-readable, explainable output
```

Every component in v1 maps to one node in this pipeline.
Nothing in v1 lives outside this pipeline.

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
    total_images: int
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
    analyzer: str                   # e.g. "glitter_analyzer/v1"
    category: str                   # e.g. "artifact.glitter"
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
    base.py          — abstract Analyzer with analyze() contract
    glitter.py
    frequency.py     — periodic noise / crystalline microtexture
    sharpness.py     — oversharpening / edge halos
    texture.py       — microtexture density
    duplicates.py    — exact and near-duplicate detection
```

**Analyzer contract:**

```python
class Analyzer(ABC):
    @abstractmethod
    def analyze(
        self,
        image_path: Path,
        context: DatasetContext,
    ) -> list[Finding]: ...
```

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

The report layer consumes Findings and produces human-readable output.

v1 outputs:
- `inspection_report.json` — machine-readable, complete findings
- `inspection_report.txt` — human-readable summary
- `inspection_report.html` — browsable per-image breakdown (optional in v1)

Reports must not re-run analysis or make decisions. They present findings.

---

## Benchmarks

Location: `benchmarks/`

```
benchmarks/
    synthetic/
        glitter/
        periodic_noise/
        oversharpening/
        speckling/
        halo/
    real/            (future — Flux, SDXL, Ideogram, Midjourney samples)
    results/         (versioned benchmark run outputs)
```

Every analyzer ships with a benchmark that validates its thresholds.

---

## What Is Not in v1

The following exist in the codebase but are out of scope for v1.
They should not be modified, expanded, or depended on by v1 code.

| Module | Status |
|---|---|
| `cleanup/` | Out of scope for v1 |
| `plugins/` | Out of scope for v1 |
| `execution/` | Out of scope for v1 |
| `transforms/` | Out of scope for v1 |
| `exporters/` | Out of scope for v1 |
| `review/` | Out of scope for v1 |
| `recommendations/engine.py` | Out of scope for v1 |

These modules represent future phases. They are preserved, not deleted,
because they may be valuable later. They are simply not part of the
v1 vertical slice.

---

## Relationship to Legacy Modules

| Bible concept | Legacy equivalent | Notes |
|---|---|---|
| DatasetContext | (none yet) | Must be created |
| Finding | `ImageEvidence` / `evidence.py` | Different schema — needs clean Finding type |
| Analyzer | `analysis/texture.py`, `analysis/metrics.py` | Wrap or port to Analyzer contract |
| Report | `analysis/health.py`, `reporting.py` | Too broad; v1 report is simpler |

---

## Artifact Family Architecture

> GPT-style image contamination is not a single phenomenon.
> Each artifact family requires its own detection signal.
> A single generic texture score cannot reliably distinguish between them.

This was established empirically during calibration review of the anthropomorph
dataset. Eleven missed detections were investigated; diagnostic analysis showed
that `highlight_speck` (isolated near-white pixel detection) had Cohen's d = −0.01
against the clean population for crystalline faceting images — no discriminating
power at all. Different artifact families require different metrics.

---

### Artifact Families

Each family is a distinct contamination phenomenon requiring its own analyzer,
evidence schema, benchmark, and (eventually) cleanup strategy.

| Family | Description | Primary Signal | Status |
|---|---|---|---|
| **Microtexture** | Elevated high-frequency noise across image surfaces; GPT rendering fingerprint | `microtexture_density`, z-score vs dataset | Implemented (`analyzers/texture.py`) |
| **Speck / Glitter** | Isolated near-white specular points; appears as scattered bright dots | `highlight_speck` (pixels ≥242, locally isolated) | Partially captured; no independent threshold yet |
| **Crystalline Faceting** | Angular micro-polygon shading; surfaces appear carved from facets; distributed mid-frequency texture | `pencil_grain`, `texture_consistency`, `local_contrast` | Not yet implemented; identified as primary recall gap |
| **Recursive Detail Overload** | Compulsive synthetic detail in every region; no restful areas; entire surface treated as foreground | Frequency distribution, detail density | Not yet implemented |
| **Oversharpening / Halos** | Edge ringing, halo artifacts around transitions, over-accentuated outlines | Edge sharpness, frequency analysis | Planned (`analyzers/sharpness.py`) |

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

**Category naming convention:** `artifact.<family>` — e.g.:

- `artifact.microtexture`
- `artifact.speck`
- `artifact.crystalline_faceting`
- `artifact.recursive_detail`
- `artifact.oversharpening`

Analyzers for different families may run in the same pipeline pass and emit
Findings independently. No analyzer should attempt to detect more than one
family. If signals overlap, that is the Findings consumer's problem, not the
analyzer's.

---

### Cleanup Architecture (future — v2+)

Cleanup must be artifact-specific. A single generic smoothing filter applied
to all findings would:

- destroy legitimate pencil grain while removing GPT microtexture
- blur intentional watercolor edges while removing halos
- damage genuine specular highlights while removing speck artifacts

Each artifact family requires a cleanup strategy tuned to that family's
characteristics. The correspondence is:

| Artifact Family | Candidate Cleanup Strategy |
|---|---|
| Microtexture | Edge-preserving denoise (detail-aware, not Gaussian) |
| Speck / Glitter | Isolated bright-pixel suppression with local inpainting |
| Crystalline Faceting | Mid-frequency band suppression; texture field smoothing |
| Recursive Detail Overload | Frequency-domain attenuation; semantic detail reduction (AI phase) |
| Oversharpening / Halos | Unsharp-mask reversal; edge deconvolution |

Cleanup families inherit their scope from the corresponding Finding. An image
with a `artifact.speck` Finding receives speck cleanup, not microtexture cleanup.

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

## Guiding Rule

> Core should orchestrate. Analyzers should specialize. Finding is the contract.
> Each artifact family is a first-class citizen with its own detector, evidence, and cleanup path.
