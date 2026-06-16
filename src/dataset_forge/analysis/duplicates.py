"""Duplicate detection entry points."""

from dataset_forge.analysis.metrics import (
    PERCEPTUAL_HASH_DISTANCE,
    assign_duplicate_references,
    perceptual_hash_distance,
)

__all__ = [
    "PERCEPTUAL_HASH_DISTANCE",
    "assign_duplicate_references",
    "perceptual_hash_distance",
]

