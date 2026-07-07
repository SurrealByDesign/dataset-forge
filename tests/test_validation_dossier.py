from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from dataset_forge.calibration_evidence import (
    CALIBRATION_LABELS_SCHEMA,
    parse_calibration_labels,
)
from dataset_forge.review_decisions import (
    REVIEW_DECISIONS_SCHEMA,
    parse_review_decisions,
)
from dataset_forge.validation_dossier import (
    READINESS_FALSE_NEGATIVES,
    READINESS_FALSE_POSITIVES,
    READINESS_INSUFFICIENT_EVIDENCE,
    READINESS_READY,
    READINESS_REVIEW_DISAGREEMENT,
    VALIDATION_DOSSIER_SCHEMA,
    build_validation_dossier,
    build_validation_dossier_files,
    write_validation_dossier_json,
)


TEXTURE = "texture.high_microtexture"
TEXTURE_ANALYZER = "texture_analyzer/v1"


def _labels(
    positives: set[int],
    *,
    count: int = 10,
    category: str = TEXTURE,
) -> dict:
    return {
        "schema": CALIBRATION_LABELS_SCHEMA,
        "labels": [
            {
                "image_path": f"image_{index:02d}.png",
                "categories": [category] if index in positives else [],
            }
            for index in range(count)
        ],
    }


def _report(
    predicted: set[int],
    *,
    category: str = TEXTURE,
    analyzer: str = TEXTURE_ANALYZER,
) -> dict:
    return {
        "schema": "dataset-forge/inspection/v1",
        "findings": [
            {
                "image_path": f"image_{index:02d}.png",
                "analyzer": analyzer,
                "category": category,
                "severity": "MEDIUM",
                "confidence": 0.45,
            }
            for index in sorted(predicted)
        ],
    }


def _decisions() -> dict:
    return {
        "schema": REVIEW_DECISIONS_SCHEMA,
        "decisions": [
            {
                "image_path": "image_00.png",
                "category": TEXTURE,
                "analyzer": TEXTURE_ANALYZER,
                "decision": "IMPROVEMENT_CANDIDATE",
                "workflow_state": "REVIEWED",
            },
            {
                "image_path": "image_03.png",
                "category": TEXTURE,
                "analyzer": TEXTURE_ANALYZER,
                "decision": "ACCEPTED_STYLE_FALSE_POSITIVE",
                "workflow_state": "REVIEWED",
            },
        ],
    }


class ValidationDossierTests(unittest.TestCase):
    def test_generates_valid_dossier_with_metrics_and_review_counts(self) -> None:
        dossier = build_validation_dossier(
            _report({0, 1, 2}),
            parse_calibration_labels(_labels({0, 1, 2})),
            parse_review_decisions(_decisions()),
        )

        payload = dossier.to_dict()
        texture = payload["category_summaries"][TEXTURE]

        self.assertEqual(payload["schema"], VALIDATION_DOSSIER_SCHEMA)
        self.assertEqual(payload["report_schema"], "dataset-forge/inspection/v1")
        self.assertEqual(payload["label_schema"], CALIBRATION_LABELS_SCHEMA)
        self.assertEqual(payload["review_decision_schema"], REVIEW_DECISIONS_SCHEMA)
        self.assertEqual(texture["metrics"]["tp"], 3)
        self.assertEqual(texture["confirmed_artifact_count"], 1)
        self.assertEqual(texture["false_positive_review_decision_count"], 1)

    def test_optional_review_decisions_may_be_omitted(self) -> None:
        dossier = build_validation_dossier(
            _report({0, 1, 2}),
            parse_calibration_labels(_labels({0, 1, 2})),
        )
        payload = dossier.to_dict()

        self.assertIsNone(payload["review_decision_schema"])
        self.assertIsNone(payload["review_decision_summary"])
        self.assertEqual(
            payload["category_summaries"][TEXTURE]["confirmed_artifact_count"],
            0,
        )

    def test_insufficient_evidence_status_is_explicit(self) -> None:
        dossier = build_validation_dossier(
            _report({0}),
            parse_calibration_labels(_labels({0}, count=4)),
        )

        texture = dossier.to_dict()["category_summaries"][TEXTURE]

        self.assertFalse(texture["ready_for_repair_planning"])
        self.assertEqual(texture["readiness_status"], READINESS_INSUFFICIENT_EVIDENCE)

    def test_false_positive_examples_are_extracted(self) -> None:
        dossier = build_validation_dossier(
            _report({0, 1, 2, 3}),
            parse_calibration_labels(_labels({0, 1, 2})),
        )

        examples = dossier.to_dict()["false_positive_examples"]

        self.assertEqual(len(examples), 1)
        self.assertEqual(examples[0]["image_path"], "image_03.png")
        self.assertEqual(examples[0]["category"], TEXTURE)
        self.assertEqual(examples[0]["example_type"], "false_positive")

    def test_false_negative_examples_are_extracted(self) -> None:
        dossier = build_validation_dossier(
            _report({0, 1}),
            parse_calibration_labels(_labels({0, 1, 2})),
        )

        examples = dossier.to_dict()["false_negative_examples"]

        self.assertEqual(len(examples), 1)
        self.assertEqual(examples[0]["image_path"], "image_02.png")
        self.assertEqual(examples[0]["category"], TEXTURE)
        self.assertEqual(examples[0]["example_type"], "false_negative")

    def test_per_analyzer_and_category_summaries_are_present(self) -> None:
        dossier = build_validation_dossier(
            _report({0, 1, 2}),
            parse_calibration_labels(_labels({0, 1, 2})),
        )
        payload = dossier.to_dict()

        self.assertIn(TEXTURE_ANALYZER, payload["analyzer_summaries"])
        self.assertIn(TEXTURE, payload["category_summaries"])
        self.assertEqual(
            payload["analyzer_summaries"][TEXTURE_ANALYZER]["metrics"]["tp"],
            3,
        )

    def test_ready_status_requires_sufficient_clean_metrics(self) -> None:
        dossier = build_validation_dossier(
            _report({0, 1, 2}),
            parse_calibration_labels(_labels({0, 1, 2})),
        )

        texture = dossier.to_dict()["category_summaries"][TEXTURE]

        self.assertTrue(texture["ready_for_repair_planning"])
        self.assertEqual(texture["readiness_status"], READINESS_READY)

    def test_false_positive_status_blocks_readiness(self) -> None:
        dossier = build_validation_dossier(
            _report({0, 1, 2, 3}),
            parse_calibration_labels(_labels({0, 1, 2})),
        )

        texture = dossier.to_dict()["category_summaries"][TEXTURE]

        self.assertFalse(texture["ready_for_repair_planning"])
        self.assertEqual(texture["readiness_status"], READINESS_FALSE_POSITIVES)
        self.assertEqual(
            dossier.to_dict()["threshold_review_candidates"][0]["category"],
            TEXTURE,
        )

    def test_false_negative_status_blocks_readiness(self) -> None:
        dossier = build_validation_dossier(
            _report({0, 1}),
            parse_calibration_labels(_labels({0, 1, 2})),
        )

        texture = dossier.to_dict()["category_summaries"][TEXTURE]

        self.assertFalse(texture["ready_for_repair_planning"])
        self.assertEqual(texture["readiness_status"], READINESS_FALSE_NEGATIVES)

    def test_review_disagreement_blocks_readiness(self) -> None:
        dossier = build_validation_dossier(
            _report({0, 1, 2}),
            parse_calibration_labels(_labels({0, 1, 2})),
            parse_review_decisions(_decisions()),
        )

        texture = dossier.to_dict()["category_summaries"][TEXTURE]

        self.assertFalse(texture["ready_for_repair_planning"])
        self.assertEqual(texture["readiness_status"], READINESS_REVIEW_DISAGREEMENT)

    def test_output_ordering_is_deterministic(self) -> None:
        dossier = build_validation_dossier(
            _report({2, 0, 1}),
            parse_calibration_labels(_labels({2, 0, 1})),
        )
        payload = dossier.to_dict()

        self.assertEqual(
            list(payload["category_summaries"]),
            [
                "artifact.crystalline_faceting",
                "artifact.high_frequency_isolated",
                "artifact.oversharpening_halo",
                TEXTURE,
            ],
        )

    def test_output_is_json_serializable(self) -> None:
        dossier = build_validation_dossier(
            _report({0, 1, 2}),
            parse_calibration_labels(_labels({0, 1, 2})),
        )

        self.assertIn(
            VALIDATION_DOSSIER_SCHEMA,
            json.dumps(dossier.to_dict()),
        )

    def test_file_api_loads_inputs_and_writes_dossier_json(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            report_path = root / "inspection_report.json"
            labels_path = root / "calibration_labels.json"
            decisions_path = root / "review_decisions.json"
            output_path = root / "validation_dossier.json"
            report_path.write_text(json.dumps(_report({0, 1, 2})), encoding="utf-8")
            labels_path.write_text(json.dumps(_labels({0, 1, 2})), encoding="utf-8")
            decisions_path.write_text(json.dumps(_decisions()), encoding="utf-8")

            dossier = build_validation_dossier_files(
                report_path,
                labels_path,
                decisions_path,
            )
            write_validation_dossier_json(dossier, output_path)
            payload = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(payload["schema"], VALIDATION_DOSSIER_SCHEMA)
        self.assertEqual(payload["category_summaries"][TEXTURE]["metrics"]["tp"], 3)


if __name__ == "__main__":
    unittest.main()
