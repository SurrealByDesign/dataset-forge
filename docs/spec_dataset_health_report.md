# Spec: Dataset Health Report

> **Historical design record. Superseded by descriptive Dataset Intelligence.**
> Quality scores, readiness labels, cleanup summaries, and export guidance in
> this document are not part of Dataset Forge v1.9.3.

**Status:** Specification — not yet implemented.

**Pipeline position:** After texture analysis and Decision Engine evaluation,
before export.

**Primary question answered:**
> "If I trained a LoRA on this dataset today, how confident should I feel
> that the dataset itself is well prepared?"

---

## Governing Philosophy

The report favors preservation over intervention. A dataset where 80% of images
are already excellent should be celebrated, not aggressively optimized. Doing
nothing is often the correct decision. The goal is not to maximize cleanup. The
goal is to maximize LoRA quality while minimizing unnecessary intervention.

The report must never suggest processing simply because a metric exists. It
must recognize and say out loud when restraint is the right call.

---

## Position in the Existing Architecture

This report is a new aggregation layer over data that already exists. It does
not replace any existing component.

```
Analyze (texture.py, quality.py)
  ↓
Evidence (evidence.py)
  ↓
recommend_evidence() — unchanged, authoritative for existing callers
  ↓
evaluate_decision() — additive engine layer (decisions.py)
  ↓
Dataset Health Report  ← new, reads from all of the above
  ↓
LoRA Export Prep (spec_lora_export_prep.md)
```

Input to the health report is a `list[TextureImageResult]` and the
corresponding `TextureReportSummary`. The report reads all existing fields
including the four `engine_*` fields. It does not re-run analysis and does not
call cleanup operations.

---

## Output Files

Every run writes three files to the report output folder:

| File | Purpose |
|---|---|
| `dataset_health_report.json` | Machine-readable, full detail |
| `dataset_health_report.html` | Human-readable dashboard |
| `dataset_health_report.txt` | Plain-text executive summary (terminal-friendly) |

Existing files (`texture_report.*`, `evidence.json`, CSV) are untouched.

---

## Section 1 — Executive Summary

### Fields

| Field | Type | Description |
|---|---|---|
| `total_images` | int | All images passed to analysis |
| `analyzed_images` | int | Successfully analyzed (status == "analyzed") |
| `error_images` | int | Failed to open or analyze |
| `skipped_images` | int | Explicitly excluded by user or engine |
| `dataset_health_score` | float 0–100 | See computation below |
| `lora_readiness_score` | float 0–100 | See computation below |
| `headline` | str | One-sentence summary |
| `recommendations` | list[str] | Ordered actionable recommendations |

### Example output (plain text)

```
Dataset Health: 94/100
Estimated LoRA Readiness: 96/100

Recommendation:
  Dataset is well prepared.
  Run deterministic cleanup on 25 images.
  No AI conservation currently recommended.
  Ready for training after export.
```

The "Estimated LoRA Readiness" label must always be accompanied by a note that
it is a heuristic intended to guide preparation, not predict actual model
performance.

---

## Section 2 — Decision Engine Summary

### Fields

| Field | Type |
|---|---|
| `leave_alone_count` | int |
| `leave_alone_pct` | float |
| `deterministic_only_count` | int |
| `deterministic_only_pct` | float |
| `ai_conservation_count` | int |
| `ai_conservation_pct` | float |
| `manual_review_count` | int |
| `manual_review_pct` | float |
| `intervention_ratio` | float | fraction of images requiring any action |
| `high_confidence_decisions` | int | engine_confidence >= 80 |
| `low_confidence_decisions` | int | engine_confidence < 60 |

### Intervention ratio visualization (text)

```
51%  Leave alone      ████████████████████████████████░░░░░░░░░░░░░░░░░░
25%  Deterministic    ████████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
18%  AI candidate     █████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
 6%  Manual review    ███░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
```

A low intervention ratio (LEAVE_ALONE > 50%) should be reported as a positive
signal, not a neutral one. A dataset that mostly needs to be left alone is a
well-composed dataset.

---

## Section 3 — Cleanup Summary

This section is only populated if deterministic cleanup has been run. If no
cleanup has been executed, the section reports "Cleanup not yet applied" and
shows the projected metrics from Decision Engine routing.

### Fields (post-cleanup)

| Field | Type | Description |
|---|---|---|
| `images_cleaned` | int | |
| `images_rejected` | int | Exceeded acceptance thresholds; original kept |
| `images_unchanged` | int | LEAVE_ALONE route, never submitted to cleanup |
| `average_pixel_difference` | float | Mean `avg_pixel_diff` across cleaned images |
| `average_edge_preservation` | float | 1 − mean edge_diff |
| `average_color_preservation` | float | 1 − mean hist_diff |
| `average_microtexture_reduction` | float | Mean (before − after) microtexture_density_score |
| `average_intervention_cost` | float | Mean Intervention Cost score (0–100) |
| `profile_used` | str | Name of the cleanup profile applied |
| `profile_version` | str | e.g. "V1" |

### Fields (pre-cleanup / projected)

| Field | Type | Description |
|---|---|---|
| `projected_images_to_clean` | int | engine DETERMINISTIC_ONLY count |
| `projected_ai_candidates` | int | engine AI_CONSERVATION_CANDIDATE count |
| `projected_manual_review` | int | engine MANUAL_REVIEW count |

The emphasis in this section is on how little change occurred. Lead with
preservation metrics, not change metrics.

---

## Section 4 — Dataset Statistics

All statistics computed from `TextureImageResult` and `TextureReportSummary`
fields that already exist.

### Texture statistics

| Field | Source |
|---|---|
| `average_microtexture` | `TextureReportSummary.average_microtexture_density` |
| `median_microtexture` | computed from `[item.microtexture_density_score for item in analyzed]` |
| `stddev_microtexture` | `TextureReportSummary.microtexture_standard_deviation` |
| `texture_variance` | stddev² |
| `reference_baseline` | from `cleanup_rules.json` `decision_engine.reference_baseline_microtexture` (26.86) |
| `gap_from_reference` | average − reference_baseline |
| `above_average_outlier_count` | `len(TextureReportSummary.above_average_outliers)` |
| `below_average_outlier_count` | `len(TextureReportSummary.below_average_outliers)` |

### Resolution statistics

Computed from per-image `original_path` metadata (PIL image size, loaded during
analysis or stored in evidence). If resolution data is not present in the current
run (texture analysis does not record it), mark as "not available in this run"
and note that a quality analysis pass would populate this.

| Field | Description |
|---|---|
| `resolution_distribution` | histogram buckets: <512px, 512–1024px, >1024px (longest edge) |
| `aspect_ratio_distribution` | histogram: portrait, landscape, near-square (ratio within 0.1 of 1.0) |
| `min_resolution` | smallest image (longest edge) |
| `max_resolution` | largest image (longest edge) |

### Duplicate statistics

| Field | Source |
|---|---|
| `exact_duplicate_count` | from `build_dataset_report` / manifest if available; else 0 with note |
| `near_duplicate_count` | same |

### Future extension points (present but empty in V1)

```json
{
  "caption_completeness": null,
  "caption_consistency": null,
  "prompt_consistency": null
}
```

These keys must be present in `dataset_health_report.json` with `null` values
so downstream consumers can check for them without branching on key existence.

---

## Section 5 — Consistency Scores

Six heuristic 0–100 scores. All are explicitly labeled as descriptive
indicators, not scientific measurements.

### Computation

**Texture consistency (0–100)**

```
mean(item.texture_consistency_score for item in analyzed)
```

Direct reuse of the per-image `texture_consistency_score` already computed by
`evaluate_texture()`. No new computation.

**Resolution consistency (0–100)**

```
100 × exp(−coefficient_of_variation(longest_edge))
```

where `coefficient_of_variation = stddev / mean`. Score of 100 means all images
are the same resolution. Requires resolution data; if absent, returns `null`.

**Aspect ratio consistency (0–100)**

```
pct_in_dominant_bucket × 100
```

where dominant bucket is the most common of {portrait, landscape, near-square}.
A dataset where 90% of images share an aspect ratio category scores 90. If
absent, returns `null`.

**Style consistency (0–100)**

Heuristic based on spread of `watercolor_smoothness_score` and
`microtexture_density_score`:

```
100 × exp(−(cv_smoothness + cv_microtexture) / 2)
```

where `cv = stddev / mean` for each metric. High score means the dataset has
consistent visual style. Low score means wide stylistic spread.

**Cleanup consistency (0–100)**

```
100 × (1 − intervention_ratio)  ×  mean(engine_confidence / 100 for non-LEAVE_ALONE)
```

High score: engine is confident its decisions are correct AND most images need
no intervention. Penalizes both high intervention rates and low-confidence
decisions. Returns 100 if all images are LEAVE_ALONE.

**Overall dataset consistency (0–100)**

Weighted mean of available consistency scores:

```
0.35 × texture_consistency
0.25 × style_consistency
0.20 × resolution_consistency   (or texture if resolution unavailable)
0.20 × cleanup_consistency
```

If resolution_consistency is null, its weight is redistributed to texture_consistency.

---

## Section 6 — Estimated LoRA Readiness Score

A single heuristic 0–100 score. Must always be labeled "Estimated" and must
always include the disclaimer: "This score is an estimate intended to guide
preparation decisions. It does not predict actual model performance."

### Formula

Start at 100. Apply penalties. Clamp to [0, 100]. Round to nearest integer.

**Reward signals (reduce penalties when present)**

| Signal | Effect |
|---|---|
| LEAVE_ALONE rate > 50% | −0 (no penalty added for the good images) |
| engine_confidence mean > 80 | Reduces uncertainty penalty by half |
| Overall dataset consistency > 80 | Reduces variance penalty by 25% |

**Penalties**

| Condition | Penalty |
|---|---|
| Each MANUAL_REVIEW image | −0.5 per image, max −15 total |
| Each AI_CONSERVATION_CANDIDATE | −0.3 per image, max −10 total |
| Intervention ratio > 60% | −10 |
| Intervention ratio > 80% | −20 (replaces above) |
| Texture stddev > 15 | −5 |
| Texture stddev > 25 | −10 (replaces above) |
| Gap from reference baseline > 20 | −5 |
| Gap from reference baseline > 30 | −10 (replaces above) |
| Exact duplicates present | −3 per duplicate pair, max −15 |
| Near duplicates present | −1 per near-duplicate pair, max −8 |
| Resolution inconsistency score < 60 | −5 |
| Aspect ratio inconsistency (< 60% in dominant bucket) | −5 |
| Error images > 5% of total | −5 |
| Error images > 15% of total | −15 (replaces above) |
| Average microtexture > 50 (above ceiling of V1) | −8 |

**Example scoring for ANTHROPOMORPHS dataset:**

```
Base: 100
− 12.0   (24 MANUAL_REVIEW × 0.5)
−  0.0   (0 AI candidates)
−  0.0   (intervention ratio 49% — under 60% threshold)
−  0.0   (stddev 11.62 — under 15)
−  5.0   (gap from reference: 38.59 − 26.86 = +11.73 — between 10 and 20)
−  0.0   (no duplicates in current run)
−  0.0   (resolution data not available this run)
−  0.0   (no errors)
−  0.0   (average microtexture 38.59 — under 50)
= 83 estimated LoRA readiness
```

Scores above 85 should be accompanied by a positive headline. Scores below 60
should be accompanied by a specific list of what is pulling the score down.

---

## Section 7 — Human-Readable Recommendations

A prioritized list of plain-English action items generated from the data. Each
recommendation is one or two sentences. The list is ordered by expected impact
(highest first).

### Generation rules

Recommendations are evaluated in this order and included only when their
condition is met:

1. **Positive statement** (always first if warranted):
   - If LEAVE_ALONE ≥ 50%: "N images are already excellent training examples and should not be modified."
   - If overall consistency > 80: "The dataset already demonstrates strong stylistic consistency."

2. **Critical issues** (errors, duplicates):
   - If error_images > 0: "N images could not be analyzed and should be reviewed manually."
   - If exact_duplicate_count > 0: "Remove N exact duplicate images before training."
   - If near_duplicate_count > 0: "Review N near-duplicate pairs — similar images reduce training diversity."

3. **Deterministic cleanup** (if DETERMINISTIC_ONLY > 0):
   - "Run deterministic cleanup on N images. Expected benefit: speck removal and mild texture reduction."
   - If cleanup has already been run: "Deterministic cleanup applied to N images. All N accepted by preservation checks."

4. **AI conservation** (if AI_CONSERVATION_CANDIDATE > 0):
   - "N images are AI conservation candidates. These have recursive microfacet structure that deterministic cleanup cannot resolve."
   - If no AI backend: "No AI conservation backend is configured. N images are held in manual review."

5. **Manual review** (if MANUAL_REVIEW > 0):
   - "N images require manual review." + most common reason.
   - If all manual review is due to microtexture: "These images have texture complexity beyond the current deterministic ceiling and are candidates for the AI Conservator phase."

6. **Resolution guidance** (if resolution data available):
   - If resolution_consistency < 60: "Resolution normalization recommended — significant variation across the dataset."
   - If aspect_ratio_consistency < 60: "Aspect ratio normalization recommended before export."

7. **Restraint statement** (always last if cleanup is low):
   - If intervention_ratio < 30%: "The expected benefit of further cleanup is low. The dataset is close to ready as-is."
   - If average_intervention_cost available and < 5.0: "Average intervention cost is minimal. V1 cleanup is safe to apply."

8. **Export readiness**:
   - "Ready for LoRA export after applying the actions above." or "Ready for LoRA export now." if no actions.

---

## Section 8 — Export Guidance

A projection of the export plan based on Decision Engine routing. This is
informational — it does not trigger export.

```
Export Recommendation
─────────────────────
Leave unchanged:          51  (51%)
Deterministic cleanup:    25  (25%)
AI conservation:           0   (0%)
Manual review:            24  (24%)

Recommended training set after optimization: 100 images
```

If duplicates are known, the recommendation may adjust:
```
After removing 2 duplicate pairs: 98 images recommended for export.
```

---

## Section 9 — Future Extension Points

The following sections are defined in the JSON schema with `null` or empty
values in V1. Their keys must be present so consumers do not need to guard
against missing keys.

```json
{
  "ai_conservator_statistics": null,
  "caption_quality": null,
  "prompt_consistency": null,
  "lora_validation_results": null,
  "training_history": null,
  "style_clustering": null,
  "outlier_detection": null
}
```

These become populated sections when the corresponding features are implemented.
The surrounding report structure (executive summary, consistency scores, export
guidance) does not change shape when new sections are added.

---

## Implementation Location

| Component | Path |
|---|---|
| `DatasetHealthReport` dataclass | `src/dataset_forge/analysis/health.py` (new file) |
| `DatasetHealthSummary` dataclass | same |
| `generate_health_report()` function | same |
| `_compute_health_score()` | same (private) |
| `_compute_readiness_score()` | same (private) |
| `_compute_consistency_scores()` | same (private) |
| `_generate_recommendations()` | same (private) |
| HTML renderer | same or `src/dataset_forge/analysis/health_html.py` if large |
| CLI subcommand | `src/dataset_forge/cli.py` — `health-report` |
| Tests | `tests/analysis/test_health.py` |

The existing `reporting.py` and `quality.py` are not modified. The health report
reads their outputs as inputs but does not replace them.

---

## `generate_health_report()` Signature

```python
def generate_health_report(
    results: list[TextureImageResult],
    summary: TextureReportSummary,
    output_path: Path,
    *,
    cleanup_execution_report: dict | None = None,
    duplicate_count: int = 0,
    near_duplicate_count: int = 0,
    rules: dict | None = None,
) -> DatasetHealthReport:
    ...
```

- `results` and `summary` come directly from `generate_texture_report()`.
- `cleanup_execution_report` is the output of a cleanup run, if one has been
  performed. When `None`, the Cleanup Summary section is projected rather than
  measured.
- `duplicate_count` and `near_duplicate_count` come from the existing
  `build_dataset_report()` / manifest pipeline.
- `rules` is the raw dict from `cleanup_rules.json`; when `None`, defaults apply.

---

## `dataset_health_report.json` Schema (abbreviated)

```json
{
  "version": 1,
  "generated_at": "2026-06-16T...",
  "executive_summary": {
    "total_images": 100,
    "analyzed_images": 100,
    "error_images": 0,
    "skipped_images": 0,
    "dataset_health_score": 87.4,
    "lora_readiness_score": 83,
    "headline": "Dataset is well prepared.",
    "recommendations": ["..."]
  },
  "decision_engine_summary": {
    "leave_alone_count": 51,
    "leave_alone_pct": 51.0,
    "deterministic_only_count": 25,
    "deterministic_only_pct": 25.0,
    "ai_conservation_count": 0,
    "ai_conservation_pct": 0.0,
    "manual_review_count": 24,
    "manual_review_pct": 24.0,
    "intervention_ratio": 0.49,
    "high_confidence_decisions": 62,
    "low_confidence_decisions": 27
  },
  "cleanup_summary": {
    "status": "not_applied",
    "projected_images_to_clean": 25,
    "projected_ai_candidates": 0,
    "projected_manual_review": 24
  },
  "dataset_statistics": {
    "texture": {
      "average_microtexture": 38.59,
      "median_microtexture": 37.7,
      "stddev_microtexture": 11.62,
      "texture_variance": 135.02,
      "reference_baseline": 26.86,
      "gap_from_reference": 11.73,
      "above_average_outlier_count": 19,
      "below_average_outlier_count": 18
    },
    "resolution": null,
    "duplicates": {
      "exact_duplicate_count": 0,
      "near_duplicate_count": 0
    },
    "future": {
      "caption_completeness": null,
      "caption_consistency": null,
      "prompt_consistency": null
    }
  },
  "consistency_scores": {
    "texture_consistency": 68.4,
    "resolution_consistency": null,
    "aspect_ratio_consistency": null,
    "style_consistency": 71.2,
    "cleanup_consistency": 84.7,
    "overall_dataset_consistency": 74.8
  },
  "lora_readiness": {
    "score": 83,
    "disclaimer": "Estimated. Does not predict actual model performance.",
    "penalty_breakdown": {
      "manual_review_penalty": -12.0,
      "gap_from_reference_penalty": -5.0,
      "total_penalty": -17.0
    }
  },
  "export_guidance": {
    "leave_unchanged": 51,
    "deterministic_cleanup": 25,
    "ai_conservation": 0,
    "manual_review": 24,
    "recommended_training_set_size": 100
  },
  "future_sections": {
    "ai_conservator_statistics": null,
    "caption_quality": null,
    "prompt_consistency": null,
    "lora_validation_results": null,
    "training_history": null,
    "style_clustering": null,
    "outlier_detection": null
  }
}
```

---

## HTML Dashboard Layout

The HTML report uses the same dark-theme design language as the existing
`texture_report.html`. Layout is a single scrollable page with a sticky
header showing the two headline scores.

```
┌─────────────────────────────────────────────────────┐
│  Dataset Forge — Dataset Health Report              │ ← sticky header
│  Health: 87/100    LoRA Readiness: 83/100           │
└─────────────────────────────────────────────────────┘

┌──────────────────┐ ┌──────────────────────────────┐
│ Executive        │ │ Decision Engine Summary       │
│ Summary          │ │ ████████░░░░ 51% Leave alone  │
│                  │ │ ████░░░░░░░░ 25% Deterministic│
│ 100 images       │ │ ░░░░░░░░░░░░  0% AI candidate │
│ 100 analyzed     │ │ ███░░░░░░░░░ 24% Manual review│
│ 0 errors         │ └──────────────────────────────┘
│                  │
│ Recommendations: │ ┌──────────────────────────────┐
│ • 51 images …    │ │ Consistency Scores            │
│ • Run cleanup…   │ │ Texture consistency:    68    │
│ • Review 24…     │ │ Style consistency:      71    │
│ • Ready after…   │ │ Cleanup consistency:    85    │
└──────────────────┘ │ Overall:                75    │
                     └──────────────────────────────┘

┌──────────────────────────────────────────────────────┐
│ Dataset Statistics                                   │
│ Avg microtexture: 38.6   Reference baseline: 26.9   │
│ Std deviation:    11.6   Gap from reference: +11.7  │
│ Above-avg outliers: 19   Below-avg outliers: 18     │
└──────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────┐
│ Cleanup Summary                                      │
│ Cleanup not yet applied.                            │
│ Projected: 25 images for deterministic cleanup.     │
└──────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────┐
│ Export Guidance                                      │
│ Leave unchanged:     51   Deterministic: 25         │
│ AI conservation:      0   Manual review: 24         │
│ Recommended training set: 100 images                │
└──────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────┐
│ Estimated LoRA Readiness: 83/100                    │
│ This score is an estimate intended to guide         │
│ preparation decisions. It does not predict actual   │
│ model performance.                                  │
│                                                     │
│ Score breakdown:                                    │
│   Manual review penalty:       −12.0               │
│   Gap from reference penalty:   −5.0               │
│   Total penalty:               −17.0               │
└──────────────────────────────────────────────────────┘
```

---

## Acceptance Criteria

An implementation passes when:

1. `dataset_health_report.json`, `.html`, and `.txt` are all written to the
   output folder.
2. The JSON file is valid and matches the schema above, with all future-section
   keys present as `null`.
3. The `lora_readiness_score` is always accompanied by the disclaimer string in
   both JSON and HTML.
4. No source images are read, written, or modified by the health report.
5. The health report can be generated from `generate_texture_report()` output
   alone (without a cleanup execution report). The cleanup section correctly
   reports "not applied" and shows projections.
6. Running the health report twice on the same input produces identical output
   (deterministic).
7. If all 100 images are LEAVE_ALONE, the report correctly outputs a positive
   headline and does not manufacture intervention suggestions.
8. The `overall_dataset_consistency` score degrades gracefully when
   `resolution_consistency` is null (redistributes weight, does not crash).
9. The HTML report renders in a modern browser without external network
   requests (fully offline).

---

## Open Questions (resolve before implementation)

1. **`dataset_health_score` formula.** The existing `HealthSummary.dataset_health_score`
   from `quality.py` is already computed and available. Should the health report
   reuse it directly, or derive its own? Recommendation: reuse existing score
   when available, derive a texture-aware variant when quality analysis has not
   been run.

2. **Resolution data availability.** The texture analysis path does not currently
   record per-image pixel dimensions. Should `generate_health_report()` re-open
   each image to measure it, or should resolution stats wait until the quality
   analysis path (`assess_dataset_quality()`) has been run first? Recommendation:
   resolution stats are optional; if not available, display "Run quality analysis
   to include resolution statistics."

3. **Integration with the CLI pipeline order.** The health report is specified
   to run after Decision Engine evaluation and before export. Should it run
   automatically as part of `dataset-forge texture-report`, or be a separate
   `dataset-forge health-report` command? Recommendation: separate command for
   now; `texture-report` output feeds into it explicitly.

4. **Cleanup execution report format.** The `cleanup_execution_report` parameter
   is a raw dict. Should this be a typed dataclass? Recommendation: yes —
   define `CleanupExecutionSummary` in `src/dataset_forge/cleanup/summary.py`
   before implementing the health report, so the integration is typed.

5. **`dataset_health_score` vs `lora_readiness_score`.** The two scores serve
   different purposes: health reflects dataset completeness and correctness;
   readiness reflects how much preparation work remains. They should be allowed
   to diverge. A dataset with high health but many MANUAL_REVIEW images has
   high health, lower readiness. Document the distinction clearly in the report.
