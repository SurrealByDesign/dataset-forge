# Dataset Forge -- Internal Calibration Notes

> Internal document. Contains private dataset calibration details, probe results,
> and development history. Not for public release.

---

## Crystalline Calibration -- Post-Focused-Review Results

Focused review pass: 27 images (13 former Group C + 14 former Group U) re-reviewed
with crystalline evidence displayed. Full calibration computed in
`scripts/_crystalline_calibration_report.py`.

**Crystalline flags (54 total):**
| Class | Count | Meaning |
|---|---|---|
| A -- co-detected, reviewer AGREE | 19 | Both analyzers + human agree: confirmed artifact |
| B -- crystalline-only, reviewer DISAGREE | 11 | Missed detections caught by crystalline |
| C -- crystalline-only, reviewer AGREE | 24 | Confirmed false positives |
| U -- UNSURE | 0 | Fully resolved by focused review |

**Precision:**
- Crystalline-only (B / B+C): **31.4%** (revised; was 40.9% pre-review)
  -- Dropped because 14 formerly-UNSURE resolved to AGREE (FP), not TP
- All crystalline flags (A+B / A+B+C): **55.6%**

**Recall vs confirmed-missed population:**
- 11/13 = **84.6%** (was 81.8%; 2 more disagreements confirmed after focused review)
- Remaining uncaught: abesteak.jpg (grain=43.3) and appledoctor.jpg (grain=33.1)

**Status:** First-pass validated, uncalibrated. Produces meaningful signal.
Should not be used as a final gate (human review required for all findings).

**Remaining UNSURE (11 images):** all DF-FINDING via TextureAnalyzer only;
crystalline adds no ambiguity.

---

## Crystalline FP Characterization (24 disagreements)

Script: `scripts/crystalline_fp_characterization.py`

The 24 FP images cluster into four patterns:

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

**Recommended next steps:**
1. Do NOT raise the grain threshold. The interleaving makes it counterproductive.
2. Design a fourth discriminating signal (spatial coherence, directional frequency
   content, or micro-edge profile).
3. Grain 45-55 with moderate smooth already emits LOW not MEDIUM (implemented).
4. Investigate Cluster D (subject-texture masquerading as crystalline signal).

---

## Crystalline Severity Calibration Analysis

Script: `scripts/crystalline_severity_calibration.py`

Four severity models evaluated:

| Model | LOW | MEDIUM | HIGH | Description |
|---|---|---|---|---|
| 0 (old) | 0 | 54 | 0 | MEDIUM for everything |
| 1 (grain tiers) | 26 | 21 | 7 | grain<55=LOW, 55-65=MEDIUM, 65+=HIGH |
| 2 (co-detect) | 35 | 19 | 0 | co-detected=MEDIUM, cryst-only=LOW |
| 3 (combined) | 34 | 20 | 0 | co-detect>=55 OR cryst-only>=65=MEDIUM; else LOW |

**Key finding from grain tier analysis:**
- grain 45-54: cryst-only precision 28% (7 TP / 25 total cryst-only)
- grain 55-64: cryst-only precision 33% (3 TP / 9 total cryst-only)
- grain 65+:   cryst-only precision 100% (1 TP / 1 total cryst-only -- no FPs in this tier)
- Co-detected (grain 55+): 100% confirmed artifacts (19/19)

**Implemented: Model 1 (grain-only)**
- grain >= 65 -> HIGH
- grain >= 55 -> MEDIUM
- grain < 55  -> LOW

Severity distribution on anthropomorph dataset (54 crystalline findings):
| Severity | Old | New |
|---|---|---|
| HIGH | 0 | 7 |
| MEDIUM | 54 | 21 |
| LOW | 0 | 26 |

---

## CrystallineFacetingAnalyzer -- Initial Calibration Run (anthropomorph dataset)

Live run on anthropomorph dataset (100 images):
- Group A (TextureAnalyzer already found): 18 images -- crystalline also flags all 18
- Group B (missed by TextureAnalyzer): 9/11 caught <- new signal
- Group C (agreed clean -> false positives): 13 images
- Group U (unsure -- needs re-review): 14 images flagged

Precision against labeled data (B vs B+C): 9 / (9+13) = 40.9%
Recall against Group B: 9 / 11 = 81.8%

---

## Research: Speck / Glitter Artifact Family

Probe: `scripts/research/_probe_speck_glitter.py` -- 100 images x 15 signals.
Report: `benchmarks/results/probe_speck_glitter/SPECK_GLITTER_RESEARCH_REPORT.md`

**Recommendation: DEFER.**

Key findings:
- Cohen's d = -0.181 (inverted): clean images score higher than artifact images
  on highlight_speck. Root cause: microtexture raises local blur baseline, making
  the isolation condition harder to satisfy in textured images. Clean watercolor
  art has isolated whites against smooth washes and scores high.
- r(highlight_speck, microtexture) = -0.089: near-zero. Independent phenomena.
- New signals (component count, scatter index, brightness excess) all correlate
  with highlight_speck at r > 0.93 and inherit the same inversion.
- 70% of top-30 speck images are already crystalline-flagged.
- Estimated independent speck-only prevalence: ~3% -- below threshold for a
  dedicated family.

`highlight_speck` role: appropriate as a component of `watercolor_smoothness`
(weight=0.15). Not suitable as a primary artifact classifier.

---

## Research: Oversharpening / Halo Artifact Family

Probe: `scripts/research/_probe_oversharpening.py` -- 100 images x 6 signals.
Report: `benchmarks/results/probe_oversharpening/OVERSHARPENING_RESEARCH_REPORT.md`

**Recommendation: DEFER.**

Key findings:
- `ringing_score` (Laplacian sign-alternation): stddev=2.19 -- no variance across
  dataset. Sign alternation is a property of all edges, not just oversharpened ones.
- `halo_score` (perpendicular strip brightness range): inverts. Clean images score
  higher than artifact images because clean watercolor has isolated hard outlines
  against smooth backgrounds, compressing strip range in textured images.
- 60% overlap with crystalline-flagged images.
- Better signal requires USM residual approach or directional signed undershoot
  measurement.

---

## Crystalline Fourth-Signal Research -- Patch-Size/Coherence Family (DEFER)

Goal: find a fourth discriminating signal to resolve the Cluster C grain
45-55 TP/FP interleave (see "Crystalline FP Characterization" above), since
threshold adjustment alone cannot solve it. Two candidates were probed,
both targeting the hypothesis that real crystalline faceting forms large,
spatially coherent polygon-shaped regions, while Cluster C's false positives
are amplitude-only elevation without that spatial structure.

Population for both probes: 11 TP (reviewer DISAGREE, crystalline-only)
vs. 15 Cluster-C FP (reviewer AGREE, crystalline-only, threshold-fringe),
from the anthropomorph decision-review dataset.

**Candidate 1 -- full-resolution patch coherence**
(`scripts/research/_probe_crystalline_patch_coherence.py`): elevated-amplitude
mask on the high-frequency map (threshold = per-image relative cutoff: max of
90th percentile, mean + 1.5 stddev, or a floor), connected-components at full
pixel resolution, patch-area statistics.

**Candidate 4 -- block-level coherence**
(`scripts/research/_probe_crystalline_block_coherence.py`): identical
high-frequency map and identical per-image relative threshold rule, but
block-pooled to a coarse grid before connected-components, isolating
resolution as the only changed variable relative to Candidate 1.

**Comparison:**

| Metric | Candidate 1 (full-res) | Candidate 4 (block-res) |
|---|---|---|
| Cohen's d (TP - Cluster-C FP) | -0.720 | -0.374 |
| r vs grain | -0.7076 | -0.5802 |
| r vs smoothness | -0.1627 | -0.1985 |
| r vs microtexture | -0.5043 | -0.2703 |
| Verdict | INCONCLUSIVE | INCONCLUSIVE |

**Mechanism-level diagnosis:** Both candidates score Cluster-C FPs *higher*
than confirmed TPs (d negative both times) -- the opposite of the hypothesis.
The two TP images with the strongest grain signal in the sample had the
*lowest* patch-coherence scores in the entire population at full resolution,
which explains the strong negative grain correlation: a per-image relative
amplitude threshold fragments busy/high-grain images into many small
disconnected components, while moderately-textured images (the Cluster-C FPs,
which sit at the low end of the already-narrow 45-55 grain band) are more
likely to have a small number of large smooth background or flat-color
regions cross the same relative cutoff, inflating their "coherence" score for
reasons unrelated to faceting.

Coarsening to block resolution (Candidate 4) attenuated but did not eliminate
this: effect size shrank from -0.720 to -0.374 and grain correlation from
-0.7076 to -0.5802, but the sign never flipped and grain correlation never
dropped below the 0.5 redundancy bar. This rules out "full-resolution
connected-components specifically" as the sole cause -- if it were, coarsening
should have flipped the sign or driven correlations near zero. Instead the
result implicates the shared mechanism in both candidates: defining "patch
coherence" via a per-image relative amplitude threshold inherently entangles
the measurement with overall texture amplitude (grain, microtexture),
regardless of the resolution it's computed at.

**Verdict: DEFER the patch-size/connected-component-coherence family as a
whole**, not just Candidate 1. Two independently-implemented measurements
sharing the same threshold-then-region-size mechanism both failed in the same
direction against the same population. Further tuning of threshold
percentiles or block sizes within this family is not expected to produce a
qualitatively different result -- the problem is in how the threshold is set
(relative to each image's own amplitude distribution), not in the grid
resolution it's applied to.

**Caveat:** n=11 TP / n=15 Cluster-C FP, single dataset, single review pass.
This is first-pass evidence only, consistent with the caveat convention used
throughout this document -- not a final calibration result, and not strong
enough on its own to permanently rule out a properly-designed spatial-shape
signal, only this specific amplitude-threshold-based mechanism.

**Recommendation: Candidate 2, structure-tensor orientation coherence, is the
next research target.** Structure-tensor coherence is a ratio of eigenvalues
normalized against local gradient energy, making it invariant to overall
texture amplitude by construction -- it directly avoids the mechanism that
caused both Candidate 1 and Candidate 4 to fail. The known risk to test
explicitly before trusting that result: hand-drawn directional
hatching/brushwork (a genuine stylistic technique present in this dataset) is
itself locally coherent and could false-positive against intentional artistic
technique, the same class of confound already flagged when Candidate 2 was
first proposed. No analyzer code, thresholds, or calibration status were
changed by this research.

---

## Performance: Phase 1 -- evaluate_texture() caching

`@functools.lru_cache(maxsize=None)` added to `evaluate_texture()`.

Measured on anthropomorph dataset (100 images, 2 analyzers):
- Before (3 uncached calls/image): 7.43s total, 74.3ms/image
- After  (1 miss + 2 hits/image):  2.44s total, 24.4ms/image
- Speedup: 3.04x
- Cache profile: 100 misses + 200 hits = 67% hit rate

Extrapolated savings (texture passes only):
- 1,000 images: ~50s saved
- 10,000 images: ~495s saved

Phase 2 (ImageMeasurements dataclass + explicit routing) will replace lru_cache
with a proper measurements cache.

---

## TextureAnalyzer Threshold Calibration -- First-Pass Evidence (Decision-Review Fallback)

Tool: `scripts/texture_threshold_calibration.py`. Dataset: anthropomorph dataset
(`C:\Users\someo\Desktop\ANTHROPOMORPHS`).

**Label source: `decision_review_fallback`.**

`ground_truth.json` for this dataset exists with a valid schema
(`dataset-forge/ground-truth/v1`) but `"labels": {}` -- empty. `created_at` and
`updated_at` are two minutes apart with nothing recorded, consistent with a
`label_ground_truth.py` session that was started and quit before any image was
labeled. No independent ground truth exists yet for this dataset.

The calibration run instead used `decision_review.json` via the script's
documented fallback path. That file is fully populated: 100 reviews (76 AGREE,
13 DISAGREE, 11 UNSURE; 55 CLEAN, 45 FINDING by current analyzer decision).
The fallback excludes crystalline-only findings from the texture-specific
groups, per the script's built-in category filter -- 74 of the 100 reviewed
images yielded a usable texture-specific sample (ARTIFACT or CLEAN); the
remainder were excluded as UNCERTAIN/UNSURE or crystalline-only.

**Caveat (carried from the tool's own output):** decision-review-derived labels
are not independent ground truth -- AGREE/DISAGREE was recorded against the
analyzer's current threshold (z >= 1.0), so this evidence is weaker than a true
blind ARTIFACT/CLEAN/UNCERTAIN labeling pass would produce. Treat as first-pass
signal, not a final calibration.

**Samples measured: 74.**

**Threshold sweep (z-score vs. dataset mean/stddev, absolute floor unchanged):**

| z threshold | TP | FP | FN | TN | precision | recall | F1 | FP rate |
|---|---|---|---|---|---|---|---|---|
| 0.5 | 21 | 0 | 9 | 33 | 1.000 | 0.700 | 0.824 | 0.000 |
| 1.0 (current) | 19 | 0 | 11 | 33 | 1.000 | 0.633 | 0.775 | 0.000 |
| 1.5 | 8 | 0 | 22 | 33 | 1.000 | 0.267 | 0.421 | 0.000 |
| 2.0 | 2 | 0 | 28 | 33 | 1.000 | 0.067 | 0.125 | 0.000 |
| 2.5 | 0 | 0 | 30 | 33 | n/a | 0.000 | n/a | 0.000 |
| 3.0 | 0 | 0 | 30 | 33 | n/a | 0.000 | n/a | 0.000 |

**Current threshold (z >= 1.0) summary:**
- TP/FP/FN/TN = 19/0/11/33
- Measured FP rate: 0.000
- Configured FP rate: 0.150 -- **appears conservative** (measured rate is well
  below the hardcoded estimate in `analyzers/texture.py`)
- Confidence cap: 0.700 -- **appears conservative** (measured precision at this
  threshold is 1.000, comfortably above the cap)

**Key observation:** precision is 1.000 at every threshold tested in this
sample -- zero false positives were observed across the full 0.5-3.0 sweep.
Recall falls off sharply as the threshold rises (0.700 at z=0.5 down to 0.000
at z>=2.5), meaning the current z >= 1.0 setting trades recall for a wide
conservative margin against false positives that this sample does not show
any evidence of needing. This is consistent with -- not contradicting -- the
existing hardcoded conservative defaults; it does not yet justify changing
them.

**Status:** First-pass evidence only. No threshold or analyzer changes were
made or are recommended from this evidence alone. Zero observed false
positives on a 74-sample, single-dataset, non-independent-label run is not
sufficient to recalibrate `_Z_MEDIUM`, `_UNCALIBRATED_FP_RATE`, or
`_UNCALIBRATED_MAX_CONFIDENCE` -- it is a data point indicating the current
defaults are not obviously wrong in the conservative direction. A genuine
`label_ground_truth.py` session against this dataset (or a second dataset)
would be required before treating this as calibration evidence strong enough
to act on.

---

## Local Benchmark Private Cases

`benchmarks/local_benchmark_manifest.json` (gitignored) -- 3 private real-sample cases:
- Positive MEDIUM: private_sample_03.jpg (grain=62.4, smooth=36.6)
- Positive LOW: private_sample_02.jpg (grain=50.9, smooth=46.9)
- Negative: private_sample_01.jpg (grain=35.7)
