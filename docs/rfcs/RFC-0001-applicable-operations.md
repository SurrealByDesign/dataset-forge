# RFC-0001: Applicable Operations

**Status:** Accepted design direction; prototype validation required  
**Target:** Dataset Forge 2.0  
**Implementation authorization:** None  

This RFC is the architectural north star for Applicable Operations. It defines
the current product direction, not an implementation checklist or a commitment
to persisted v2 contracts.

## Context

Dataset Forge currently creates one Improvement Preview record per image with
one `recommended_operation`. Deterministic category precedence selects caption
work before duplicates, duplicates before halo reduction, halo reduction before
encoding reduction, and finally source replacement.

This is deterministic but lossy. Independent findings can justify several
review options, while only the first matching operation remains visible.

Dataset Forge remains evidence-first, advisory, deterministic, sidecar-based,
provider-neutral, source-immutable, human-review-first, and non-executing by
default.

## Problem Statement

An image with caption, halo, and encoding findings may legitimately warrant
manual caption review, a halo-reduction preview, and an encoding-artifact
preview. The current model emits only `MANUAL_CAPTION`, suppressing relevant
evidence and making provider and candidate review artificially exclusive.

## Goals

- Present zero or more evidence-supported operations per image.
- Aggregate findings that support the same operation.
- Give every operation stable internal identity.
- Preserve deterministic ordering and traceability.
- Record operation and candidate decisions separately.
- Keep providers subordinate to human-selected operations.
- Remain usable across very large datasets.
- Normalize v1 data without rewriting it.

## Non-Goals

This RFC does not introduce execution, cleanup, source modification, operation
chains, dependency graphs, combined candidates, automatic provider selection,
provider plugins, bulk approval, bulk generation, quality scores, candidate
histories, path-independent image identity, Review Sessions, or a browser
framework migration.

## Terminology

| Term | Meaning |
|---|---|
| Image decision | Existing human disposition such as Keep, Accepted Style, Improvement Candidate, or Exclude Candidate. |
| Image Plan | The planning record for one image. |
| Applicable Operation | An evidence-supported option presented for human consideration. |
| Operation type | Readable stable value such as `REDUCE_HALO`. |
| Plan operation ID | Internal identifier joining one image and operation type. |
| Operation decision | Whether the reviewer wants to explore or skip an applicable operation. |
| Candidate availability | Whether an isolated candidate exists for that operation. |
| Candidate decision | Human acceptance or rejection of that candidate as a planning artifact. |
| Workflow stage | Independent review-workflow metadata; it is not a decision. |

`KEEP`, `NO_ACTION`, Accepted Style, and Exclude Candidate are decisions or
dispositions, not operations.

## Current Architecture

The single-operation assumption exists in:

- `improvement_preview.py`: `_operation_from_categories()` returns one
  first-match result.
- Improvement Preview v1: one operation, rationale, provider, status, and
  approval state per image.
- Preview summaries and Markdown: one operation count and rendered operation
  per record.
- `preview_provider_contract.py`: `PreviewRequest.planned_operation` represents
  one request.
- `preview_artifacts.py`: artifact identity includes one recommended operation
  and allows one artifact per plan record.
- `local_classical_preview.py`: image lookup resolves one record and operation.
- CLI: `preview-import` and `preview-generate` select an image but not an
  operation.
- `review_desk.py`: derives one provider match and candidate association per
  image plan.
- `review_server.py`: approval updates are keyed by image path and the browser
  renders one operation panel.
- Tests and documentation: assume one operation, provider, status, decision,
  and artifact per image.

Provider descriptors already advertise multiple supported operation types and
need only narrow request-level evolution.

## Proposed Conceptual Model

```text
Image Plan
├── image decision
├── workflow stage
├── current findings
└── applicable operations
    ├── operation A
    │   ├── triggering findings
    │   ├── operation decision
    │   └── optional candidate and candidate decision
    └── operation B
        ├── triggering findings
        ├── operation decision
        └── optional candidate and candidate decision
```

Conceptual operation record:

```json
{
  "plan_operation_id": "plan-operation-...",
  "operation_type": "REDUCE_HALO",
  "display_label": "Reduce Halo",
  "rationale": "Halo evidence supports reviewing a conservative preview.",
  "triggering_findings": [],
  "confidence": 0.55,
  "required_provider_type": "LOCAL_CLASSICAL",
  "required_capabilities": [],
  "operation_decision": "UNDECIDED",
  "candidate_availability": "ABSENT",
  "candidate_decision": null
}
```

Every operation type appears at most once per image. Supporting findings
aggregate beneath it.

## Identity Model

| Option | Assessment |
|---|---|
| `operation_id` | Too easily confused with the readable operation type. |
| `operation_record_id` | Accurate but unnecessarily generic. |
| `plan_operation_id` | Clearly identifies one operation within an Image Plan. |
| `operation_key` | Sounds transient or implementation-specific. |
| `image_plan_id` plus operation type | Conceptually sufficient but awkward for joins and artifact references. |

Use three distinct concepts:

- `image_plan_id`: internal identity for the image plan.
- `operation_type`: readable machine value used by people and CLI.
- `plan_operation_id`: opaque internal join identity.

The conceptual derivation is:

```text
plan_operation_id = hash(contract namespace, image_plan_id, operation_type)
```

It must not include findings, rationale, confidence, provider choice, priority,
or candidate state. Changing those details must not silently orphan artifacts.
Path-independent image identity remains a separate problem.

## Applicability And Priority

Applicability means evidence supports showing an operation. Priority means only
deterministic presentation order.

Do not expose numeric priority as primary UI language. Use **Suggested first**,
**Also applicable**, and **Additional option**.

Priority should be derived, not stored as an independent mutable number. A
future persisted planning contract should record its planner-contract version
and serialize operations in derived order.

Suggested initial ordering:

1. Unresolved operations with an available unreviewed candidate.
2. Unresolved visual candidate-producing operations.
3. Unresolved dataset-structure or source-disposition operations.
4. Unresolved metadata or manual operations.
5. Resolved operations.
6. Highest triggering severity.
7. Highest evidence confidence.
8. Operation type as stable tie-breaker.

This order requires prototype validation. It must never imply execution order,
quality rank, required correction, urgency, or certainty. `REPLACE_SOURCE`
remains a fallback only when no specific operation applies.

## Decision-State Model

Presence in `applicable_operations` means the operation is applicable. No extra
applicability state is required.

Recommended operation decision states are `UNDECIDED`, `EXPLORE`, and `SKIP`.
Recommended candidate availability is `ABSENT` or `AVAILABLE`. Recommended
candidate decisions are `UNREVIEWED`, `ACCEPTED`, and `REJECTED`.

User-facing language should be **Explore operation**, **Skip operation**,
**Accept candidate**, and **Reject candidate**. Accepting a candidate records
planning preference only. It does not apply, export, replace, or execute
anything.

Avoid a generic `approval_state`; it overloads plan acceptance and candidate
acceptance. Avoid using Reviewed or Complete for decisions.

## Review Desk UX

The image grid remains the primary workspace. Selecting an image reveals:

```text
Image details and evidence

Applicable Operations (3)

[Suggested first] Reduce Halo
  Halo evidence supports reviewing a conservative preview.
  Findings: Oversharpening / Edge Halo
  Provider: Local Classical
  Candidate: Available
  Operation decision: Explore
  Candidate decision: Not reviewed
  [A/B comparison]

[Also applicable] Reduce Encoding Artifacts
  Collapsed summary...

[Additional option] Manual Caption Review
  Collapsed summary...
```

The first unresolved operation expands by default. Other operations remain
collapsed and keyboard reachable. Only the selected operation displays full
evidence and A/B comparison. Raw operation and provider IDs remain secondary
technical metadata.

## Scenario Behavior

| Scenario | Behavior |
|---|---|
| Zero operations | Show “No applicable operation from current evidence.” Preserve findings and image decision. |
| One operation | Expand it automatically. |
| Two unrelated operations | Expand the first unresolved and retain the second compactly. |
| Several operations | Show compact rows and one expanded detail region. |
| Metadata plus visual operation | Keep both; visual work must not be hidden by caption findings. |
| No compatible provider | Keep the operation reviewable and say no candidate path is currently available. |
| Multiple operations with candidates | Each operation owns its candidate; comparison follows the selected operation. |
| Accepted candidate plus unresolved operation | The image still has unresolved operation work. |

## Large-Dataset Behavior

Use the smallest scalable interaction model:

- `N` moves to the next image containing any unresolved review item.
- Selecting that image expands its first unresolved operation.
- Dedicated previous/next-operation controls move within the selected image.
- No operation-specific queue is added.
- No full evidence dossiers render for every collapsed operation.
- Compact labels such as Visual, Structure, or Metadata may aid scanning; they
  are not queues.

An image is unresolved when its image decision is undecided, any operation
decision is undecided, or any available candidate is unreviewed.

Summary counts must distinguish images with applicable operations, total
applicable operations, unresolved operation decisions, and candidates awaiting
review. Operation aggregation replaces precedence-based suppression so caption
findings cannot hide visual work.

## Provider And CLI Implications

A provider receives exactly one operation request at a time. Providers do not
determine applicability, reorder operations, choose the best operation, or
compose operations.

The existing singular `PreviewRequest` remains directionally correct. Minimum
conceptual additions are `plan_operation_id`, selected `operation_type`,
explicit parameters, and provider and provenance requirements.

Preferred CLI form:

```text
dataset-forge preview-generate <output> <image> --operation REDUCE_HALO
```

Users select readable operation types, never opaque plan-operation IDs. If
exactly one compatible candidate-producing operation exists, omission of
`--operation` may resolve it automatically. If several exist, omission fails
deterministically and lists valid operation types.

Unknown operations, inapplicable operations, ambiguous image references, and
operations without a compatible provider must produce distinct errors. Manual
import uses the same readable selector. No batch selection is introduced.

## Artifact Evolution

Do not change persisted artifacts during the prototype phase.

| Option | Assessment |
|---|---|
| Continue adapting v1 artifacts | Appropriate for prototype and legacy reads only. |
| Extend v1 records additively | Misleading because uniqueness changes from plan-level to operation-level. |
| Introduce `preview-artifact/v2` | Cleanest long-term choice if operation-linked artifacts prove necessary. |

Persistence should eventually support one active candidate per operation and
several operations per image. Candidate history and multiple-provider galleries
remain excluded.

Move to artifact persistence only after operation identity, regeneration,
replacement, source-hash validation, and rollback behavior are proven in
memory.

## Backward Compatibility

A read-only v1 adapter should normalize:

- A normal singular operation into one applicable operation.
- `KEEP` and `NO_ACTION` into an empty active operation list with preserved
  legacy context.
- V1 plan approval into an explicitly labeled ambiguous legacy decision when
  no candidate association clarifies it.
- V1 candidate approval into candidate decision only when a verified artifact
  is joined.
- Manual and LOCAL_CLASSICAL artifacts into the synthetic v1 operation.
- `preview_entries` identically to `preview_records`.
- Unknown additive fields into preserved legacy metadata for diagnostics.

Never rewrite v1 sidecars silently. Never dual-write v1 and v2. Never invent
certainty when legacy approval meaning is ambiguous.

Inspection reports, recommendations, manifests, and review decisions can
remain compatible. Improvement Preview planning, per-operation state, and
operation-linked artifacts require the 2.0 boundary.

## Dependencies And Composition

Initial operations are independent options. `REDUCE_HALO` and
`REDUCE_ENCODING_ARTIFACTS` produce separate candidates and are not chained.
No generic dependencies, exclusions, composition, or graph fields are
included.

Composition should be reconsidered only after repeated user demand, validated
order-sensitive operations, clear provenance requirements, and evidence that
separate candidates cannot support the workflow.

## Review Sessions

Applicable Operations does not require a Review Session layer. Filters,
selected image, UI preferences, reviewer identity, and bookmarks are session
concerns, not operation-contract requirements. Adding sessions now would expand
state and migration complexity without solving applicability. Review Sessions
are explicitly deferred.

## Prototype Plan

Phase A is an isolated, non-persisting prototype:

1. Define pure in-memory Image Plan and Applicable Operation contracts.
2. Normalize v1 records and artifacts in memory.
3. Replace first-match planning with operation accumulation.
4. Render a temporary Review Desk operation list.
5. Exercise CLI selection through pure resolution functions and tests.
6. Test datasets with zero through five operations per image.
7. Leave v1 writers, artifacts, and production behavior untouched.

## Prototype Success Metrics

- Caption operations no longer hide visual operations.
- Duplicate operation types never appear for one image.
- Reviewers understand why every operation appears.
- At least 80% of testers distinguish operation decisions from candidate
  decisions without assistance.
- At least 80% select the intended operation using readable types.
- Median applicable-operation count remains at or below three.
- Images with three to five operations remain usable without showing all
  evidence simultaneously.
- Legacy fixtures normalize without crashes, silent loss, or hidden ambiguity.
- No provider is allowed to select or reorder operations.

These are adoption gates, not claims of statistical significance.

## User-Validation Plan

Ask testers:

- Did you expect more than one operation for this image?
- Were any operations redundant?
- Did Suggested first feel sensible without sounding mandatory?
- Could you distinguish exploring an operation from accepting a candidate?
- Which operation did you expect to generate first?
- Did caption work obscure visual work?
- Was the list manageable during sustained review?
- At what operation count did the panel become burdensome?
- Did an operation without a provider still feel useful?
- Did Next Undecided take you where expected?

Validate across several dataset types and reviewer workflows. One tester's
preferred order must not become universal policy.

## Risks

- Operation accumulation may replace hidden evidence with excessive noise.
- More decision units increase cognitive and persistence complexity.
- Unstable identity could orphan or misassociate candidates.
- Legacy approval semantics may remain ambiguous.
- Counts may confuse images with operations.
- Derived priority may appear prescriptive.
- Regeneration may invalidate candidate provenance.
- UI density may become unacceptable above three to five operations.
- Dormant graph concepts would pull Dataset Forge toward execution architecture.

## Open Questions

- Should visual operations always appear before metadata operations?
- Should an Improvement Candidate image decision be required before operations
  become active?
- What confidence aggregation best represents several supporting findings?
- When should an accepted candidate stop contributing to unresolved-image
  status?
- Should manually imported candidates require an operation type that normally
  produces no image?
- What evidence proves path-dependent image identity is no longer sufficient?
- What maximum operation count should trigger consolidation or wording changes?

## Adoption Criteria

Persisted v2 contracts should proceed only when:

- The in-memory model passes deterministic contract tests.
- Legacy normalization exposes ambiguity rather than guessing.
- External users understand operation and candidate decisions.
- Real datasets demonstrate multiple useful independent operations.
- Operation lists remain manageable at realistic scale.
- Stable operation identity survives evidence-detail changes.
- CLI ambiguity behavior is predictable.
- Candidate joins and source provenance are demonstrably safe.
- No v1 production behavior must change to run the prototype.

## Recommendation

Dataset Forge 2.0 should adopt Applicable Operations if the prototype validates
the interaction model.

The smallest sound model is one Image Plan containing zero or more uniquely
typed operations, each with `plan_operation_id`, `operation_type`, aggregated
triggering findings, derived presentation priority, provider requirements,
operation decision, and optional candidate decision.

Priority should be derived from a versioned planner contract and serialized
through deterministic array order, not persisted as a user-visible numeric
score. Artifact schema changes should follow, not precede, in-memory prototype
and planning-contract validation.

Operation decisions answer whether an option is worth exploring. Candidate
decisions answer whether a specific isolated result is acceptable for planning.
Neither authorizes execution.

CLI selection should use readable operation types and reject ambiguity
deterministically. A Review Session layer is not required and remains deferred.

## Phased Implementation Outline

**Phase A:** Pure contracts, v1 normalization, accumulating planner, temporary
Review Desk prototype, and CLI resolution tests. No writers.

**Phase B:** After validation, define and write a versioned v2 Improvement
Preview planning contract. Keep v1 read-only compatibility.

**Phase C:** After artifact-association validation, introduce the least
misleading operation-linked artifact contract, likely `preview-artifact/v2`.

**Phase D:** Make v2 the 2.0 default only after migration, rollback,
source-safety, deterministic rendering, and real-user validation pass.

