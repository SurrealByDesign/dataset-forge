from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


class CleanupAction(str, Enum):
    KEEP = "KEEP"
    CLEAN_LIGHT = "CLEAN_LIGHT"
    CLEAN_MEDIUM = "CLEAN_MEDIUM"
    CLEAN_STRONG = "CLEAN_STRONG"
    TEXTURE_NORMALIZE_LIGHT = "TEXTURE_NORMALIZE_LIGHT"
    TEXTURE_NORMALIZE_MEDIUM = "TEXTURE_NORMALIZE_MEDIUM"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    DUPLICATE_REVIEW = "DUPLICATE_REVIEW"
    EXCLUDE = "EXCLUDE"
    REGENERATE = "REGENERATE"
    CAPTION_ONLY = "CAPTION_ONLY"


@dataclass(frozen=True)
class CleanupDecision:
    image_id: str
    filename: str
    action: CleanupAction
    confidence: int
    explanation: str
    expected_benefit: str
    before_quality_score: float
    estimated_after_quality_score: float
    estimated_quality_delta: float
    recommended_plugin: str
    recommended_preset: str
    recommended_strength: str
    estimated_runtime: str
    estimated_disk_write: int
    estimated_gpu_required: bool
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        values = asdict(self)
        values["action"] = self.action.value
        values["warnings"] = list(self.warnings)
        return values


@dataclass(frozen=True)
class CleanupPlan:
    version: int
    dataset_health_score: float
    projected_dataset_health: float
    estimated_artifact_leakage_reduction: float
    estimated_runtime: str
    estimated_disk_usage: int
    estimated_gpu_required: bool
    resource_profile: str
    total_images: int
    action_counts: dict[str, int]
    decisions: tuple[CleanupDecision, ...]
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "dataset_health_score": self.dataset_health_score,
            "projected_dataset_health": self.projected_dataset_health,
            "estimated_artifact_leakage_reduction": (
                self.estimated_artifact_leakage_reduction
            ),
            "estimated_runtime": self.estimated_runtime,
            "estimated_disk_usage": self.estimated_disk_usage,
            "estimated_gpu_required": self.estimated_gpu_required,
            "resource_profile": self.resource_profile,
            "total_images": self.total_images,
            "action_counts": self.action_counts,
            "warnings": list(self.warnings),
            "decisions": [decision.to_dict() for decision in self.decisions],
        }
