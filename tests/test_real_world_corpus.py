from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from dataset_forge.calibration_evidence import load_calibration_labels
from dataset_forge.real_world_corpus import (
    REAL_WORLD_CORPUS_SCHEMA,
    REAL_WORLD_CORPUS_VALIDATION_SCHEMA,
    load_real_world_corpus_manifest,
    parse_real_world_corpus_manifest,
    validate_real_world_corpus,
)
from dataset_forge.validation_dossier import (
    READINESS_INSUFFICIENT_EVIDENCE,
    build_validation_dossier,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
CORPUS_ROOT = REPO_ROOT / "benchmarks" / "real_world"
MANIFEST_PATH = CORPUS_ROOT / "manifest.json"


class RealWorldCorpusTests(unittest.TestCase):
    def test_valid_real_world_corpus_manifest_loads(self) -> None:
        manifest = load_real_world_corpus_manifest(MANIFEST_PATH)

        self.assertEqual(manifest.schema, REAL_WORLD_CORPUS_SCHEMA)
        self.assertEqual(manifest.version, "v1")
        self.assertEqual(len(manifest.groups), 2)
        self.assertEqual(manifest.groups[0].fixture_kind, "placeholder_synthetic")
        self.assertEqual(manifest.groups[1].visibility, "private")

    def test_invalid_corpus_manifest_schema_is_rejected(self) -> None:
        raw = {
            "schema": "dataset-forge/real-world-validation-corpus/v999",
            "corpus_name": "Bad",
            "version": "v1",
            "description": "Invalid schema",
            "groups": [],
        }

        with self.assertRaisesRegex(ValueError, "Unsupported real-world corpus schema"):
            parse_real_world_corpus_manifest(raw)

    def test_unknown_manifest_fields_are_rejected(self) -> None:
        raw = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        raw["unexpected"] = True

        with self.assertRaisesRegex(ValueError, "unknown fields"):
            parse_real_world_corpus_manifest(raw)

    def test_missing_optional_private_fixtures_skip_cleanly(self) -> None:
        result = validate_real_world_corpus(MANIFEST_PATH)

        self.assertTrue(result.is_valid)
        self.assertGreaterEqual(result.skipped_optional_case_count, 1)
        self.assertEqual(result.missing_required_paths, ())

    def test_committed_public_fixture_paths_exist(self) -> None:
        manifest = load_real_world_corpus_manifest(MANIFEST_PATH)
        public_group = manifest.groups[0]

        self.assertEqual(public_group.visibility, "public")
        for case in public_group.cases:
            with self.subTest(case=case.image_id):
                self.assertTrue(case.committed)
                self.assertFalse(case.optional)
                self.assertTrue((CORPUS_ROOT / case.image_path).exists())

    def test_label_file_is_compatible_with_calibration_evidence(self) -> None:
        labels = load_calibration_labels(
            CORPUS_ROOT / "labels" / "placeholder_labels.json"
        )

        self.assertEqual(labels.image_count, 2)
        self.assertEqual(
            labels.labels_by_image["../synthetic_defects/10_texture_positive.png"],
            frozenset({"texture.high_microtexture"}),
        )

    def test_validation_dossier_compatibility_is_insufficient_evidence(self) -> None:
        labels = load_calibration_labels(
            CORPUS_ROOT / "labels" / "placeholder_labels.json"
        )
        report = {
            "schema": "dataset-forge/inspection/v1",
            "findings": [
                {
                    "image_path": "../synthetic_defects/10_texture_positive.png",
                    "analyzer": "texture_analyzer/v1",
                    "category": "texture.high_microtexture",
                    "severity": "MEDIUM",
                    "confidence": 0.45,
                }
            ],
        }

        dossier = build_validation_dossier(report, labels).to_dict()

        self.assertEqual(dossier["evaluated_image_count"], 2)
        self.assertEqual(
            dossier["category_summaries"]["texture.high_microtexture"][
                "readiness_status"
            ],
            READINESS_INSUFFICIENT_EVIDENCE,
        )

    def test_validate_result_is_json_serializable(self) -> None:
        payload = validate_real_world_corpus(MANIFEST_PATH).to_dict()

        self.assertEqual(payload["schema"], REAL_WORLD_CORPUS_VALIDATION_SCHEMA)
        self.assertIn(REAL_WORLD_CORPUS_VALIDATION_SCHEMA, json.dumps(payload))

    def test_missing_required_public_fixture_is_reported(self) -> None:
        raw = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        raw["groups"] = [raw["groups"][0]]
        raw["groups"][0]["cases"][0]["image_path"] = "missing-required.png"
        raw["groups"][0]["cases"] = [raw["groups"][0]["cases"][0]]

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "labels").mkdir()
            (root / "expected").mkdir()
            (root / "labels" / "placeholder_labels.json").write_text(
                json.dumps(
                    {
                        "schema": "dataset-forge/calibration-labels/v1",
                        "labels": [
                            {
                                "image_path": "missing-required.png",
                                "categories": [],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (root / "expected" / "placeholder_expected.json").write_text(
                "{}",
                encoding="utf-8",
            )
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(raw), encoding="utf-8")

            result = validate_real_world_corpus(manifest_path)

        self.assertFalse(result.is_valid)
        self.assertEqual(result.missing_required_paths, ("missing-required.png",))


if __name__ == "__main__":
    unittest.main()
