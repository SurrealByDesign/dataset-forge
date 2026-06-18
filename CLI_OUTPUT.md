# Dataset Forge -- CLI Output Specification

This file defines what success looks like.
The implementation should move toward producing this output.

---

## Command

```
dataset-forge inspect path/to/dataset/
```

---

## Expected Terminal Output

```
Dataset Forge Inspect
=====================
Dataset:    path/to/dataset/
Images:     100
Analyzed:   100
Errors:     0

Building dataset context...
  Resolution:      512x512 -- 1024x1536  (mean 768x1024)
  Aspect ratios:   portrait 72%  square 18%  landscape 10%
  Microtexture:    mean=39.9  stddev=11.6  p10=24.1  p90=55.2
  Frequency:       baseline established (100 images)
  Duplicates:      0 exact  2 near-duplicate pairs flagged

Running analyzers...
  [glitter]      100/100  12 findings
  [frequency]    100/100   7 findings
  [sharpness]    100/100   4 findings
  [texture]      100/100   0 findings  (all within dataset baseline)

Summary
-------
Total findings:     23
  HIGH severity:     3
  MEDIUM severity:  14
  LOW severity:      6

Images with findings:   19 / 100
Images with no issues:  81 / 100

Recommendation: 81 images require no action.
                19 images have calibrated findings. Review report for details.

Report written:
  inspection_report.json
  inspection_report.txt
```

---

## JSON Report Structure

```json
{
  "schema": "dataset-forge/inspection/v1",
  "generated_at": "2026-06-16T14:23:00Z",
  "dataset_path": "path/to/dataset",
  "context": {
    "total_images": 100,
    "analyzed_images": 100,
    "error_images": 0,
    "resolution_stats": { "min_w": 512, "max_w": 1024, "mean_w": 768, "stddev_w": 112 },
    "texture_distributions": { "mean": 39.9, "stddev": 11.6, "p10": 24.1, "p90": 55.2 },
    "duplicate_hashes": [],
    "near_duplicate_pairs": [["image_014.png", "image_087.png"]]
  },
  "findings": [
    {
      "image_path": "image_023.png",
      "analyzer": "glitter_analyzer/v1",
      "category": "artifact.glitter",
      "severity": "HIGH",
      "confidence": 0.91,
      "false_positive_rate": 0.04,
      "benchmark_version": "synthetic_glitter_v1",
      "evidence": {
        "glitter_pixel_ratio": 0.034,
        "peak_brightness_delta": 87,
        "spatial_frequency_score": 0.71
      },
      "explanation": "3.4% of pixels show isolated high-brightness speckle consistent with GPT glitter artifacts. Spatial frequency analysis confirms non-organic distribution.",
      "recommendation": "Candidate for speck removal. Estimated intervention cost: low."
    }
  ],
  "summary": {
    "total_findings": 23,
    "images_with_findings": 19,
    "images_clean": 81,
    "severity_counts": { "HIGH": 3, "MEDIUM": 14, "LOW": 6, "NONE": 0 }
  }
}
```

---

## TXT Report Structure

```
Dataset Forge Inspection Report
================================
Generated:  2026-06-16 14:23:00
Dataset:    path/to/dataset/
Images:     100 analyzed, 0 errors

FINDINGS BY IMAGE
-----------------

image_023.png
  [HIGH] artifact.glitter  --  confidence 0.91 (FP rate ~4%)
  Benchmark: synthetic_glitter_v1
  Evidence: glitter_pixel_ratio=0.034, peak_brightness_delta=87
  Why: 3.4% of pixels show isolated high-brightness speckle consistent
       with GPT glitter artifacts.
  Action: Candidate for speck removal. Estimated cost: low.

image_041.png
  [MEDIUM] artifact.periodic_noise  --  confidence 0.77 (FP rate ~8%)
  ...

CLEAN IMAGES (no findings)
--------------------------
81 images produced no findings at any severity level.
These images are ready for training as-is.

SUMMARY
-------
Findings:         23 total (3 HIGH, 14 MEDIUM, 6 LOW)
Images affected:  19 / 100
Images clean:     81 / 100

Recommendation: Run `dataset-forge clean --from-report inspection_report.json`
                to apply deterministic fixes to flagged images (future feature).
```

---

## Design Notes

- The "clean" images section is not a fallback  --  it is a primary result.
- Every finding includes the benchmark that calibrated its threshold.
- Confidence and false-positive rate are always shown together.
- The report never says "fix everything." It explains each finding.
- A report with 100 clean images and 0 findings is a successful run.
