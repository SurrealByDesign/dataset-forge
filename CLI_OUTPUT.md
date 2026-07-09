# Dataset Forge -- CLI Output Specification

The public command-line experience should make the read-only workflow obvious.

The CLI should quickly answer:

- What happened?
- Where were outputs written?
- What should I open first?
- Where are human decisions saved?
- Were source images changed?

---

## Public Commands

The public v1.x surface is:

```text
dataset-forge inspect <dataset>
dataset-forge review <inspect_output>
dataset-forge compare <before> <after> --output <comparison_output>
dataset-forge plan <inspect_output>
dataset-forge preview <improvement_plan.json>
dataset-forge --help
dataset-forge --version
```

Cleanup, export, execution, repair, profile selection, analyzer toggles,
plugins, cloud features, databases, and image modification are not public
v1.x commands.

---

## Inspect Success Output

Expected shape:

```text
Dataset Forge Inspect
=====================
Dataset:  path/to/dataset
Output:   path/to/dataset/inspect_output

Images:   100
Analyzed: 100
Errors:   0

Summary
-------
Total findings:  19
  HIGH severity:  2
  MEDIUM severity: 11
  LOW severity:   6

Images with findings:        15 / 100
No Findings Emitted:         85 / 100

85 images emitted no current review findings.
15 images have findings. Review report for details.

Recommendation Summary
----------------------
  No Findings Emitted: 85
  Needs Review:        13
  Priority Review:     2

Recommendations are advisory and based only on existing findings.
Execution, cleanup, export, and source-image modification are out of scope.
Source images were not modified.

Report written:
  path/to/dataset/inspect_output/inspection_report.json
  path/to/dataset/inspect_output/inspection_report.txt
  path/to/dataset/inspect_output/recommendation_summary.json
  path/to/dataset/inspect_output/recommendation_summary.md
  path/to/dataset/inspect_output/triage_dossiers.json
  path/to/dataset/inspect_output/triage_dossiers.md
  path/to/dataset/inspect_output/inspection_manifest.json
  path/to/dataset/inspect_output/review_decisions_template.json

Start Here
----------
Review Desk: dataset-forge review "path/to/dataset/inspect_output"
Output dir:   path/to/dataset/inspect_output
Decisions:    review_decisions.json

Open first:
  triage_dossiers.md
  recommendation_summary.md
  inspection_report.json
```

`No Findings Emitted` must not be described as training-ready, clean, approved,
artifact-free, or guaranteed safe for training.

---

## Review Command Output

Expected shape:

```text
Dataset Forge Review Desk
=========================
Inspect output: path/to/dataset/inspect_output
Serving:        http://127.0.0.1:8765
Writes only:    review_decisions.json
Consumes only:  generated JSON sidecars
Source images and reports will not be modified.
Press Ctrl+C to stop.
```

The Review Desk must communicate that it:

- serves localhost only
- consumes generated sidecars
- writes only `review_decisions.json`
- does not run analyzers
- does not modify source images or reports
- does not move files or create quarantine folders
- does not clean, repair, export, or execute improvements
- does not produce a quality score or readiness score

---

## Compare / Plan / Preview Wording

Comparison is advisory and sidecar-only. It should not imply that one run is
better or worse unless the sidecars themselves directly say so.

Improvement Planning is advisory and planning-only. It writes plan sidecars; it
does not execute changes.

Improvement Preview is execution-free. It explains plan entries; it does not
process images, modify files, or trigger cleanup.

---

## Analyzer Trust Wording

Findings should be described as advisory review signals. Confidence and
severity should not be presented as certainty.

Known false-positive contexts that may need human judgment:

- JPEG compression, ringing, mosquito noise, chroma artifacts, or banding
- low-resolution JPEG/compression artifacts
- natural paper, pencil, watercolor, canvas, or scan grain
- engraving or etched illustration texture
- intentional highlights, glitter, stars, freckles, or decorative specks
- hard-edge line art, ink outlines, or crisp transitions
- mixed-media and intentionally rough texture

Image Encoding Analyzer findings are advisory source-context signals. JPEG
presence alone is not a finding, and high-quality JPEGs should not be flagged
only because they are JPEG files. Encoding evidence may explain texture, halo,
crystalline, or high-frequency findings, but Dataset Forge does not repair,
denoise, upscale, clean, exclude, export, move, or modify images.

Exact duplicate detection is advisory and limited to byte-identical and
decoded pixel-identical images; it does not detect perceptual near-duplicates.

---

## Release Checks

Before a v1.x release, run:

```text
python -m pytest tests/test_cli_surface.py -q
python -m pytest tests/test_review_server.py -q
python -m pytest -q
git diff --check
```

Also confirm source image hashes are unchanged after inspect, review, compare,
plan, and preview smoke tests.
