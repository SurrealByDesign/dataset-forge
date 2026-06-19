"""Tests for scripts/texture_threshold_calibration.py."""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
from PIL import Image

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "src"))
sys.path.insert(0, str(_REPO / "scripts"))

from texture_threshold_calibration import (
    GROUND_TRUTH_SCHEMA,
    TEXTURE_CATEGORY,
    build_samples,
    choose_label_source,
    current_threshold_summary,
    evaluate_threshold,
    labels_from_decision_review,
    labels_from_ground_truth,
    main,
    render_report,
    sweep_thresholds,
    texture_findings_by_name,
)


def _write_image(path: Path) -> None:
    Image.fromarray(np.full((32, 32, 3), 128, dtype=np.uint8)).save(path)


def _texture_finding(name: str) -> dict:
    return {
        "image_path": name,
        "category": TEXTURE_CATEGORY,
        "evidence": {"z_score": 1.2, "microtexture_density": 52.0},
    }


def _crystalline_finding(name: str) -> dict:
    return {
        "image_path": name,
        "category": "artifact.crystalline_faceting",
        "evidence": {"pencil_grain_score": 65.0},
    }


def _report(dataset: Path, findings: list[dict] | None = None) -> dict:
    return {
        "schema": "dataset-forge/inspection/v1",
        "dataset_path": str(dataset),
        "context": {
            "texture_distributions": {
                "mean": 40.0,
                "stddev": 10.0,
                "p10": 30.0,
                "p90": 50.0,
                "sample_count": 3,
            },
        },
        "findings": findings or [],
    }


def _ground_truth(labels: dict[str, str]) -> dict:
    return {
        "schema": GROUND_TRUTH_SCHEMA,
        "labels": {
            name: {"label": label}
            for name, label in labels.items()
        },
    }


def _review(reviews: dict[str, dict]) -> dict:
    return {
        "schema": "dataset-forge/decision-review/v1",
        "reviews": reviews,
    }


class TestTextureCalibrationFiltering(unittest.TestCase):
    def test_texture_findings_exclude_crystalline_only_findings(self):
        report = {
            "findings": [
                _texture_finding("texture.png"),
                _crystalline_finding("crystal.png"),
            ],
        }

        index = texture_findings_by_name(report)

        self.assertIn("texture.png", index)
        self.assertNotIn("crystal.png", index)

    def test_decision_review_excludes_crystalline_only_findings(self):
        report = {
            "findings": [
                _texture_finding("texture.png"),
                _crystalline_finding("crystal.png"),
            ],
        }
        review = _review({
            "texture.png": {
                "review": "AGREE",
                "df_decision": "FINDING",
                "category": TEXTURE_CATEGORY,
            },
            "crystal.png": {
                "review": "AGREE",
                "df_decision": "FINDING",
                "category": "artifact.crystalline_faceting",
            },
        })

        labels = labels_from_decision_review(review, report)

        self.assertEqual(labels, {"texture.png": "ARTIFACT"})


class TestGroundTruthLabels(unittest.TestCase):
    def test_ground_truth_partitioning(self):
        labels = labels_from_ground_truth(_ground_truth({
            "a.png": "ARTIFACT",
            "c.png": "CLEAN",
            "u.png": "UNCERTAIN",
        }))

        self.assertEqual(labels["a.png"], "ARTIFACT")
        self.assertEqual(labels["c.png"], "CLEAN")
        self.assertEqual(labels["u.png"], "UNCERTAIN")

    def test_ground_truth_ignores_unknown_labels(self):
        labels = labels_from_ground_truth(_ground_truth({
            "a.png": "ARTIFACT",
            "bad.png": "MAYBE",
        }))

        self.assertEqual(labels, {"a.png": "ARTIFACT"})


class TestLabelSourceSelection(unittest.TestCase):
    def test_choose_label_source_prefers_ground_truth_over_review(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dataset = root / "dataset"
            dataset.mkdir()
            ground_truth_path = root / "ground_truth.json"
            review_path = root / "decision_review.json"
            ground_truth_path.write_text(
                json.dumps(_ground_truth({"ground.png": "CLEAN"})),
                encoding="utf-8",
            )
            review_path.write_text(
                json.dumps(_review({
                    "review.png": {
                        "review": "AGREE",
                        "df_decision": "FINDING",
                        "category": TEXTURE_CATEGORY,
                    },
                })),
                encoding="utf-8",
            )

            source, labels = choose_label_source(
                dataset,
                _report(dataset, [_texture_finding("review.png")]),
                ground_truth_path,
                review_path,
            )

        self.assertEqual(source, "ground_truth")
        self.assertEqual(labels, {"ground.png": "CLEAN"})

    def test_choose_label_source_uses_dataset_ground_truth_by_default(self):
        with tempfile.TemporaryDirectory() as td:
            dataset = Path(td)
            ground_truth_path = dataset / "ground_truth.json"
            ground_truth_path.write_text(
                json.dumps(_ground_truth({"default.png": "ARTIFACT"})),
                encoding="utf-8",
            )

            source, labels = choose_label_source(
                dataset,
                _report(dataset),
                None,
                None,
            )

        self.assertEqual(source, "ground_truth")
        self.assertEqual(labels, {"default.png": "ARTIFACT"})

    def test_choose_label_source_raises_without_available_labels(self):
        with tempfile.TemporaryDirectory() as td:
            dataset = Path(td)

            with self.assertRaises(ValueError):
                choose_label_source(dataset, _report(dataset), None, None)


class TestThresholdMetrics(unittest.TestCase):
    def test_threshold_sweep_metrics(self):
        samples = [
            {"filename": "tp.png", "label": "ARTIFACT", "micro": 50.0, "z": 1.5},
            {"filename": "fn.png", "label": "ARTIFACT", "micro": 50.0, "z": 0.8},
            {"filename": "fp.png", "label": "CLEAN", "micro": 50.0, "z": 1.4},
            {"filename": "tn.png", "label": "CLEAN", "micro": 50.0, "z": 0.2},
        ]

        row = evaluate_threshold(samples, 1.0)

        self.assertEqual(row["tp"], 1)
        self.assertEqual(row["fp"], 1)
        self.assertEqual(row["fn"], 1)
        self.assertEqual(row["tn"], 1)
        self.assertAlmostEqual(row["precision"], 0.5)
        self.assertAlmostEqual(row["recall"], 0.5)
        self.assertAlmostEqual(row["f1"], 0.5)

    def test_evaluate_threshold_enforces_absolute_floor(self):
        samples = [
            {"filename": "artifact.png", "label": "ARTIFACT", "micro": 14.9, "z": 99.0},
            {"filename": "clean.png", "label": "CLEAN", "micro": 14.9, "z": 99.0},
        ]

        row = evaluate_threshold(samples, 1.0, absolute_floor=15.0)

        self.assertEqual(row["tp"], 0)
        self.assertEqual(row["fp"], 0)
        self.assertEqual(row["fn"], 1)
        self.assertEqual(row["tn"], 1)

    def test_sweep_thresholds_returns_one_row_per_threshold(self):
        rows = sweep_thresholds([], [0.5, 1.0, 1.5])
        self.assertEqual([r["threshold"] for r in rows], [0.5, 1.0, 1.5])

    def test_current_threshold_summary(self):
        samples = [
            {"filename": "tp.png", "label": "ARTIFACT", "micro": 50.0, "z": 1.5},
            {"filename": "tn.png", "label": "CLEAN", "micro": 50.0, "z": 0.2},
        ]

        summary = current_threshold_summary(samples)

        self.assertEqual(summary["threshold"], 1.0)
        self.assertEqual(summary["tp"], 1)
        self.assertEqual(summary["tn"], 1)
        self.assertEqual(summary["fp_rate"], 0.0)
        self.assertIn(summary["fp_rate_assessment"], {"conservative", "optimistic", "unknown"})
        self.assertIn(summary["confidence_cap_assessment"], {"conservative", "optimistic", "unknown"})

    def test_render_report_includes_decision_review_fallback_caveat(self):
        current = {
            "tp": 0,
            "fp": 0,
            "fn": 0,
            "tn": 0,
            "fp_rate": None,
            "configured_fp_rate": 0.0,
            "confidence_cap": 0.0,
            "fp_rate_assessment": "unknown",
            "confidence_cap_assessment": "unknown",
        }

        report = render_report("decision_review_fallback", [], [], current)

        self.assertIn("decision_review fallback", report)
        self.assertIn("less reliable than ground_truth.json", report)


class TestBuildSamplesAndCli(unittest.TestCase):
    def test_build_samples_uses_measurement_helper(self):
        with tempfile.TemporaryDirectory() as td:
            dataset = Path(td)
            path = dataset / "img.png"
            _write_image(path)
            tex = MagicMock()
            tex.status = "analyzed"
            tex.microtexture_density_score = 55.0

            with patch("texture_threshold_calibration.measure_texture", return_value=tex):
                samples = build_samples(
                    dataset,
                    {"img.png": "ARTIFACT"},
                    _report(dataset),
                )

        self.assertEqual(samples[0]["filename"], "img.png")
        self.assertEqual(samples[0]["label"], "ARTIFACT")
        self.assertEqual(samples[0]["micro"], 55.0)
        self.assertEqual(samples[0]["z"], 1.5)

    def test_script_runs_on_small_synthetic_fixture_inputs(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dataset = root / "dataset"
            dataset.mkdir()
            _write_image(dataset / "artifact.png")
            _write_image(dataset / "clean.png")

            report_path = root / "inspection_report.json"
            gt_path = root / "ground_truth.json"
            report_path.write_text(
                json.dumps(_report(dataset, [_texture_finding("artifact.png")])),
                encoding="utf-8",
            )
            gt_path.write_text(
                json.dumps(_ground_truth({
                    "artifact.png": "ARTIFACT",
                    "clean.png": "CLEAN",
                })),
                encoding="utf-8",
            )

            stdout = io.StringIO()
            argv = [
                "texture_threshold_calibration.py",
                "--dataset", str(dataset),
                "--report", str(report_path),
                "--ground-truth", str(gt_path),
                "--threshold-min", "0.5",
                "--threshold-max", "1.0",
                "--threshold-step", "0.5",
            ]
            with patch.object(sys, "argv", argv):
                with patch("sys.stdout", stdout):
                    main()

        output = stdout.getvalue()
        self.assertIn("Dataset Forge Texture Threshold Calibration", output)
        self.assertIn("Label source: ground_truth", output)
        self.assertIn("Threshold sweep", output)
        self.assertIn("Current TextureAnalyzer threshold", output)


if __name__ == "__main__":
    unittest.main()
