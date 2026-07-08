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
from dataset_forge.inspection_profiles import (
    DEFAULT_INSPECTION_PROFILE,
    InspectionProfile,
    validate_inspection_profile,
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
    profile_id: str
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
    *,
    profile: InspectionProfile = DEFAULT_INSPECTION_PROFILE,
) -> PolicyResolution:
    """Resolve effective policy from descriptor defaults and profile overrides."""

    defaults = policy_from_descriptor_defaults(descriptor)
    validate_inspection_profile(profile)
    override = profile.override_for_analyzer(descriptor.id)
    effective = defaults
    source = "descriptor_defaults"
    if override is not None:
        effective = ReviewSignalPolicy(
            execution=override.execution or defaults.execution,
            display=override.display or defaults.display,
            triage=override.triage or defaults.triage,
        )
        validate_review_signal_policy(effective)
        source = f"inspection_profile:{profile.id}"
    return PolicyResolution(
        analyzer_id=descriptor.id,
        descriptor_defaults=defaults,
        profile_id=profile.id,
        effective_policy=ResolvedReviewSignalPolicy(
            analyzer_id=descriptor.id,
            policy=effective,
            source=source,
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
