"""Tests for the Finding dataclass — universal analyzer output contract."""

import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from dataset_forge.finding import Finding, Severity


def _make_finding(**overrides) -> Finding:
    defaults = dict(
        image_path=Path("test.png"),
        analyzer="test_analyzer/v1",
        category="artifact.test",
        severity=Severity.MEDIUM,
        confidence=0.85,
        false_positive_rate=0.05,
        benchmark_version="synthetic_test_v1",
        evidence={"score": 42},
        explanation="Test explanation.",
        recommendation="Test recommendation.",
    )
    return Finding(**{**defaults, **overrides})


class TestFindingConstruction(unittest.TestCase):
    def test_constructs_with_all_fields(self):
        f = _make_finding()
        self.assertEqual(f.analyzer, "test_analyzer/v1")
        self.assertEqual(f.severity, Severity.MEDIUM)
        self.assertAlmostEqual(f.confidence, 0.85)

    def test_is_frozen(self):
        f = _make_finding()
        with self.assertRaises(FrozenInstanceError):
            f.confidence = 0.99  # type: ignore[misc]

    def test_evidence_is_extensible_dict(self):
        f = _make_finding(evidence={"a": 1, "b": "two", "c": [3]})
        self.assertEqual(f.evidence["b"], "two")


class TestFindingSerialization(unittest.TestCase):
    def test_to_dict_returns_dict(self):
        f = _make_finding()
        d = f.to_dict()
        self.assertIsInstance(d, dict)

    def test_to_dict_image_path_is_string(self):
        f = _make_finding(image_path=Path("/some/path/img.png"))
        d = f.to_dict()
        self.assertIsInstance(d["image_path"], str)

    def test_to_dict_severity_is_string(self):
        f = _make_finding(severity=Severity.HIGH)
        d = f.to_dict()
        self.assertEqual(d["severity"], "HIGH")

    def test_to_dict_contains_schema(self):
        f = _make_finding()
        d = f.to_dict()
        self.assertIn("schema", d)
        self.assertTrue(d["schema"].startswith("dataset-forge/finding/"))


class TestSeverityOrdering(unittest.TestCase):
    def test_none_is_lowest(self):
        self.assertLess(Severity.NONE, Severity.LOW)

    def test_critical_is_highest(self):
        self.assertGreater(Severity.CRITICAL, Severity.HIGH)

    def test_full_ordering(self):
        ordered = [Severity.NONE, Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL]
        self.assertEqual(ordered, sorted(ordered))

    def test_equality(self):
        self.assertEqual(Severity.MEDIUM, Severity.MEDIUM)
        self.assertNotEqual(Severity.LOW, Severity.HIGH)


class TestFindingValidation(unittest.TestCase):
    def test_confidence_above_1_rejected(self):
        with self.assertRaises(ValueError):
            _make_finding(confidence=1.01)

    def test_confidence_below_0_rejected(self):
        with self.assertRaises(ValueError):
            _make_finding(confidence=-0.01)

    def test_confidence_boundary_values_accepted(self):
        _make_finding(confidence=0.0)
        _make_finding(confidence=1.0)

    def test_false_positive_rate_above_1_rejected(self):
        with self.assertRaises(ValueError):
            _make_finding(false_positive_rate=1.5)

    def test_false_positive_rate_below_0_rejected(self):
        with self.assertRaises(ValueError):
            _make_finding(false_positive_rate=-0.1)

    def test_false_positive_rate_boundary_values_accepted(self):
        _make_finding(false_positive_rate=0.0)
        _make_finding(false_positive_rate=1.0)

    def test_invalid_severity_type_rejected(self):
        with self.assertRaises(TypeError):
            _make_finding(severity="HIGH")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
