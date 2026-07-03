from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from dataset_forge.calibration_evidence import (
    CALIBRATION_EVIDENCE_SCHEMA,
    CALIBRATION_LABELS_SCHEMA,
    ConfusionMetrics,
    evaluate_calibration,
    evaluate_calibration_files,
    parse_calibration_labels,
    write_calibration_evidence_json,
)


def _labels() -> dict:
    return {
        "schema": CALIBRATION_LABELS_SCHEMA,
        "labels": [
            {
                "image_path": "a.png",
                "categories": ["texture.high_microtexture"],
            },
            {
                "image_path": "b.png",
                "categories": [],
            },
            {
                "image_path": "c.png",
                "categories": ["artifact.crystalline_faceting"],
            },
            {
                "image_path": "d.png",
                "categories": [],
            },
        ],
    }


def _report() -> dict:
    return {
        "schema": "dataset-forge/inspection/v1",
        "findings": [
            {
                "image_path": "a.png",
                "analyzer": "texture_analyzer/v1",
                "category": "texture.high_microtexture",
                "severity": "MEDIUM",
            },
            {
                "image_path": "b.png",
                "analyzer": "texture_analyzer/v1",
                "category": "texture.high_microtexture",
                "severity": "LOW",
            },
            {
                "image_path": "d.png",
                "analyzer": "oversharpening_halo_analyzer/v1",
                "category": "artifact.oversharpening_halo.error",
                "severity": "LOW",
            },
        ],
    }


class ConfusionMetricTests(unittest.TestCase):
    def test_computes_precision_recall_f1_and_false_positive_rate(self) -> None:
        metrics = ConfusionMetrics(tp=2, fp=1, fn=1, tn=6)

        self.assertEqual(metrics.precision, 0.666667)
        self.assertEqual(metrics.recall, 0.666667)
        self.assertEqual(metrics.f1, 0.666667)
        self.assertEqual(metrics.false_positive_rate, 0.142857)

    def test_zero_denominators_return_zero(self) -> None:
        metrics = ConfusionMetrics(tp=0, fp=0, fn=0, tn=0)

        self.assertEqual(metrics.precision, 0.0)
        self.assertEqual(metrics.recall, 0.0)
        self.assertEqual(metrics.f1, 0.0)
        self.assertEqual(metrics.false_positive_rate, 0.0)


class CalibrationLabelTests(unittest.TestCase):
    def test_parses_clean_and_artifact_labels(self) -> None:
        labels = parse_calibration_labels(_labels())

        self.assertEqual(labels.schema, CALIBRATION_LABELS_SCHEMA)
        self.assertEqual(labels.image_count, 4)
        self.assertEqual(
            labels.labels_by_image["a.png"],
            frozenset({"texture.high_microtexture"}),
        )
        self.assertEqual(labels.labels_by_image["b.png"], frozenset())

    def test_rejects_unknown_schema(self) -> None:
        raw = _labels()
        raw["schema"] = "wrong"

        with self.assertRaises(ValueError):
            parse_calibration_labels(raw)

    def test_rejects_duplicate_image_labels(self) -> None:
        raw = _labels()
        raw["labels"].append({
            "image_path": "a.png",
            "categories": [],
        })

        with self.assertRaises(ValueError):
            parse_calibration_labels(raw)

    def test_rejects_unknown_categories(self) -> None:
        raw = _labels()
        raw["labels"][0]["categories"] = ["artifact.future_unknown"]

        with self.assertRaises(ValueError):
            parse_calibration_labels(raw)


class CalibrationEvidenceTests(unittest.TestCase):
    def test_evaluates_per_analyzer_confusion_metrics(self) -> None:
        evidence = evaluate_calibration(_report(), parse_calibration_labels(_labels()))

        texture = evidence.analyzer_results["texture_analyzer/v1"]
        self.assertEqual(texture.tp, 1)
        self.assertEqual(texture.fp, 1)
        self.assertEqual(texture.fn, 0)
        self.assertEqual(texture.tn, 2)
        self.assertEqual(texture.precision, 0.5)
        self.assertEqual(texture.recall, 1.0)
        self.assertEqual(texture.f1, 0.666667)
        self.assertEqual(texture.false_positive_rate, 0.333333)

    def test_evaluates_category_level_summary(self) -> None:
        evidence = evaluate_calibration(_report(), parse_calibration_labels(_labels()))

        crystalline = evidence.category_results["artifact.crystalline_faceting"]
        self.assertEqual(crystalline.tp, 0)
        self.assertEqual(crystalline.fp, 0)
        self.assertEqual(crystalline.fn, 1)
        self.assertEqual(crystalline.tn, 3)
        self.assertEqual(crystalline.precision, 0.0)
        self.assertEqual(crystalline.recall, 0.0)

    def test_ignores_error_findings_for_positive_calibration(self) -> None:
        evidence = evaluate_calibration(_report(), parse_calibration_labels(_labels()))

        halo = evidence.analyzer_results["oversharpening_halo_analyzer/v1"]
        self.assertEqual(halo.tp, 0)
        self.assertEqual(halo.fp, 0)
        self.assertEqual(halo.fn, 0)
        self.assertEqual(halo.tn, 4)
        self.assertEqual(evidence.ignored_error_finding_count, 1)

    def test_output_is_json_serializable_and_schema_versioned(self) -> None:
        evidence = evaluate_calibration(_report(), parse_calibration_labels(_labels()))
        payload = evidence.to_dict()

        self.assertEqual(payload["schema"], CALIBRATION_EVIDENCE_SCHEMA)
        self.assertEqual(payload["report_schema"], "dataset-forge/inspection/v1")
        self.assertEqual(payload["label_schema"], CALIBRATION_LABELS_SCHEMA)
        self.assertEqual(payload["evaluated_image_count"], 4)
        self.assertIn("category_to_analyzer", payload)
        self.assertIn("texture_analyzer/v1", json.loads(json.dumps(payload))["analyzer_results"])

    def test_file_api_loads_report_and_labels_and_writes_json(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            report_path = root / "inspection_report.json"
            labels_path = root / "ground_truth.json"
            output_path = root / "calibration_evidence.json"
            report_path.write_text(json.dumps(_report()), encoding="utf-8")
            labels_path.write_text(json.dumps(_labels()), encoding="utf-8")

            evidence = evaluate_calibration_files(report_path, labels_path)
            write_calibration_evidence_json(evidence, output_path)
            data = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(data["schema"], CALIBRATION_EVIDENCE_SCHEMA)
        self.assertEqual(data["analyzer_results"]["texture_analyzer/v1"]["fp"], 1)


if __name__ == "__main__":
    unittest.main()
