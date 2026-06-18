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

## Local Benchmark Private Cases

`benchmarks/local_benchmark_manifest.json` (gitignored) -- 3 private real-sample cases:
- Positive MEDIUM: private_sample_03.jpg (grain=62.4, smooth=36.6)
- Positive LOW: private_sample_02.jpg (grain=50.9, smooth=46.9)
- Negative: private_sample_01.jpg (grain=35.7)
