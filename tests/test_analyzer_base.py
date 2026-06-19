"""Tests for the Analyzer abstract base class."""

import unittest
from pathlib import Path

from dataset_forge.analyzers.base import Analyzer
from dataset_forge.context import DatasetContext
from dataset_forge.finding import Finding, Severity


# ---------------------------------------------------------------------------
# Minimal concrete implementation for testing the contract
# ---------------------------------------------------------------------------

class _AlwaysCleanAnalyzer(Analyzer):
    """Returns no findings — represents a healthy-image fast path."""

    @property
    def name(self) -> str:
        return "always_clean"

    @property
    def version(self) -> str:
        return "v1"

    def analyze(
        self,
        image_path: Path,
        context: DatasetContext,
        measurements=None,
    ) -> list[Finding]:
        return []


class _OneFindingAnalyzer(Analyzer):
    """Always emits one LOW finding — useful for testing report consumers."""

    @property
    def name(self) -> str:
        return "one_finding"

    @property
    def version(self) -> str:
        return "v1"

    @property
    def supported_categories(self) -> tuple[str, ...]:
        return ("artifact.test",)

    @property
    def benchmark_version(self) -> str | None:
        return "synthetic_test_v1"

    def analyze(
        self,
        image_path: Path,
        context: DatasetContext,
        measurements=None,
    ) -> list[Finding]:
        return [
            Finding(
                image_path=image_path,
                analyzer=self.analyzer_id,
                category="artifact.test",
                severity=Severity.LOW,
                confidence=0.75,
                false_positive_rate=0.10,
                benchmark_version=self.benchmark_version or "uncalibrated",
                evidence={"raw_score": 0.5},
                explanation="Test finding.",
                recommendation="No action required.",
            )
        ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ctx() -> DatasetContext:
    return DatasetContext.empty(image_paths=[Path("img.png")])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAnalyzerCannotBeInstantiatedDirectly(unittest.TestCase):
    def test_abstract_class_raises(self):
        with self.assertRaises(TypeError):
            Analyzer()  # type: ignore[abstract]


class TestAnalyzerContract(unittest.TestCase):
    def test_analyzer_id_combines_name_and_version(self):
        a = _AlwaysCleanAnalyzer()
        self.assertEqual(a.analyzer_id, "always_clean/v1")

    def test_default_supported_categories_is_empty(self):
        a = _AlwaysCleanAnalyzer()
        self.assertEqual(a.supported_categories, ())

    def test_default_benchmark_version_is_none(self):
        a = _AlwaysCleanAnalyzer()
        self.assertIsNone(a.benchmark_version)

    def test_overridden_supported_categories(self):
        a = _OneFindingAnalyzer()
        self.assertIn("artifact.test", a.supported_categories)

    def test_overridden_benchmark_version(self):
        a = _OneFindingAnalyzer()
        self.assertEqual(a.benchmark_version, "synthetic_test_v1")


class TestAnalyzerAnalyze(unittest.TestCase):
    def test_clean_analyzer_returns_empty_list(self):
        a = _AlwaysCleanAnalyzer()
        findings = a.analyze(Path("img.png"), _ctx())
        self.assertEqual(findings, [])

    def test_one_finding_analyzer_returns_list(self):
        a = _OneFindingAnalyzer()
        findings = a.analyze(Path("img.png"), _ctx())
        self.assertEqual(len(findings), 1)

    def test_finding_analyzer_id_matches(self):
        a = _OneFindingAnalyzer()
        findings = a.analyze(Path("img.png"), _ctx())
        self.assertEqual(findings[0].analyzer, "one_finding/v1")

    def test_finding_is_finding_instance(self):
        a = _OneFindingAnalyzer()
        findings = a.analyze(Path("img.png"), _ctx())
        self.assertIsInstance(findings[0], Finding)

    def test_finding_image_path_matches_input(self):
        a = _OneFindingAnalyzer()
        path = Path("some/image.png")
        findings = a.analyze(path, _ctx())
        self.assertEqual(findings[0].image_path, path)

    def test_analyzer_does_not_modify_context(self):
        a = _OneFindingAnalyzer()
        ctx = _ctx()
        image_count_before = ctx.image_count
        a.analyze(Path("img.png"), ctx)
        self.assertEqual(ctx.image_count, image_count_before)


if __name__ == "__main__":
    unittest.main()
