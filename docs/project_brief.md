# Dataset Forge — Project Brief

## Mission

Dataset Forge is a non-destructive LoRA dataset optimization platform.

Its purpose is to analyze, curate, harmonize, and conservatively improve
AI-generated training images while preserving the original artwork.

This is not an image enhancement tool. It is a LoRA dataset engineering tool.

The governing question behind every feature:

> **Would I rather train my LoRA on this version than the original?**

If the answer is no, the feature should not exist.

---

## The Core Problem

Modern AI image generators produce training images with structural artifacts
that LoRA models learn alongside the intended content:

- **Recursive microfacet texture** — GPT-generated images exhibit repeating
  high-frequency texture patterns that are not present in authentic watercolor art.
- **Speck noise** — Small isolated high-contrast pixels that are not part of the
  underlying artwork.
- **Tonal drift** — Generated images tend toward higher microtexture density than
  reference images (dataset average: 39.89 vs. reference baseline: 26.86).

These artifacts are not always visible to the human eye but are measurable
and are learned by LoRA training.

The goal is not to make images look better. The goal is to give the LoRA
fewer false patterns to learn.

---

## Design Philosophy

### Preservation Over Intervention

Dataset Forge does not ask: *"Can this image be cleaned?"*

It asks: *"Should this image be cleaned?"*

Expected benefit is weighed against intervention cost. An image that is already
suitable for training should remain untouched. Any intervention that cannot
demonstrate measurable benefit relative to its cost should not happen.

### Intervention Cost

Every intervention carries cost:

- Risk of edge degradation
- Risk of color shift
- Risk of introducing processing artifacts
- Risk of softening stylistically intentional detail
- Computational cost
- Human review burden

Intervention cost is not zero. Cleanup that does not clearly pay for itself
makes the dataset worse, not better.

### LEAVE_ALONE Is a First-Class Outcome

The Decision Engine routes images into four states. LEAVE_ALONE is not a
fallback for when analysis fails. It is the desired outcome when an image
is already suitable for training.

A dataset where most images are LEAVE_ALONE is a good dataset.

---

## Architecture

### analysis/texture.py

The primary analysis pipeline. All measurements are deterministic.

Produces `TextureImageResult` (per image) and `TextureReportSummary` (dataset-level).

Measures:

- `microtexture_density_score` — high-frequency energy at ~1px scale,
  computed as `_saturating(mean(|gray - GaussianBlur(gray, σ=1.0)|), 12.0)`
- `speck_density` — isolated high-contrast pixel count
- `watercolor_smoothness` — broad tonal smoothness metric
- Preservation metrics — edge fidelity, histogram correlation
- Dataset-relative statistics — z-score relative to dataset mean/stddev

Analysis must remain deterministic. No ML inference in this layer.

### decisions.py

Contains `evaluate_decision()`, a pure function with no side effects.

Routes each image to one of four outcomes based on signal extraction:

| Outcome | Meaning |
|---|---|
| `LEAVE_ALONE` | Image is already suitable for training. Do not touch. |
| `DETERMINISTIC_ONLY` | Speck removal and mild smoothing expected to help. |
| `AI_CONSERVATION_CANDIDATE` | Held for future Semantic Conservator. |
| `MANUAL_REVIEW` | Conflicting signals or heavy texture. Human decides. |

The Decision Engine is additive. It runs after `recommend_evidence()` and
writes only to `engine_*` fields on `TextureImageResult`. It does not replace
or override `recommend_evidence()`.

Routing is intentionally biased toward preservation. When in doubt,
the engine routes to LEAVE_ALONE or MANUAL_REVIEW rather than intervention.

### Deterministic Cleanup V1

Profile: `watercolor_microcleanup_light.json`

Status: **Frozen.**

Components:

- **Speck Removal** — sensitivity=32, max_area=5, replacement_blend=0.72, median_kernel=5
- **Edge Preserving Smoothing** — sigma_spatial=18, sigma_range=0.12, blend=0.22

Acceptance checks: pixel=14.0, hist=0.18, edge=0.12.

V1 is intentionally conservative. It solves isolated speck noise and mild
tonal roughness. It does not and cannot solve:

- Recursive GPT microfacet structure
- Semantically embedded generated texture
- Style inconsistency between images

These limitations are known and accepted. V1 is not tuned further without
new measurement evidence. The right response to these limitations is the
Semantic Conservator phase, not loosening the V1 profile.

### analysis/health.py

Aggregates existing analysis outputs into a Dataset Health Report.

Outputs: `dataset_health_report.json`, `dataset_health_report.html`,
`dataset_health_report.txt`

Sections:

1. Executive summary — health score, LoRA readiness, headline, recommendations
2. Decision Engine summary — counts and ratios by outcome
3. Cleanup summary — intervention counts and acceptance rates
4. Dataset statistics — texture, resolution, duplicates
5. Consistency scores — texture, style, cleanup, resolution, aspect ratio, overall
6. LoRA Readiness detail — penalty breakdown with disclaimer
7. Export guidance
8. Future sections (null keys for forward compatibility)

The health report is an aggregation layer only. It must never re-run analysis,
modify images, or invoke cleanup.

### exporters/lora.py (planned)

The LoRA Export Prep stage. Specification at `docs/spec_lora_export_prep.md`.

Goals:
- Prepare a clean export folder from selected/cleaned images
- Preserve aspect ratio; never stretch
- Optional square padding
- Write `export_manifest.json`
- Never modify originals
- Future: caption file support

---

## LoRA Optimization Workflow

```
Source images
    ↓
Texture Analysis (texture.py)
    ↓
Decision Engine (decisions.py)
    ↓
┌────────────────────────────────────────┐
│ LEAVE_ALONE → export as-is            │
│ DETERMINISTIC_ONLY → V1 cleanup       │
│ AI_CONSERVATION_CANDIDATE → (future)  │
│ MANUAL_REVIEW → human decides         │
└────────────────────────────────────────┘
    ↓
Dataset Health Report (health.py)
    ↓
LoRA Export Prep (exporters/lora.py)
    ↓
Export manifest + training-ready folder
```

Originals are never overwritten at any stage.

---

## Future: Semantic Conservator

The Semantic Conservator is a future optional AI stage — not the default,
not currently implemented.

Its purpose:

> Produce the same artwork with fewer GPT fingerprints.

This is not image enhancement. It is targeted semantic cleanup of patterns
that are measurably harmful to LoRA training.

Design constraints:

- AI proposals are always measured against the original
- Results are compared using the same metrics as deterministic cleanup
- Human review is available at every step
- Automatic application is never the default
- Dataset Forge remains the decision-maker; the AI is a proposal engine only

The Semantic Conservator handles what V1 cannot: recursively embedded
microfacet structure that cannot be addressed without semantic understanding
of the image content.

---

## Roadmap

| Stage | Status |
|---|---|
| Texture analysis | Complete |
| Deterministic cleanup V1 | Complete (frozen) |
| Decision Engine | Complete |
| Dataset Health Report | Complete |
| LoRA Export Prep | Specified, not implemented |
| Reference image registry | Planned |
| Semantic Conservator | Future phase |
| Caption integration | Future phase |
| LoRA validation feedback loop | Future phase |

---

## Guiding Principles

1. **The best cleanup is often no cleanup.**
2. **LEAVE_ALONE is a first-class outcome, not a failure state.**
3. **Never overwrite originals.**
4. **Measure before intervening. Measure after intervening.**
5. **Deterministic before AI. Human review before automatic application.**
6. **Intervention cost is real. It must be justified.**
7. **If uncertain, ask: "Would I rather train my LoRA on this version?"**
8. **Dataset Forge does not ask "Can this image be changed?" It asks "Should this image be changed?"**
