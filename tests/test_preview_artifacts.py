from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PIL import Image

from dataset_forge.improvement_preview import IMPROVEMENT_PREVIEW_SCHEMA
from dataset_forge.preview_artifacts import (
    PREVIEW_ARTIFACT_SCHEMA,
    PREVIEW_ARTIFACTS_FILENAME,
    PreviewArtifactError,
    import_manual_preview_candidate,
    load_preview_artifacts,
    preview_plan_record_id,
    resolve_preview_artifact,
)


def _image(path: Path, *, color: tuple[int, int, int], size: tuple[int, int] = (24, 24), image_format: str = "PNG") -> None:
    Image.new("RGB", size, color).save(path, format=image_format)


def _preview_record(image: Path) -> dict[str, object]:
    return {
        "image": {"path": str(image), "filename": image.name},
        "current_findings": [
            {
                "analyzer": "texture_analyzer/v1",
                "category": "texture.high_microtexture",
                "severity": "MEDIUM",
            }
        ],
        "recommended_operation": "REPLACE_SOURCE",
        "operation_rationale": "Manual review only.",
        "confidence": 0.55,
        "required_provider_type": "MANUAL",
        "preview_status": "WAITING_FOR_PROVIDER",
        "approval_state": "REJECTED",
    }


def _write_preview(output: Path, image: Path, *, legacy: bool = False) -> dict[str, object]:
    record = _preview_record(image)
    if legacy:
        record = {
            "image_path": str(image),
            "filename": image.name,
            "triggering_findings": record["current_findings"],
            "suggested_improvement": "REPLACE_SOURCE",
            "planning_status": "WAITING_FOR_PROVIDER",
        }
    payload = {
        "schema": IMPROVEMENT_PREVIEW_SCHEMA,
        "summary": {},
        "preview_entries": [record],
    }
    if not legacy:
        payload["preview_records"] = [record]
    (output / "improvement_preview.json").write_text(json.dumps(payload), encoding="utf-8")
    return record


class PreviewArtifactImportTests(unittest.TestCase):
    def test_import_is_isolated_deterministic_and_idempotent(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "inspect_output"
            output.mkdir()
            source = root / "source.png"
            candidate = root / "candidate.png"
            _image(source, color=(10, 20, 30))
            _image(candidate, color=(30, 20, 10), size=(48, 24))
            record = _write_preview(output, source)
            source_before = source.read_bytes()
            candidate_before = candidate.read_bytes()

            first = import_manual_preview_candidate(output, source, candidate)
            second = import_manual_preview_candidate(output, source, candidate)

            sidecar = json.loads((output / PREVIEW_ARTIFACTS_FILENAME).read_text(encoding="utf-8"))
            preview = json.loads((output / "improvement_preview.json").read_text(encoding="utf-8"))
            artifact = sidecar["artifacts"][0]
            copied = Path(first["artifact_path"])
            copied_exists = copied.is_file()
            copied_bytes = copied.read_bytes()
            source_after = source.read_bytes()
            candidate_after = candidate.read_bytes()

        self.assertTrue(first["imported"])
        self.assertTrue(second["idempotent"])
        self.assertEqual(sidecar["schema"], PREVIEW_ARTIFACT_SCHEMA)
        self.assertEqual(artifact["preview_plan_record_id"], preview_plan_record_id(record))
        self.assertEqual(artifact["provider"]["type"], "MANUAL")
        self.assertFalse(artifact["provider"]["execution_available"])
        self.assertFalse(Path(artifact["candidate"]["artifact_reference"]["relative_path"]).is_absolute())
        self.assertEqual(artifact["candidate"]["sha256"], hashlib.sha256(candidate_before).hexdigest())
        self.assertEqual(artifact["source"]["sha256"], hashlib.sha256(source_before).hexdigest())
        self.assertTrue(copied_exists)
        self.assertEqual(copied_bytes, candidate_before)
        self.assertEqual(source_after, source_before)
        self.assertEqual(candidate_after, candidate_before)
        self.assertEqual(preview["preview_records"][0]["preview_status"], "READY")
        self.assertEqual(preview["preview_records"][0]["approval_state"], "NOT_REQUESTED")
        self.assertTrue(artifact["warnings"])

    def test_import_rejects_invalid_inputs_without_writes(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "inspect_output"
            output.mkdir()
            source = root / "source.png"
            corrupt = root / "corrupt.png"
            _image(source, color=(10, 20, 30))
            corrupt.write_text("not an image", encoding="utf-8")
            _write_preview(output, source)
            preview_before = (output / "improvement_preview.json").read_bytes()

            with self.assertRaises(PreviewArtifactError):
                import_manual_preview_candidate(output, source, corrupt)
            with self.assertRaises(PreviewArtifactError):
                import_manual_preview_candidate(output, source, source)
            artifacts_missing = not (output / PREVIEW_ARTIFACTS_FILENAME).exists()
            artifact_root_missing = not (output / "preview_artifacts").exists()
            preview_after = (output / "improvement_preview.json").read_bytes()

        self.assertTrue(artifacts_missing)
        self.assertTrue(artifact_root_missing)
        self.assertEqual(preview_after, preview_before)

    def test_import_rejects_candidate_inside_artifact_root(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "inspect_output"
            output.mkdir()
            source = root / "source.png"
            artifact_root = output / "preview_artifacts"
            artifact_root.mkdir()
            candidate = artifact_root / "candidate.png"
            _image(source, color=(10, 20, 30))
            _image(candidate, color=(30, 20, 10))
            _write_preview(output, source)
            preview_before = (output / "improvement_preview.json").read_bytes()

            with self.assertRaises(PreviewArtifactError):
                import_manual_preview_candidate(output, source, candidate)
            preview_after = (output / "improvement_preview.json").read_bytes()

        self.assertEqual(preview_after, preview_before)

    def test_import_rejects_symlinked_artifact_root(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "inspect_output"
            output.mkdir()
            source = root / "source.png"
            candidate = root / "candidate.png"
            outside = root / "outside_artifacts"
            outside.mkdir()
            _image(source, color=(10, 20, 30))
            _image(candidate, color=(30, 20, 10))
            _write_preview(output, source)
            try:
                (output / "preview_artifacts").symlink_to(outside, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"symlink creation is unavailable: {exc}")

            with self.assertRaises(PreviewArtifactError):
                import_manual_preview_candidate(output, source, candidate)

        self.assertFalse(list(outside.rglob("candidate-*")))

    def test_metadata_failure_cleans_up_new_artifact_and_preserves_preview(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "inspect_output"
            output.mkdir()
            source = root / "source.png"
            candidate = root / "candidate.png"
            _image(source, color=(10, 20, 30))
            _image(candidate, color=(30, 20, 10))
            _write_preview(output, source)
            preview_before = (output / "improvement_preview.json").read_bytes()

            with patch("dataset_forge.preview_artifacts._atomic_write_json", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    import_manual_preview_candidate(output, source, candidate)
            artifacts_missing = not (output / PREVIEW_ARTIFACTS_FILENAME).exists()
            copied_paths = list((output / "preview_artifacts").rglob("candidate-*"))
            preview_after = (output / "improvement_preview.json").read_bytes()

        self.assertTrue(artifacts_missing)
        self.assertFalse(copied_paths)
        self.assertEqual(preview_after, preview_before)

    def test_legacy_preview_entry_is_updated_without_schema_rewrite(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "inspect_output"
            output.mkdir()
            source = root / "source.png"
            candidate = root / "candidate.png"
            _image(source, color=(10, 20, 30))
            _image(candidate, color=(30, 20, 10))
            _write_preview(output, source, legacy=True)

            import_manual_preview_candidate(output, source, candidate)
            preview = json.loads((output / "improvement_preview.json").read_text(encoding="utf-8"))

        self.assertIn("preview_entries", preview)
        self.assertNotIn("preview_records", preview)
        self.assertEqual(preview["preview_entries"][0]["preview_status"], "READY")

    def test_loaded_artifact_path_is_allow_listed_and_hash_checked(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "inspect_output"
            output.mkdir()
            source = root / "source.png"
            candidate = root / "candidate.png"
            _image(source, color=(10, 20, 30))
            _image(candidate, color=(30, 20, 10))
            _write_preview(output, source)

            result = import_manual_preview_candidate(output, source, candidate)
            artifact_id = result["artifact"]["artifact_id"]
            self.assertIsNotNone(resolve_preview_artifact(output, artifact_id))
            self.assertIsNone(resolve_preview_artifact(output, "artifact-../unsafe"))
            Path(result["artifact_path"]).write_bytes(b"changed")
            self.assertIsNone(resolve_preview_artifact(output, artifact_id))

    def test_missing_or_malformed_artifact_sidecar_fails_safe_for_review_loading(self) -> None:
        with TemporaryDirectory() as tmp:
            output = Path(tmp)
            self.assertFalse(load_preview_artifacts(output)["available"])
            (output / PREVIEW_ARTIFACTS_FILENAME).write_text("[]", encoding="utf-8")
            loaded = load_preview_artifacts(output)

        self.assertTrue(loaded["available"])
        self.assertIn("error", loaded)


if __name__ == "__main__":
    unittest.main()
