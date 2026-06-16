"""Universal output contract for all Dataset Forge analyzers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any

FINDING_SCHEMA = "dataset-forge/finding/v1"


class Severity(Enum):
    NONE = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

    def __lt__(self, other: Severity) -> bool:
        return self.value < other.value

    def __le__(self, other: Severity) -> bool:
        return self.value <= other.value

    def __gt__(self, other: Severity) -> bool:
        return self.value > other.value

    def __ge__(self, other: Severity) -> bool:
        return self.value >= other.value


@dataclass(frozen=True)
class Finding:
    """A single calibrated observation emitted by an analyzer.

    Treat this as a stable public API. Analyzers adapt to Finding;
    Finding does not change to accommodate analyzers. Extensions belong
    in the `evidence` dict, not as new top-level fields.
    """

    image_path: Path
    analyzer: str             # e.g. "glitter_analyzer/v1"
    category: str             # e.g. "artifact.glitter"
    severity: Severity
    confidence: float         # 0.0–1.0
    false_positive_rate: float  # estimated from benchmark
    benchmark_version: str    # benchmark that calibrated this threshold
    evidence: dict[str, Any]  # raw measurements; extensible
    explanation: str          # human-readable why
    recommendation: str       # human-readable what to do

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be 0.0–1.0, got {self.confidence}")
        if not 0.0 <= self.false_positive_rate <= 1.0:
            raise ValueError(f"false_positive_rate must be 0.0–1.0, got {self.false_positive_rate}")
        if not isinstance(self.severity, Severity):
            raise TypeError(f"severity must be a Severity instance, got {type(self.severity)}")

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["image_path"] = str(self.image_path)
        d["severity"] = self.severity.name
        d["schema"] = FINDING_SCHEMA
        return d
