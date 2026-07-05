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
  [texture]                    100/100   8 findings
  [crystalline_faceting]        100/100   6 findings
  [oversharpening_halo]         100/100   3 findings
  [high_frequency_isolated]     100/100   6 findings

Summary
-------
Total findings:     23
  HIGH severity:     3
  MEDIUM severity:  14
  LOW severity:      6

Images with findings:   19 / 100
Images with no issues:  81 / 100

Recommendation: 81 images require no action.
                19 images have findings. Review report for details.

Recommendation Summary
----------------------
  Ready for Training: 81
  Needs Review:       16
  Priority Review:    3

Recommendations are advisory and based only on existing findings.
Source images were not modified.

Report written:
  inspection_report.json
  inspection_report.txt
  recommendation_summary.json
  recommendation_summary.md
  review_gallery.html  # only with --review-gallery
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
    "near_duplicate_pairs": [["image_014.png", "image_087.png"]],
    "analyzer_versions": {
      "texture_analyzer": "v1",
      "crystalline_faceting_analyzer": "v1",
      "oversharpening_halo_analyzer": "v1",
      "high_frequency_isolated_artifact_analyzer": "v1"
    }
  },
  "findings": [
    {
      "image_path": "image_023.png",
      "analyzer": "high_frequency_isolated_artifact_analyzer/v1",
      "category": "artifact.high_frequency_isolated",
      "severity": "MEDIUM",
      "confidence": 0.42,
      "false_positive_rate": 0.40,
      "benchmark_version": "uncalibrated",
      "evidence": {
        "isolated_component_count": 22,
        "component_density_per_megapixel": 335.69,
        "median_component_residual": 81.1,
        "edge_adjacent_component_ratio": 0.14,
        "calibrated": false
      },
      "explanation": "Small isolated high-frequency residual components were detected above the local background.",
      "recommendation": "Candidate for human review. Leave the image alone if these marks are intentional highlights or decorative details."
    }
  ],
  "summary": {
    "total_findings": 23,
    "images_with_findings": 19,
    "images_clean": 81,
    "severity_counts": { "HIGH": 3, "MEDIUM": 14, "LOW": 6, "NONE": 0 }
  },
  "dataset_summary": {
    "schema": "dataset-forge/dataset-summary/v1",
    "image_count": 100,
    "images_with_findings": 19,
    "images_without_findings": 81,
    "findings_by_category": {
      "artifact.high_frequency_isolated": 6
    },
    "findings_by_severity": {
      "HIGH": 3,
      "MEDIUM": 14,
      "LOW": 6
    },
    "analyzer_error_count": 0,
    "calibrated_finding_count": 0,
    "uncalibrated_finding_count": 23,
    "dominant_artifact_families": [
      "artifact.high_frequency_isolated"
    ]
  },
  "review_queue": {
    "schema": "dataset-forge/review-queue/v1",
    "outcomes": {
      "no_attention_needed": 81,
      "review_recommended": 16,
      "priority_review": 3
    },
    "items": []
  }
}
```

`inspection_report.json` does not embed Recommendation Summary. The sidecar
`recommendation_summary.json` is reproducible from the Inspection Report alone.

---

## Recommendation Summary Structure

```json
{
  "schema": "dataset-forge/recommendation-summary/v1",
  "source_report_schema": "dataset-forge/inspection/v1",
  "summary": {
    "image_count": 100,
    "ready_for_training_count": 81,
    "needs_review_count": 16,
    "priority_review_count": 3,
    "analyzer_error_count": 0
  },
  "recommendations": [
    {
      "image_path": "image_023.png",
      "recommendation": "PRIORITY_REVIEW",
      "display_label": "Priority Review",
      "primary_reason": "High-severity finding detected.",
      "reason_codes": ["finding.high_severity"],
      "finding_refs": [
        {
          "analyzer": "high_frequency_isolated_artifact_analyzer/v1",
          "category": "artifact.high_frequency_isolated",
          "severity": "HIGH"
        }
      ],
      "guidance": "Review this image early before deciding whether to include it in training.",
      "confidence_note": "Recommendations are advisory and based only on existing findings. Uncalibrated analyzers are review signals, not final judgments."
    }
  ]
}
```

The sidecar must not contain numeric quality scores or serialized priority
fields. Ready for Training means Dataset Forge emitted no current findings
requiring review. It does not guarantee the image is artifact-free.

---

## Static Review Gallery

When `dataset-forge inspect path/to/dataset/ --review-gallery` is used, inspect
writes `review_gallery.html` alongside the existing inspection and
recommendation sidecars.

The static gallery:

- is generated from `inspection_report.json` and `recommendation_summary.json`
- shows Recommendation Summary counts
- shows Priority Review and Needs Review image cards
- summarizes Ready for Training images without listing every image
- includes advisory wording that recommendations are review priorities, source
  images were not modified, and Ready for Training is not a guarantee of
  artifact-free images
- does not add buttons, checkboxes, forms, scripts, review decisions, cleanup,
  repair, export, or server behavior

The JSON sidecars remain the source of truth.

---

## Recommendation Markdown Structure

`recommendation_summary.md` is a plain Markdown review report:

```
# Dataset Recommendation Summary

- Images inspected: 100
- Ready for Training: 81
- Needs Review: 16
- Priority Review: 3

# Recommended Review Order

## Priority Review

### artifact.high_frequency_isolated

- Filename: `image_023.png`
  - Recommendation: Priority Review
  - Primary reason: High-severity finding detected.
  - Finding references: artifact.high_frequency_isolated from high_frequency_isolated_artifact_analyzer/v1 (HIGH)

## Needs Review

### artifact.oversharpening_halo

- Filename: `image_041.png`
  - Recommendation: Needs Review
  - Primary reason: Measurable finding detected.
  - Finding references: artifact.oversharpening_halo from oversharpening_halo_analyzer/v1 (MEDIUM)

# Ready for Training

81 images emitted no current findings requiring review.

# Important Notes

Ready for Training means Dataset Forge emitted no current findings requiring
review.

It does not guarantee the image is artifact-free.

Recommendations are advisory.

Dataset Forge never modifies source images.

# Next Step

Review Priority Review images first.

Then review Needs Review images if appropriate.

After review, decide whether each image belongs in your training dataset.
```

The Markdown report does not list every Ready for Training image. It is a review
order document, not a gallery or an action system.

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
  [MEDIUM] artifact.high_frequency_isolated  --  confidence 0.42 (FP rate ~40%)
  Benchmark: uncalibrated
  Evidence: isolated_component_count=22, component_density_per_megapixel=335.69
  Why: Small isolated high-frequency residual components were detected above
       the local background.
  Action: Candidate for human review. Leave the image alone if these marks are
          intentional highlights or decorative details.

image_041.png
  [MEDIUM] artifact.oversharpening_halo  --  confidence 0.45 (FP rate ~35%)
  ...

CLEAN IMAGES (no findings)
--------------------------
81 images produced no findings at any severity level.
These images are ready for training as-is.

DATASET SUMMARY
---------------
Images with findings:       19
Images without findings:    81
Analyzer errors:            0
Calibrated findings:        0
Uncalibrated findings:      23
Dominant artifact families: artifact.high_frequency_isolated

REVIEW QUEUE
------------
Review Queue is advisory only. Dataset Forge does not delete, modify,
repair, reject, regenerate, or export images.
No attention needed: 81
Review recommended:  16
Priority review:     3

SUMMARY
-------
Findings:         23 total (3 HIGH, 14 MEDIUM, 6 LOW)
Images affected:  19 / 100
Images clean:     81 / 100

Recommendation: Review findings before making any dataset changes.
                Dataset Forge inspect is read-only and does not modify images.
```

---

## Design Notes

- The "clean" images section is not a fallback  --  it is a primary result.
- Every finding includes its benchmark status. `uncalibrated` means synthetic
  fixtures may validate the rule shape, but real-world calibration is pending.
- Confidence and false-positive rate are always shown together.
- The report never says "fix everything." It explains each finding.
- A report with 100 clean images and 0 findings is a successful run.
- Dataset Summary and Review Queue are additive report sections. They organize
  existing findings for human review and do not hide or replace findings.
- Recommendation Summary sidecars are additive outputs. They organize existing
  findings into Ready for Training, Needs Review, and Priority Review groups
  without changing `inspection_report.json`.
