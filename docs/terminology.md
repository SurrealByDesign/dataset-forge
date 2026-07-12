# Terminology

Use these names consistently in product copy and documentation.

| Preferred term | Meaning | Avoid |
|---|---|---|
| Dataset Forge | The product and Python package. | Generic "cleanup tool" descriptions. |
| Review Desk | The localhost browser interface. | Gallery when referring to the interactive UI. |
| Review Queue | The image grid grouped by triage status. | Cleanup queue or action queue. |
| Finding | One analyzer's advisory evidence record. | Defect unless visually confirmed by a human. |
| Review signal | Human-facing interpretation of a finding. | Automatic judgment. |
| No Findings Emitted | No current analyzer emitted a finding. | Ready for Training, clean, passed. |
| Priority Review | Highest review-order triage group. | Critical failure. |
| Needs Review | At least one current review finding. | Failed. |
| Exclude Candidate | Human decision that an image may not belong in training. | Remove, delete. |
| Set Aside Intent (no files moved) | Workflow metadata only. | Quarantine Planned in visible copy. |
| Decision recorded | A human decision other than `UNDECIDED` is saved. | Reviewed when referring to decision progress. |
| Review Complete | The separate `REVIEWED` workflow stage. | Decision recorded. |
| Improvement Plan | Advisory sidecar describing possible next steps. | Execution plan. |
| Improvement Preview | Planning records and candidate-review workflow. | Image repair or cleanup. |
| Preview plan | One image-centered record in `improvement_preview.json`. | Job or execution request. |
| Candidate preview | Disposable image shown against the original. | Improved image, repaired image. |
| Preview artifact | Isolated candidate bytes plus provenance metadata. | Dataset output. |
| Original source image | The read-only dataset image used as reference. | Input to overwrite. |
| Local Classical Provider | Friendly display name for `LOCAL_CLASSICAL`. | Cleanup provider. |
| Descriptor only | Static metadata with no working integration. | Available or connected. |
| Plan decision | Review metadata for a preview plan without a candidate image. | Permission to execute. |
| Candidate decision | Review metadata for a preview plan with a candidate image. | Permission to execute. |

Machine enums and raw IDs remain unchanged even when the Review Desk uses a
friendlier label.
