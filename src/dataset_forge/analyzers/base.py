"""Abstract base class for all Dataset Forge analyzers.

Contract: an Analyzer consumes a DatasetContext and emits list[Finding].

Every concrete analyzer must implement `analyze()`, `name`, and `version`.
`supported_categories` and `benchmark_version` are strongly encouraged but
optional for analyzers that are not yet calibrated against a benchmark.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from dataset_forge.context import DatasetContext
from dataset_forge.finding import Finding


class Analyzer(ABC):
    """Base class for all analyzers in the Dataset Forge Inspect pipeline.

    Subclass this, implement the three abstract members, and the analyzer
    is automatically usable anywhere the pipeline accepts an Analyzer.

    Analyzers must be stateless with respect to individual images.
    Any cross-image state (distributions, baselines) lives in DatasetContext,
    which is built before analysis begins and is read-only during analysis.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable identifier for this analyzer, e.g. 'glitter_analyzer'.

        Used in Finding.analyzer (combined with version as 'name/version')
        and in DatasetContext.analyzer_versions. Do not change once findings
        have been published — it would break result comparisons across runs.
        """

    @property
    @abstractmethod
    def version(self) -> str:
        """Version string for this analyzer, e.g. 'v1'.

        Increment when thresholds, logic, or benchmark calibration changes
        in a way that would produce different findings on the same image.
        """

    @property
    def analyzer_id(self) -> str:
        """Canonical identifier used in Finding.analyzer: 'name/version'."""
        return f"{self.name}/{self.version}"

    @property
    def supported_categories(self) -> tuple[str, ...]:
        """Finding categories this analyzer may emit, e.g. ('artifact.glitter',).

        Used by the report layer to describe what each analyzer covers.
        Override in subclasses. Empty tuple means not declared.
        """
        return ()

    @property
    def benchmark_version(self) -> str | None:
        """Benchmark used to calibrate this analyzer's thresholds, or None.

        A finding produced by an uncalibrated analyzer (None here) should be
        treated as an uncalibrated opinion. Override once a benchmark exists.
        """
        return None

    @abstractmethod
    def analyze(self, image_path: Path, context: DatasetContext) -> list[Finding]:
        """Analyze one image and return zero or more calibrated Findings.

        Args:
            image_path: Absolute or relative path to the image file.
            context: Dataset-level statistics built before analysis began.
                     Read-only — do not modify.

        Returns:
            A list of Finding instances. Return an empty list if the image
            has no issues at any severity level. NONE-severity findings
            should not be emitted unless there is a specific reason to
            record a clean measurement.

        The implementation must not:
        - modify the image file
        - modify context
        - call other analyzers
        - maintain mutable cross-image state
        """
