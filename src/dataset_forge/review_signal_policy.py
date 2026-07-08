"""Internal review signal policy resolution.

Policies describe how analyzer signals participate in an inspection run. They
do not change analyzer thresholds, expose user configuration, or implement
Review Profiles.
"""

from __future__ import annotations

from dataclasses import dataclass

from dataset_forge.analyzer_descriptors import (
    DISPLAY_HIDDEN,
    DISPLAY_VISIBLE,
    EXECUTION_DISABLED,
    EXECUTION_ENABLED,
    TRIAGE_EXCLUDED,
    TRIAGE_INCLUDED,
    AnalyzerDescriptor,
)

EXECUTION_POLICIES = (EXECUTION_ENABLED, EXECUTION_DISABLED)
DISPLAY_POLICIES = (DISPLAY_VISIBLE, DISPLAY_HIDDEN)
TRIAGE_POLICIES = (TRIAGE_INCLUDED, TRIAGE_EXCLUDED)


@dataclass(frozen=True)
class ReviewSignalPolicy:
    execution: str
    display: str
    triage: str


@dataclass(frozen=True)
class ResolvedReviewSignalPolicy:
    analyzer_id: str
    policy: ReviewSignalPolicy
    source: str

    @property
    def execution(self) -> str:
        return self.policy.execution

    @property
    def display(self) -> str:
        return self.policy.display

    @property
    def triage(self) -> str:
        return self.policy.triage


@dataclass(frozen=True)
class PolicyResolution:
    analyzer_id: str
    descriptor_defaults: ReviewSignalPolicy
    effective_policy: ResolvedReviewSignalPolicy


def policy_from_descriptor_defaults(
    descriptor: AnalyzerDescriptor,
) -> ReviewSignalPolicy:
    """Return the descriptor default policy as a policy object."""

    policy = ReviewSignalPolicy(
        execution=descriptor.default_execution_policy,
        display=descriptor.default_display_policy,
        triage=descriptor.default_triage_policy,
    )
    validate_review_signal_policy(policy)
    return policy


def resolve_review_signal_policy(
    descriptor: AnalyzerDescriptor,
) -> PolicyResolution:
    """Resolve effective policy for v0.27 from descriptor defaults only."""

    defaults = policy_from_descriptor_defaults(descriptor)
    return PolicyResolution(
        analyzer_id=descriptor.id,
        descriptor_defaults=defaults,
        effective_policy=ResolvedReviewSignalPolicy(
            analyzer_id=descriptor.id,
            policy=defaults,
            source="descriptor_defaults",
        ),
    )


def validate_review_signal_policy(policy: ReviewSignalPolicy) -> None:
    """Validate stable review signal policy values."""

    if policy.execution not in EXECUTION_POLICIES:
        raise ValueError(f"Unsupported execution policy: {policy.execution!r}")
    if policy.display not in DISPLAY_POLICIES:
        raise ValueError(f"Unsupported display policy: {policy.display!r}")
    if policy.triage not in TRIAGE_POLICIES:
        raise ValueError(f"Unsupported triage policy: {policy.triage!r}")


__all__ = [
    "DISPLAY_POLICIES",
    "EXECUTION_POLICIES",
    "PolicyResolution",
    "ResolvedReviewSignalPolicy",
    "ReviewSignalPolicy",
    "TRIAGE_POLICIES",
    "policy_from_descriptor_defaults",
    "resolve_review_signal_policy",
    "validate_review_signal_policy",
]
