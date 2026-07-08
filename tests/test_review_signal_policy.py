"""Tests for internal review signal policy resolution."""

from __future__ import annotations

import unittest

from dataset_forge.analyzer_descriptors import (
    DISPLAY_VISIBLE,
    EXECUTION_ENABLED,
    TRIAGE_INCLUDED,
    built_in_descriptors,
)
from dataset_forge.analyzers.registry import create_analyzers
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
            self.assertEqual(resolution.effective_policy.execution, EXECUTION_ENABLED)
            self.assertEqual(resolution.effective_policy.display, DISPLAY_VISIBLE)
            self.assertEqual(resolution.effective_policy.triage, TRIAGE_INCLUDED)
            self.assertEqual(resolution.effective_policy.source, "descriptor_defaults")

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
