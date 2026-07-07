# Dataset Forge -- Current Status

*Last updated: 2026-07-07. Reflects v0.20.0-alpha.*

---

## Release

**Dataset Forge v0.20.0-alpha** implements the inspect-first foundation for a
LoRA Dataset Decision Engine and writes additive Recommendation Summary
sidecars from `dataset-forge inspect`. v0.9 polishes
`recommendation_summary.md` as a human-facing review-order report without
changing recommendation rules or JSON output. v0.10 adds an optional static
`review_gallery.html` generated from existing sidecars. v0.11 adds optional
recommendation contact sheets generated from the same sidecars. v0.12 improves
Markdown and HTML recommendation explainability without changing rules or
schemas. v0.13 adds persistent human review decisions as sidecar state:
`inspect` creates `review_decisions_template.json` when absent, reads
`review_decisions.json` when present, and annotates Markdown/HTML review
outputs without changing recommendations. v0.14 adds an optional local-only
review server so users can record those decisions without hand-editing JSON.
v0.15 adds deterministic comparison between two existing inspect output folders.
v0.16 improves first-time user onboarding, README flow, CLI help wording, and
actionable sidecar error messages without changing behavior or schemas.
v0.17 adds explicit, advisory Improvement Planning from existing sidecars. It
writes `improvement_plan.json` and `improvement_plan.md` only and does not
execute improvements.
v0.18 adds execution-free Improvement Preview from `improvement_plan.json`. It
writes `improvement_preview.json` and `improvement_preview.md` only and marks
execution availability as Not Implemented.
v0.19 adds Real-World Triage Evidence: user-facing No Findings Emitted
language, image-centered recommendation evidence, analyzer coverage summaries,
and image-level triage dossiers. It keeps execution, cleanup, export, repair,
source-image modification, and pixel modification out of scope.
v0.20 adds the Browser-Based Review Desk: `dataset-forge review` now launches a
local, image-centered browser workflow over generated JSON sidecars. It groups
images by Priority Review, Needs Review, and No Findings Emitted; shows nested
finding evidence and analyzer coverage; records v2 human decisions, workflow
state, and notes in `review_decisions.json`; and remains localhost-only,
deterministic, sidecar-based, and non-destructive.

Current public behavior remains inspect-first:

```
Findings -> Aggregation -> Dataset Summary -> Review Queue -> Report
```

Supported in v0.20.0-alpha:
- `dataset-forge inspect <path>` -- full inspect pipeline
- `dataset-forge review <inspect_output>` -- local-only browser Review Desk
- `dataset-forge compare <before_inspect_output> <after_inspect_output>
  --output <comparison_output>` -- sidecar-only comparison between inspect runs
- `dataset-forge plan <inspect_output>` -- advisory Improvement Planning from
  existing sidecars
- `dataset-forge preview <improvement_plan.json>` -- execution-free
  Improvement Preview from an existing plan
- JSON and plain-text reports (`inspection_report.json`, `inspection_report.txt`)
- Recommendation Summary sidecars (`recommendation_summary.json`,
  `recommendation_summary.md`)
- Image-level Triage Dossier sidecars (`triage_dossiers.json`,
  `triage_dossiers.md`)
- Optional static review gallery (`review_gallery.html`) from
  `dataset-forge inspect --review-gallery`
- Optional Recommendation Contact Sheets (`priority_review_contact_sheet.png`,
  `needs_review_contact_sheet.png`) from
  `dataset-forge inspect --contact-sheets`
- Persistent Review Decisions sidecars:
  `review_decisions_template.json` and optional user-authored
  `review_decisions.json`
- Local Review Desk:
  serves existing sidecars from `127.0.0.1` and writes only
  `review_decisions.json`
- Dataset Comparison:
  compares existing `inspection_report.json`, `recommendation_summary.json`,
  and optional `review_decisions.json` sidecars; writes
  `comparison_summary.json` and `comparison_summary.md`
- Improvement Planning:
  consumes existing `inspection_report.json`, `recommendation_summary.json`,
  optional `review_decisions.json`, and optional `comparison_summary.json`;
  writes `improvement_plan.json` and `improvement_plan.md`
- Improvement Preview:
  consumes `improvement_plan.json`, optional `review_decisions.json`, and
  optional `comparison_summary.json`; writes `improvement_preview.json` and
  `improvement_preview.md`
- Optional gallery PNG (`--gallery`)
- Additive Dataset Summary and Review Queue report sections
- Public benchmark suite (committed fixture expectations pass from fresh clone;
  optional generated/private cases are skipped when absent)

- Internal Calibration Evidence over existing `inspection_report.json` files
- Compare existing `inspection_report.json` with schema-versioned ground-truth labels
- Emit per-analyzer and per-category TP/FP/FN/TN, precision, recall, F1, and false-positive rate
- Internal Review Decisions over existing `inspection_report.json` findings
- Load schema-versioned human decisions for images and finding categories
- Summarize Keep, Accepted Style / False Positive, Improvement Candidate,
  Removal Candidate, and Undecided decisions plus workflow state
- Internal Validation Dossiers over existing inspection reports, labels, and optional review decisions
- Emit per-analyzer/per-category reliability summaries, examples, threshold-review candidates, and conservative readiness statuses
- Internal Real-World Validation Corpus framework for legally safe, labeled
  validation datasets
- Validate corpus manifests, label compatibility, committed fixture paths, and
  optional private/local fixture skipping
- Recommendation Summary layer over existing findings only
- Emit schema-versioned No Findings Emitted / Needs Review / Priority Review
  sidecars from `inspect`
- Present `recommendation_summary.md` as a human-facing review report:
  Priority Review first, then Needs Review, with No Findings Emitted summarized
  instead of listed image-by-image
- Show explanation fields in Markdown and HTML review outputs: primary reason,
  finding categories, severity, analyzer names, and finding count
- Show review status in Markdown and HTML outputs when `review_decisions.json`
  exists: Already Reviewed with decision, or Pending Review
- Print concise aggregate recommendation counts after inspect
- No public recommendation command
- No embedding Recommendation Summary into `inspection_report.json`
- No validation or calibration coupling for Recommendation Summary
- No Review Decisions coupling to recommendation rules or JSON schemas
- No analyzer threshold changes
- No improvement execution, cleanup, repair, export, hosted web app, plugins, or new analyzers

Not supported in v0.20.0-alpha (planned for later releases):
- Cleanup (v2+)
- Repair planning (future)
- Improvement execution (future)
- Repair (future)
- Export (future)
- Hosted/remote UI (future)
- Browser editing outside the local `review` command
- Image/pixel comparison
- Detailed review-decision comparison
- Plugin system (v2+)
- Additional analyzers beyond the current first-pass set (v1.x)
- Calibrated thresholds (pending labeled benchmark ground truth)

---

## Test suite

**962 tests passing, 1 skipped.**

The automated suite covers the full inspect pipeline plus internal evidence and
review-decision/validation/corpus helpers.

Covers: Finding, DatasetContext, Analyzer contracts, report writers, CLI,
inspect runner, gallery, benchmark framework, committed fixtures,
post-inspection review guidance, calibration evidence, review decisions, and
validation dossiers, real-world corpus validation, internal recommendation
summaries, and public CLI surface.

```
uv run pytest tests/
```

---

## Implemented (inspect pipeline)

| Component | File | Status |
|---|---|---|
| CLI `inspect` command | `src/dataset_forge/cli.py` | Done |
| Inspect spine runner | `src/dataset_forge/inspect.py` | Done |
| Gallery writer | `src/dataset_forge/inspect_gallery.py` | Done |
| JSON + TXT report writers | `src/dataset_forge/report.py` | Done |
| Dataset Summary + Review Queue | `src/dataset_forge/post_inspection.py` | Advisory post-inspection sections |
| Calibration Evidence | `src/dataset_forge/calibration_evidence.py` | Internal metrics over reports and labels |
| Review Decisions | `src/dataset_forge/review_decisions.py` | Internal human-intent model over images/findings |
| Review Persistence | `src/dataset_forge/review_persistence.py` | Persistent inspect sidecars for human review status |
| Local Review Server | `src/dataset_forge/review_server.py` | Optional localhost UI that writes only `review_decisions.json` |
| Dataset Comparison | `src/dataset_forge/comparison.py` | Sidecar-only comparison between two inspect outputs |
| Validation Dossiers | `src/dataset_forge/validation_dossier.py` | Internal reliability summaries over reports, labels, and review decisions |
| Real-World Validation Corpus | `src/dataset_forge/real_world_corpus.py`; `benchmarks/real_world/` | Internal corpus methodology and manifest validation |
| Recommendation Summary | `src/dataset_forge/recommendation_summary.py` | Additive four-rule sidecar guidance over existing findings |
| Static Review Gallery | `src/dataset_forge/static_review_gallery.py` | Optional read-only HTML surface over inspection and recommendation sidecars |
| Recommendation Contact Sheets | `src/dataset_forge/recommendation_contact_sheets.py` | Optional read-only PNG review aids over inspection and recommendation sidecars |
| `Finding` dataclass | `src/dataset_forge/finding.py` | Done |
| `DatasetContext` dataclass | `src/dataset_forge/context.py` | Done |
| `Analyzer` base class | `src/dataset_forge/analyzers/base.py` | Done |
| `TextureAnalyzer` | `src/dataset_forge/analyzers/texture.py` | First-pass; uncalibrated |
| `CrystallineFacetingAnalyzer` | `src/dataset_forge/analyzers/crystalline.py` | First-pass; uncalibrated |
| `OversharpeningHaloAnalyzer` | `src/dataset_forge/analyzers/oversharpening.py` | First-pass; uncalibrated |
| `HighFrequencyIsolatedArtifactAnalyzer` | `src/dataset_forge/analyzers/high_frequency_isolated.py` | First-pass; uncalibrated |
| Benchmark framework | `src/dataset_forge/benchmark.py` | Done |
| Benchmark manifest | `benchmarks/benchmark_manifest.json` | Committed public fixtures pass; optional generated/private cases skip when absent |

Current finding categories:

- `texture.high_microtexture` for the texture artifact family (`artifact.texture` in planning language)
- `artifact.crystalline_faceting`
- `artifact.oversharpening_halo`
- `artifact.high_frequency_isolated`

---

## Not yet implemented (post-alpha gaps)

| Component | Notes |
|---|---|
| Speck/glitter analyzer calibration | First-pass isolated high-frequency analyzer implemented; synthetic fixtures pass; real-world calibration still pending |
| Oversharpening/halo analyzer calibration | First-pass USM-residual analyzer implemented; synthetic fixtures pass; real-world calibration still pending |
| Periodic frequency analyzer | Researched; not approved for implementation until a better discriminator exists |
| Recursive detail analyzer | Not yet investigated |
| Calibrated thresholds | Pending labeled benchmark ground truth and threshold review for all analyzers |
| Real-world calibration datasets | Pending labeled ground truth beyond synthetic fixtures |

---

## Benchmark fixtures (committed, public)

Thirteen PNG fixtures are committed to `benchmarks/synthetic_defects/`:

| File | Analyzer | Expected result |
|---|---|---|
| `06_crystalline_low.png` | CrystallineFacetingAnalyzer | Fires LOW |
| `07_crystalline_medium.png` | CrystallineFacetingAnalyzer | Fires MEDIUM |
| `08_crystalline_negative_smooth.png` | CrystallineFacetingAnalyzer | No finding (smooth guard) |
| `09_texture_clean.png` | TextureAnalyzer | No finding (below floor) |
| `10_texture_positive.png` | TextureAnalyzer | Fires MEDIUM |
| `11_oversharpen_clean_edge.png` | OversharpeningHaloAnalyzer | No finding (clean hard-edge guard) |
| `12_oversharpen_halo_positive.png` | OversharpeningHaloAnalyzer | Fires MEDIUM |
| `13_oversharpen_texture_guard.png` | OversharpeningHaloAnalyzer | No finding (distributed texture guard) |
| `14_hfi_clean_negative.png` | HighFrequencyIsolatedArtifactAnalyzer | No finding (clean smooth guard) |
| `15_hfi_bright_speck_positive.png` | HighFrequencyIsolatedArtifactAnalyzer | Fires MEDIUM |
| `16_hfi_dark_speck_positive.png` | HighFrequencyIsolatedArtifactAnalyzer | Fires MEDIUM |
| `17_hfi_pencil_grain_guard.png` | HighFrequencyIsolatedArtifactAnalyzer | No finding (paper/pencil grain guard) |
| `18_hfi_edge_halo_guard.png` | HighFrequencyIsolatedArtifactAnalyzer | No finding (edge-adjacent halo guard) |

The committed public fixture expectations run immediately from a fresh clone.
Optional ignored/generated/private fixtures may be present locally and are
skipped automatically when absent.

---

## Scripts

**Public tools** (documented, supported in v0.19.0-alpha):

| Script | Purpose |
|---|---|
| `scripts/run_benchmarks.py` | Run the public benchmark suite |
| `scripts/generate_crystalline_fixtures.py` | Regenerate committed crystalline PNG fixtures |
| `scripts/generate_texture_fixtures.py` | Regenerate committed texture PNG fixtures |
| `scripts/generate_benchmark_defects.py` | Generate private synthetic defect images (requires local reference image) |

**Internal development utilities** (not part of the public API):

Files beginning with `_` (`scripts/_*.py`) are internal calibration, diagnostic,
or development scripts. The following non-prefixed scripts are also internal
calibration utilities, not supported public tools:

`compute_metrics.py`, `crystalline_fp_characterization.py`,
`crystalline_severity_calibration.py`, `diagnostic_report.py`,
`label_ground_truth.py`, `pencil_grain_diagnostic.py`,
`review_decisions.py`, `validation_contact_sheet.py`

**Research probes** (`scripts/research/`):

Artifact-family research probes live in `scripts/research/`. Historical
oversharpening and speck/glitter probes remain in `benchmarks/results/`.

---

## Known limitations

- `texture_analyzer/v1`: z-score thresholds derived from one private dataset.
  Confidence capped at 0.70. FP rate ~15% (estimated).
- `crystalline_faceting_analyzer/v1`: threshold derived from calibration review.
  Confidence capped at 0.45. FP rate ~28% (estimated). Grain 45-55 range has
  significant TP/FP interleaving that requires a fourth discriminating signal.
- `oversharpening_halo_analyzer/v1`: USM-residual rule validated against
  synthetic fixtures only. Confidence capped at 0.45. Real-world precision and
  recall are not yet known.
- `high_frequency_isolated_artifact_analyzer/v1`: residual connected-component
  rule validated against synthetic fixtures only. Confidence capped at 0.45.
  Real-world precision and recall are not yet known.
- Real-World Validation Corpus v1 is methodology only. The committed public
  group uses synthetic placeholder fixtures to validate wiring; it is not
  real-world analyzer reliability evidence. Optional private real-world datasets
  are skipped when absent.
- All first-pass analyzers emit `"calibrated": false` in their evidence dicts.
- Dataset Summary and Review Queue are advisory only. They organize existing
  findings for human review; they do not reject, regenerate, repair, export, or
  modify images.
- Public recommendation sidecars are implemented through `inspect`, but no
  separate public recommendation command exists.
- Recommendation Summary deliberately uses only four rules: analyzer error,
  HIGH/CRITICAL severity, multiple categories, and any other finding. It does
  not read images, run analyzers, generate evidence, use numeric scores, or
  consume Review Decisions, Calibration Evidence, or Validation Dossiers.
  No Findings Emitted means no current findings requiring review were emitted;
  it does not guarantee an image is artifact-free, caption-ready, or suitable
  for LoRA training.
- v0.11 adds optional Recommendation Contact Sheets only. They consume existing
  inspection and recommendation sidecars, record no state, do not create No
  Findings Emitted sheets by default, and do not change recommendation rules,
  `recommendation_summary.json`, inspect schema, analyzer behavior, or CLI
  command surface.
- v0.12 changes presentation only. Recommendation Markdown and Static Review
  Gallery now expose the existing primary reason, finding categories, severity,
  analyzer names, and finding count more clearly. Recommendation rules,
  recommendation JSON, inspect schema, analyzer behavior, contact sheets,
  validation, and review decisions are unchanged.
- v0.13 adds persistent review-decision sidecars only. Inspect creates a
  template when absent, reads existing decisions when present, and annotates
  Markdown/HTML presentation. Recommendation rules, recommendation JSON,
  inspect schema, analyzer behavior, contact sheets, validation, cleanup,
  repair, and export are unchanged.
- v0.14 adds an optional local review server only. It reads existing sidecars,
  serves `127.0.0.1`, writes only `review_decisions.json`, and does not change
  recommendations, reports, analyzers, contact sheets, source images, cleanup,
  repair, or export.
- v0.15 adds sidecar-only dataset comparison. It reads two inspect output
  folders, writes `comparison_summary.json` and `comparison_summary.md`, and
  does not inspect images, rerun analyzers, modify reports, modify review
  decisions, or classify changes as better or worse.
- v0.16 changes documentation and help/error wording only. It does not change
  analyzer behavior, recommendation behavior, report schemas, comparison
  behavior, commands, cleanup, repair, export, or browser features.
- v0.17 adds advisory Improvement Planning only. It does not inspect images,
  rerun analyzers, change recommendations, modify reports, execute
  improvements, clean up, repair, export, or mutate source images.
- v0.18 adds execution-free Improvement Preview only. It does not inspect
  images, process pixels, rerun analyzers, change plans, execute improvements,
  clean up, repair, export, or mutate source images.
- Review Decisions record human intent only. They do not implement cleanup,
  repair, export, rejection, regeneration, or image modification.
- Validation Dossiers assess analyzer reliability only. They do not implement
  repair planning, cleanup, repair, export, rejection, regeneration, or image
  modification.
- The Real-World Validation Corpus organizes validation inputs only. It does
  not implement public validation workflows, repair planning, cleanup, repair,
  export, rejection, regeneration, or image modification.

---

## Next recommended tasks

### v0.20.0-alpha Validation

v0.20 is implemented as Review UX Consolidation, not execution. The remaining
release-readiness task is real-world validation on the anthropomorphic LoRA
dataset:

1. Run `dataset-forge inspect`.
2. Open `dataset-forge review <inspect_output>`.
3. Confirm the Review Desk makes Priority Review, Needs Review, and No Findings
   Emitted images understandable at image-card level.
4. Record sample Keep, Accepted Style / False Positive, Improvement Candidate,
   Removal Candidate, and Undecided decisions.
5. Confirm `review_decisions.json` uses schema
   `dataset-forge/review-decisions/v2`.
6. Confirm comparison, plan, and preview continue to consume the v2 decisions
   without executing or modifying images.

Keep static `review_gallery.html` as a secondary read-only artifact. The local
`dataset-forge review` command is now the primary human decision workflow.

Explicitly out of scope for v0.20:

- deterministic execution
- cleanup execution
- export
- repair
- source-image modification
- pixel modification
- automatic exclude/delete/move/rename decisions
- network dependencies
- cloud service, login, database, or hosted app

---

## Internal notes

Detailed calibration results, private dataset statistics, and probe reports:
`docs/internal_calibration_notes.md`
