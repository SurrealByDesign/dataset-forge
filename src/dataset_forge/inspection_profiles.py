"""Internal Inspection Profile contract.

Inspection Profiles describe policy overrides for an inspection run. They are
provenance and policy-resolution inputs only; they do not expose user
configuration, profile editing, analyzer toggles, or threshold policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from dataset_forge.analyzer_descriptors import (
    DISPLAY_HIDDEN,
    DISPLAY_VISIBLE,
    EXECUTION_DISABLED,
    EXECUTION_ENABLED,
    TRIAGE_EXCLUDED,
    TRIAGE_INCLUDED,
)


@dataclass(frozen=True)
class AnalyzerPolicyOverride:
    analyzer_id: str
    execution: str | None = None
    display: str | None = None
    triage: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "analyzer_id": self.analyzer_id,
            "execution": self.execution,
            "display": self.display,
            "triage": self.triage,
        }


@dataclass(frozen=True)
class InspectionProfile:
    id: str
    display_name: str
    description: str
    version: str
    analyzer_policy_overrides: tuple[AnalyzerPolicyOverride, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "display_name": self.display_name,
            "description": self.description,
            "version": self.version,
            "analyzer_policy_overrides": [
                override.to_dict()
                for override in self.analyzer_policy_overrides
            ],
        }

    def override_for_analyzer(self, analyzer_id: str) -> AnalyzerPolicyOverride | None:
        for override in self.analyzer_policy_overrides:
            if override.analyzer_id == analyzer_id:
                return override
        return None


DEFAULT_INSPECTION_PROFILE = InspectionProfile(
    id="default",
    display_name="Default Inspection",
    description="Default Dataset Forge inspection profile.",
    version="v1",
    analyzer_policy_overrides=(),
)

BUILT_IN_INSPECTION_PROFILES: tuple[InspectionProfile, ...] = (
    DEFAULT_INSPECTION_PROFILE,
)

_PROFILES_BY_ID: Mapping[str, InspectionProfile] = {
    profile.id: profile
    for profile in BUILT_IN_INSPECTION_PROFILES
}


def built_in_profiles() -> tuple[InspectionProfile, ...]:
    """Return built-in Inspection Profiles in stable order."""

    return BUILT_IN_INSPECTION_PROFILES


def profile_for_id(profile_id: str) -> InspectionProfile | None:
    """Return a built-in Inspection Profile by id, if known."""

    return _PROFILES_BY_ID.get(profile_id)


def validate_analyzer_policy_override(override: AnalyzerPolicyOverride) -> None:
    """Validate optional override policy values."""

    if override.execution is not None and override.execution not in (
        EXECUTION_ENABLED,
        EXECUTION_DISABLED,
    ):
        raise ValueError(f"Unsupported execution override: {override.execution!r}")
    if override.display is not None and override.display not in (
        DISPLAY_VISIBLE,
        DISPLAY_HIDDEN,
    ):
        raise ValueError(f"Unsupported display override: {override.display!r}")
    if override.triage is not None and override.triage not in (
        TRIAGE_INCLUDED,
        TRIAGE_EXCLUDED,
    ):
        raise ValueError(f"Unsupported triage override: {override.triage!r}")


def validate_inspection_profile(profile: InspectionProfile) -> None:
    """Validate profile identity and unique analyzer overrides."""

    if not profile.id:
        raise ValueError("Inspection Profile id is required.")
    seen: set[str] = set()
    for override in profile.analyzer_policy_overrides:
        if override.analyzer_id in seen:
            raise ValueError(
                f"Duplicate analyzer policy override: {override.analyzer_id}"
            )
        seen.add(override.analyzer_id)
        validate_analyzer_policy_override(override)


__all__ = [
    "AnalyzerPolicyOverride",
    "BUILT_IN_INSPECTION_PROFILES",
    "DEFAULT_INSPECTION_PROFILE",
    "InspectionProfile",
    "built_in_profiles",
    "profile_for_id",
    "validate_analyzer_policy_override",
    "validate_inspection_profile",
]
