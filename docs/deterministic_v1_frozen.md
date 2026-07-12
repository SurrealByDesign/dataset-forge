# Deterministic Cleanup Pipeline — Version 1 (Frozen)

> **Historical design record. Not part of Dataset Forge v1.9.3.** This file
> documents an earlier cleanup experiment. No public cleanup command or source
> dataset application workflow exists. Do not treat it as current guidance.

**Status:** Frozen. Do not modify parameters, add operations, or re-run tuning experiments
on this profile. The ceiling has been empirically established.

**Profile file:** `presets/cleanup_profiles/watercolor_microcleanup_light.json`

**Governing principle:** "Preserve edges. Simplify facets."

**Success criterion:** "Would I rather train my LoRA on the cleaned version than the original?"

---

## What V1 Is

A two-operation deterministic cleanup pipeline optimized for watercolor and
colored-pencil style images. Both operations are preservation-first: they target
specific measurable artifact types and reject any candidate result that exceeds
the acceptance thresholds, even if that means leaving the image unchanged.

### Operations (in order)

**1. Speck Removal**

```json
{
  "name": "speck_removal",
  "parameters": {
    "sensitivity": 32,
    "max_area": 5,
    "replacement_blend": 0.72,
    "median_kernel": 5
  }
}
```

Targets isolated high-brightness specks and crystalline glitter artifacts smaller
than 5 pixels in area. Uses a 5×5 median kernel (validated at 3.6× better
efficacy than the earlier 3×3 default). Blend 0.72 preserves surrounding texture
at the replacement boundary. Sensitivity 32 is conservative — misses borderline
specks rather than risk removing intentional highlights.

**2. Edge-Preserving Smoothing**

```json
{
  "name": "edge_preserving_smoothing",
  "parameters": {
    "sigma_spatial": 18,
    "sigma_range": 0.12,
    "blend": 0.22
  }
}
```

A mild pass of domain-transform edge-preserving filtering. sigma_range=0.12
keeps the filter conservative — it does not cross strong color edges. Blend 0.22
limits the effect to roughly one-fifth of maximum EPS strength. At this setting
the output is visually indistinguishable from the input at normal viewing
distances.

### Acceptance Checks (per image)

```json
{
  "max_average_pixel_difference": 14.0,
  "max_color_histogram_difference": 0.18,
  "max_edge_difference": 0.12
}
```

Any result exceeding any threshold is rejected and the original is kept. Full
100-image validation: 100/100 accepted, all metrics well within limits.

### Ruled Out (not in V1)

| Operation | Reason |
|---|---|
| `local_contrast_normalization` (CLAHE) | Enhancement operator — increases microtexture rather than reducing it |
| Gaussian blur | Reduces overall sharpness; structural complexity remains, merely blurred |
| Bilateral filter at ceiling | Softens edges before solving recursive GPT facet structure |
| `frequency_smoothing` | Sigma needed for effect is sigma that causes visible blur |

---

## What V1 Does Well

- **Speck and glitter suppression.** Isolated high-brightness pixels from
  diffusion glitter are reliably removed without touching surrounding color.
  Validated on `toilet.jpg`, `toilet2.jpg`, `witchkingporcupine.jpg`,
  `potatoviking.webp`, `yagahut.jpg`, and others (highlight_speck_score ≥ 67).

- **Zero visible damage.** 100/100 images accepted by all three preservation
  metrics across the full ANTHROPOMORPHS dataset. No image was rejected or
  visually degraded in 100-image validation.

- **Conservative non-intervention.** When signals are ambiguous or the image is
  near the dataset centroid, V1 does nothing. Preferred failure mode is
  under-cleaning.

- **Measurable microtexture reduction.** Speck removal produces a small but
  consistent reduction in `microtexture_density_score` on high-speck images.
  Not a dramatic change — the improvement is LoRA-relevant, not cosmetically
  obvious.

- **Fully deterministic and reproducible.** No randomness, no AI calls, no
  parameter sampling. Same input always produces the same output.

---

## What V1 Does Not Solve

These are known limitations, not bugs. They define the boundary that motivated
the AI Conservator design.

- **Recursive GPT microfacet structure.** Images with `microtexture_density_score`
  above ~50 have recursive sub-pixel faceting that originates from how diffusion
  models layer detail. Local operators reach their preservation limit before the
  structure clears. Increasing EPS or bilateral strength beyond V1 parameters
  causes visible edge softening without eliminating the facets. This was confirmed
  empirically across multiple ceiling experiments.

- **Crystalline highlights baked into large regions.** Speck removal targets
  isolated pixels (max_area ≤ 5). Crystalline highlight patterns covering larger
  contiguous areas are outside its scope.

- **highlight_speck_score noise.** The speck detector picks up JPEG compression
  artifacts and legitimate bright artwork highlights in addition to GPT glitter.
  Images with moderate speck scores (40–55) may not benefit from speck removal
  and can produce false-positive intervention signals in the Decision Engine.

- **Style normalization.** V1 does not attempt to close the gap between GPT
  generation aesthetics and hand-drawn reference style. That requires semantic
  understanding of what texture is intentional vs. artifact — which is the
  AI Conservator's job.

- **Caption generation, resolution normalization, format conversion.** Out of
  scope for this pipeline stage.

---

## Decision Engine Integration

The V1 profile operates alongside the Decision Engine (additive layer,
`evaluate_decision()` in `src/dataset_forge/decisions.py`). The engine routes
images into one of four outcomes before any cleanup is applied:

| Engine outcome | Meaning for V1 |
|---|---|
| `LEAVE_ALONE` | Do not apply V1. Image is within acceptable range. |
| `DETERMINISTIC_ONLY` | Apply V1. Expected benefit outweighs intervention cost. |
| `AI_CONSERVATION_CANDIDATE` | Apply V1 first; escalate residual structure to AI. |
| `MANUAL_REVIEW` | Hold. Either signals conflict or structure exceeds V1 ceiling. |

Across the full ANTHROPOMORPHS dataset (100 images):
- 51 → LEAVE_ALONE
- 25 → DETERMINISTIC_ONLY (all within V1's proven effective range)
- 0 → AI_CONSERVATION_CANDIDATE (no AI backend configured)
- 24 → MANUAL_REVIEW (16 are heavy-GPT images awaiting AI phase; 8 are
  conflicting-signal cases)

---

## MANUAL_REVIEW Heavy-Microtexture Cases — AI Conservator Candidates

The following images are confirmed beyond V1's capability. They are not
failures of the pipeline — they are the motivation for the AI Conservator
phase. Both the legacy `recommend_evidence()` engine and `evaluate_decision()`
agree on MANUAL_REVIEW for the eight heaviest cases.

| Filename | microtexture | Notes |
|---|---|---|
| teaparty.jpg | 66.1 | Most over-textured image in dataset |
| azathothdanzig.jpg | 62.7 | |
| hotdogcity.jpg | 61.5 | |
| private_sample_03.jpg | 60.1 | |
| Gwendolyn Heroes painting 2019.jpg | 60.0 | Known reference image — high natural microtexture |
| milkmanmilkcarton.jpg | 58.3 | |
| sopranosfoods.jpg | 54.4 | |
| terminator.jpg | 56.7 | |
| wizardofozsquirrels.jpg | 56.3 | |
| thundarrbunnies.jpg | 53.7 | |
| house2.jpg | 56.0 | |
| 41t44mqvlnl51.jpg | 53.3 | |
| greyskull.jpg | 53.3 | |
| garden.jpg | 51.8 | |
| BOBROSSHOTDOG.jpg | 52.2 | |
| thefallofthedamnhotdogs.jpg | 50.1 | |
| potatovikings.jpg | 52.6 | |
| humptydumpty.jpg | 50.6 | |

These 18 images will become `AI_CONSERVATION_CANDIDATE` when an AI Conservator
backend is configured. Until then they remain in MANUAL_REVIEW and are not
processed by V1.

---

## Compatibility Notes

- `recommend_evidence()` in `src/dataset_forge/recommendations/engine.py` remains
  the authoritative recommendation for all existing callers. Its output populates
  `TextureImageResult.recommendation` and `.explanation` unchanged.
- `evaluate_decision()` adds four additive fields:
  `engine_recommendation`, `engine_confidence`, `engine_deciding_factor`,
  `engine_explanation`. These do not replace or shadow existing fields.
- Do not migrate callers from `recommend_evidence()` to `evaluate_decision()` until
  cross-dataset validation is complete and no plan/report drift is confirmed.

---

## Version History

| Version | Date | Change |
|---|---|---|
| V1 | 2026-06-15 | Frozen. speck_removal kernel=5 validated; CLAHE removed; EPS at conservative ceiling; 100/100 accepted in full dataset run. |
