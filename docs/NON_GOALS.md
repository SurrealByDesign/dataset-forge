# Dataset Forge — Non-Goals

> **Dataset Forge does not ask "Can this image be changed?"**
> **It asks "Should this image be changed?"**

This document defines what Dataset Forge is not and what it will never become.
It exists to prevent scope creep, architectural drift, and feature pressure
from pulling the project away from its core purpose.

---

## What Dataset Forge Is Not

**Dataset Forge is not a generic image enhancer.**
It does not improve images in the general sense. It reduces specific,
measurable artifacts that are harmful to LoRA training.

**Dataset Forge is not an upscaler.**
Resolution scaling is outside scope. The project does not add pixels,
infer detail, or increase output resolution.

**Dataset Forge is not a beauty filter.**
Images are not processed to look more appealing. An image that looks
slightly rougher but trains better is the correct outcome.

**Dataset Forge is not a LoRA trainer.**
It prepares datasets. It does not invoke training, configure training
parameters, or evaluate trained models directly.

**Dataset Forge is not an image generator.**
No new image content is created. Even the future Semantic Conservator
is a targeted defect-reduction tool, not a generative system.

**Dataset Forge does not aggressively modify artwork for cosmetic reasons.**
Cosmetic improvement is not justification for intervention.
Measurable benefit to LoRA training is the only justification.

**Dataset Forge does not overwrite originals.**
Source images are never modified. All output writes to separate paths.
This constraint is absolute and has no exceptions.

**Dataset Forge does not automatically trust AI edits.**
AI-proposed changes are proposals. They are compared against the original
using the same measurement framework as deterministic cleanup.
Human review is always available. Automatic application is never the default.

**Dataset Forge does not optimize for prettier images.**
It optimizes for better LoRA training data. These goals sometimes conflict.
When they conflict, training data quality wins.

---

## Design Guardrails

These are standing rules for all current and future development.

**Prefer LEAVE_ALONE.**
When routing is ambiguous, the default is preservation, not intervention.
LEAVE_ALONE is a first-class outcome.

**Prefer preservation.**
Any feature that risks damaging existing image quality more than it reduces
training artifacts should not be built.

**Prefer deterministic over AI.**
Deterministic methods are auditable, reproducible, and carry lower risk.
AI methods are reserved for problems that deterministic methods demonstrably
cannot solve.

**Prefer human review over automatic modification.**
Automatic application of changes is the exception, not the rule.
When in doubt, surface the decision to a human.

**Minimize intervention cost.**
Every intervention carries real cost: edge risk, color risk, artifact risk,
processing overhead, review burden. Intervention cost must be justified
by expected benefit. When cost exceeds benefit, do not intervene.

---

## The Line That Should Not Be Crossed

If a proposed feature would cause Dataset Forge to:

- modify images without measurement
- apply changes without comparison to originals
- trust AI output without human oversight
- optimize for visual appeal rather than training quality
- overwrite source files under any circumstances

— that feature is out of scope, regardless of how useful it might seem
in isolation.

---

## Why This Document Exists

LoRA dataset tools tend to accumulate features over time: sharpening filters,
color grading, resolution scaling, style transfer, automatic enhancement.
Each individual addition seems reasonable. Collectively, they transform a
precision instrument into a general-purpose image processor.

Dataset Forge is a precision instrument.

Its value comes from doing a narrow set of things correctly and conservatively,
not from doing everything an image tool might do.

This document is the standing answer to "why don't we just add X?"
