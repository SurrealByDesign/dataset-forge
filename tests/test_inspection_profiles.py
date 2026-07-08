"""Tests for the internal Inspection Profile contract."""

from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError

from dataset_forge.analyzer_descriptors import (
    DISPLAY_HIDDEN,
    EXECUTION_DISABLED,
    TRIAGE_EXCLUDED,
)
from dataset_forge.inspection_profiles import (
    AnalyzerPolicyOverride,
    DEFAULT_INSPECTION_PROFILE,
    InspectionProfile,
    built_in_profiles,
    profile_for_id,
    validate_analyzer_policy_override,
    validate_inspection_profile,
)


class TestInspectionProfiles(unittest.TestCase):
    def test_default_profile_exists_and_is_deterministic(self) -> None:
        first = DEFAULT_INSPECTION_PROFILE.to_dict()
        second = DEFAULT_INSPECTION_PROFILE.to_dict()

        self.assertEqual(first, second)
        self.assertEqual(
            first,
            {
                "id": "default",
                "display_name": "Default Inspection",
                "description": "Default Dataset Forge inspection profile.",
                "version": "v1",
                "analyzer_policy_overrides": [],
            },
        )

    def test_default_profile_has_no_overrides(self) -> None:
        self.assertEqual(DEFAULT_INSPECTION_PROFILE.analyzer_policy_overrides, ())
        self.assertIsNone(
            DEFAULT_INSPECTION_PROFILE.override_for_analyzer("texture_analyzer")
        )

    def test_default_profile_is_immutable(self) -> None:
        with self.assertRaises(FrozenInstanceError):
            DEFAULT_INSPECTION_PROFILE.id = "changed"  # type: ignore[misc]

    def test_profile_lookup_helpers(self) -> None:
        self.assertEqual(built_in_profiles(), (DEFAULT_INSPECTION_PROFILE,))
        self.assertIs(profile_for_id("default"), DEFAULT_INSPECTION_PROFILE)
        self.assertIsNone(profile_for_id("missing"))

    def test_policy_override_serializes_optional_fields(self) -> None:
        override = AnalyzerPolicyOverride(
            analyzer_id="texture_analyzer",
            execution=EXECUTION_DISABLED,
            display=DISPLAY_HIDDEN,
            triage=TRIAGE_EXCLUDED,
        )

        self.assertEqual(
            override.to_dict(),
            {
                "analyzer_id": "texture_analyzer",
                "execution": "disabled",
                "display": "hidden",
                "triage": "excluded",
            },
        )

    def test_invalid_override_values_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            validate_analyzer_policy_override(
                AnalyzerPolicyOverride("texture_analyzer", execution="maybe")
            )
        with self.assertRaises(ValueError):
            validate_analyzer_policy_override(
                AnalyzerPolicyOverride("texture_analyzer", display="maybe")
            )
        with self.assertRaises(ValueError):
            validate_analyzer_policy_override(
                AnalyzerPolicyOverride("texture_analyzer", triage="maybe")
            )

    def test_duplicate_overrides_are_rejected(self) -> None:
        profile = InspectionProfile(
            id="test",
            display_name="Test",
            description="Test profile.",
            version="v1",
            analyzer_policy_overrides=(
                AnalyzerPolicyOverride("texture_analyzer"),
                AnalyzerPolicyOverride("texture_analyzer"),
            ),
        )

        with self.assertRaises(ValueError):
            validate_inspection_profile(profile)


if __name__ == "__main__":
    unittest.main()
