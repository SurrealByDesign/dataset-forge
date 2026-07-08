"""Tests for internal review signal policy resolution."""

from __future__ import annotations

import unittest

from dataset_forge.analyzer_descriptors import (
    DISPLAY_HIDDEN,
    DISPLAY_VISIBLE,
    EXECUTION_DISABLED,
    EXECUTION_ENABLED,
    TRIAGE_EXCLUDED,
    TRIAGE_INCLUDED,
    built_in_descriptors,
)
from dataset_forge.analyzers.registry import create_analyzers
from dataset_forge.inspection_profiles import (
    AnalyzerPolicyOverride,
    DEFAULT_INSPECTION_PROFILE,
    InspectionProfile,
)
from dataset_forge.review_signal_policy import (
    ReviewSignalPolicy,
    policy_from_descriptor_defaults,
    resolve_review_signal_policy,
    validate_review_signal_policy,
)


class TestReviewSignalPolicy(unittest.TestCase):
    def test_descriptor_defaults_resolve_deterministically(self) -> None:
        first = [
            resolve_review_signal_policy(descriptor)
            for descriptor in built_in_descriptors()
        ]
        second = [
            resolve_review_signal_policy(descriptor)
            for descriptor in built_in_descriptors()
        ]

        self.assertEqual(first, second)

    def test_current_analyzers_resolve_to_default_policies(self) -> None:
        descriptors = {descriptor.id: descriptor for descriptor in built_in_descriptors()}

        for analyzer in create_analyzers():
            resolution = resolve_review_signal_policy(descriptors[analyzer.name])
            self.assertEqual(resolution.analyzer_id, analyzer.name)
            self.assertEqual(resolution.profile_id, DEFAULT_INSPECTION_PROFILE.id)
            self.assertEqual(resolution.effective_policy.execution, EXECUTION_ENABLED)
            self.assertEqual(resolution.effective_policy.display, DISPLAY_VISIBLE)
            self.assertEqual(resolution.effective_policy.triage, TRIAGE_INCLUDED)
            self.assertEqual(resolution.effective_policy.source, "descriptor_defaults")

    def test_profile_override_changes_effective_policy_only(self) -> None:
        descriptor = built_in_descriptors()[0]
        profile = InspectionProfile(
            id="test_profile",
            display_name="Test Profile",
            description="Test profile override.",
            version="v1",
            analyzer_policy_overrides=(
                AnalyzerPolicyOverride(
                    analyzer_id=descriptor.id,
                    execution=EXECUTION_DISABLED,
                    display=DISPLAY_HIDDEN,
                    triage=TRIAGE_EXCLUDED,
                ),
            ),
        )

        resolution = resolve_review_signal_policy(descriptor, profile=profile)

        self.assertEqual(resolution.profile_id, "test_profile")
        self.assertEqual(resolution.descriptor_defaults.execution, EXECUTION_ENABLED)
        self.assertEqual(resolution.descriptor_defaults.display, DISPLAY_VISIBLE)
        self.assertEqual(resolution.descriptor_defaults.triage, TRIAGE_INCLUDED)
        self.assertEqual(resolution.effective_policy.execution, EXECUTION_DISABLED)
        self.assertEqual(resolution.effective_policy.display, DISPLAY_HIDDEN)
        self.assertEqual(resolution.effective_policy.triage, TRIAGE_EXCLUDED)
        self.assertEqual(
            resolution.effective_policy.source,
            "inspection_profile:test_profile",
        )

    def test_descriptor_default_policy_object_matches_descriptor_fields(self) -> None:
        for descriptor in built_in_descriptors():
            policy = policy_from_descriptor_defaults(descriptor)
            self.assertEqual(policy.execution, descriptor.default_execution_policy)
            self.assertEqual(policy.display, descriptor.default_display_policy)
            self.assertEqual(policy.triage, descriptor.default_triage_policy)

    def test_invalid_policy_values_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            validate_review_signal_policy(
                ReviewSignalPolicy(
                    execution="maybe",
                    display=DISPLAY_VISIBLE,
                    triage=TRIAGE_INCLUDED,
                )
            )
        with self.assertRaises(ValueError):
            validate_review_signal_policy(
                ReviewSignalPolicy(
                    execution=EXECUTION_ENABLED,
                    display="maybe",
                    triage=TRIAGE_INCLUDED,
                )
            )
        with self.assertRaises(ValueError):
            validate_review_signal_policy(
                ReviewSignalPolicy(
                    execution=EXECUTION_ENABLED,
                    display=DISPLAY_VISIBLE,
                    triage="maybe",
                )
            )


if __name__ == "__main__":
    unittest.main()
