# Dataset Forge -- CLI Output Specification

This file defines what success looks like for the public command-line
experience.

The CLI should answer a new user's first questions quickly:

- What should I run first?
- Where were the reports written?
- Which file should I open first?
- Were my source images changed?

Dataset Forge should use user workflow language before architecture language.

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

Images with findings:        19 / 100
Images with no findings:     81 / 100

Recommendation: 81 images are Ready for Training.
                19 images deserve human review before training.

Recommendation Summary
----------------------
  Ready for Training: 81
  Needs Review:       16
  Priority Review:    3

Recommendations are advisory and based only on existing findings.
Source images were not modified.

Reports written:
  inspection_report.json
  inspection_report.txt
  recommendation_summary.json
  recommendation_summary.md
  review_decisions_template.json
  review_gallery.html  # only with --review-gallery
  priority_review_contact_sheet.png  # only with --contact-sheets
  needs_review_contact_sheet.png     # only with --contact-sheets
```

---

## Review Command

```
dataset-forge review path/to/dataset/inspect_output/
```

Expected terminal output:

```
Dataset Forge Review
====================
Inspect output: path/to/dataset/inspect_output
Serving:        http://127.0.0.1:8765
Writes only:    review_decisions.json
Source images and reports will not be modified.
Press Ctrl+C to stop.
```

The local review server:

- binds only to `127.0.0.1`
- reads `inspection_report.json`, `recommendation_summary.json`, and optional
  `review_decisions.json`
- writes only `review_decisions.json`
- does not modify source images, inspection reports, recommendation summaries,
  static galleries, or contact sheets
- does not change recommendation rules or analyzer behavior

---

## Compare Command

```
dataset-forge compare path/to/before/inspect_output/ path/to/after/inspect_output/ --output path/to/comparison/
```

Expected terminal output:

```
Dataset Forge Compare
=====================
Before: path/to/before/inspect_output
After:  path/to/after/inspect_output
Output: path/to/comparison

Comparison written:
  comparison_summary.json
  comparison_summary.md
```

The comparison command:

- reads `inspection_report.json`, `recommendation_summary.json`, and optional
  `review_decisions.json` from each inspect output folder
- writes only `comparison_summary.json` and `comparison_summary.md`
- validates sidecar schemas before comparison
- does not inspect images, compare pixels, rerun analyzers, modify existing
  reports, modify recommendations, or modify review decisions
- does not classify changes as better or worse

`comparison_summary.md` is ordered for human review:

1. Dataset Summary
2. Images With Changed Recommendations
3. Images With New Findings
4. Images With Resolved Findings
5. Recommendation Count Changes
6. Finding Category Changes
7. Analyzer Output Changes

`comparison_summary.json` uses schema
`dataset-forge/comparison-summary/v1`.

---

## Plan Command

```
dataset-forge plan path/to/dataset/inspect_output/
```

Expected terminal output:

```
Dataset Forge Plan
==================
Inspect output: path/to/dataset/inspect_output
Output:         path/to/dataset/inspect_output

Improvement Plan written:
  improvement_plan.json
  improvement_plan.md

Improvement Planning is advisory and planning-only.
Source images and existing sidecars were not modified.
```

The plan command:

- reads `inspection_report.json`, `recommendation_summary.json`, optional
  `review_decisions.json`, and optional `comparison_summary.json`
- writes only `improvement_plan.json` and `improvement_plan.md`
- validates sidecar schemas before planning
- maps existing findings to abstract Suggested Improvements only
- respects human review decisions
- does not inspect images, rerun analyzers, modify reports, modify
  recommendations, modify review decisions, execute improvements, or modify
  source images

`improvement_plan.json` uses schema
`dataset-forge/improvement-plan/v1`.

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
- shows most common finding categories
- shows Priority Review and Needs Review image cards
- summarizes Ready for Training images without listing every image
- explains each review card with recommendation label, primary reason, finding
  categories, severity, analyzer names, and finding count
- includes advisory wording that recommendations are review priorities, source
  images were not modified, and Ready for Training is not a guarantee of
  artifact-free images
- does not add buttons, checkboxes, forms, scripts, review-decision editing,
  cleanup, repair, export, or server behavior

The JSON sidecars remain the source of truth.

---

## Recommendation Contact Sheets

When `dataset-forge inspect path/to/dataset/ --contact-sheets` is used, inspect
writes recommendation-oriented PNG contact sheets alongside the existing
inspection and recommendation sidecars:

- `priority_review_contact_sheet.png`
- `needs_review_contact_sheet.png`

The contact sheets:

- are generated from `inspection_report.json` and `recommendation_summary.json`
- use Recommendation Summary ordering
- show image thumbnail, filename, recommendation label, and primary reason or
  finding category
- use fixed thumbnail sizing and plain labels
- write deterministic empty-state sheets when Priority Review or Needs Review
  groups are empty
- do not create Ready for Training sheets by default
- show at most the first 100 images per sheet
- do not rerun analyzers, recompute recommendations, write thumbnails beside
  source images, edit review decisions, cleanup, repair, export, web app, or
  server behavior

The JSON sidecars remain the source of truth.

---

## Recommendation Markdown Structure

`recommendation_summary.md` is a plain Markdown review report:

```
# Dataset Recommendation Summary

## Dataset Summary

- Images inspected: 100
- Ready for Training: 81
- Needs Review: 16
- Priority Review: 3
- Most common finding categories:
  - artifact.high_frequency_isolated: 6

# Recommended Review Order

## Priority Review

### artifact.high_frequency_isolated

---

#### image_023.png

Recommendation:
Priority Review

Review Status:
Already Reviewed

Decision:
Acceptable Style

Primary reason:
High-severity finding detected.

Finding categories:
- artifact.high_frequency_isolated

Analyzer:
- high_frequency_isolated_artifact_analyzer/v1

Severity:
HIGH

Finding count:
1

## Needs Review

### artifact.oversharpening_halo

---

#### image_041.png

Recommendation:
Needs Review

Review Status:
Pending Review

Decision:
None recorded

Primary reason:
Measurable finding detected.

Finding categories:
- artifact.oversharpening_halo

Analyzer:
- oversharpening_halo_analyzer/v1

Severity:
MEDIUM

Finding count:
1

# Ready for Training

81 images emitted no current findings requiring review.

# Important Notes

Ready for Training means Dataset Forge emitted no current findings requiring
review.

Recommendations are based only on current deterministic findings.

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

Each Priority Review and Needs Review item explains why it appears in the
review order using existing finding references only: primary reason, finding
categories, severity, analyzer names, and finding count. It does not add
scores, confidence tiers, validation coupling, or new recommendation logic.

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
