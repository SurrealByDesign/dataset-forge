# JSON Schema Guide

Dataset Forge sidecars are local JSON documents identified by a stable `schema`
string. They are not JSON Schema draft documents and do not require an external
schema registry.

## Primary User Sidecars

| File | Schema | Role |
|---|---|---|
| `inspection_report.json` | `dataset-forge/inspection/v1` | Canonical executed findings and evidence. |
| `recommendation_summary.json` | `dataset-forge/recommendation-summary/v1` | Image-centered triage recommendations. |
| `triage_dossiers.json` | `dataset-forge/triage-dossiers/v1` | Detailed triage evidence per image. |
| `inspection_manifest.json` | `dataset-forge/inspection-manifest/v1` | Tool, profile, analyzer, policy, and run provenance. |
| `review_decisions.json` | `dataset-forge/review-decisions/v2` | Human decision, workflow state, and notes. |
| `comparison_summary.json` | `dataset-forge/comparison-summary/v1` | Run differences and manifest compatibility. |
| `improvement_plan.json` | `dataset-forge/improvement-plan/v1` | Advisory improvement planning. |
| `improvement_preview.json` | `dataset-forge/improvement-preview/v1` | Preview-plan records and approval state. |
| `preview_artifacts.json` | `dataset-forge/preview-artifact/v1` | Candidate hashes, references, provider provenance, and warnings. |

## Review Desk Contract

`dataset-forge/review-desk-data/v1` is an internal browser payload computed
from sidecars. It is not persisted. Dataset Intelligence also exists only in
this computed payload.

## Policy Semantics

- Inspection report findings represent executed findings.
- Recommendation Summary remains based on triage-included findings.
- Triage dossiers remain based on triage-included findings.
- Current policies make executed, visible, and triage counts identical, but
  additive semantics fields document the distinction.

## Paths And Artifacts

Source image references are stored as paths because the workstation is local.
Candidate artifact references are relative to the inspect-output workspace and
are verified against recorded SHA-256 hashes before browser serving.

## Compatibility Rules

- Reject unknown required schemas at write boundaries.
- Preserve unknown additive fields where a sidecar update permits it.
- Do not silently rewrite legacy records merely to normalize them for display.
- Sort records and serialization inputs deterministically.
- Comparison should warn about unlike provenance instead of blocking by default.

## Editing Sidecars

Review Desk should be the normal editor for decisions and preview approvals.
Hand editing can create duplicate records, invalid enums, stale summaries, or
broken artifact associations. Keep backups and validate the schema string if
manual editing is unavoidable.

