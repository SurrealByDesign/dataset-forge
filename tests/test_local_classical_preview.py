from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import numpy as np
from PIL import Image

from dataset_forge.local_classical_preview import (
    LOCAL_CLASSICAL_PROVIDER_VERSION,
    LocalClassicalPreviewError,
    generate_local_classical_preview,
)
from dataset_forge.preview_artifacts import PreviewArtifactError
from dataset_forge.preview_artifacts import import_manual_preview_candidate
from dataset_forge.review_desk import build_review_data


def _source_image(path: Path) -> None:
    arr = np.zeros((32, 32, 3), dtype=np.uint8)
    arr[:, :16] = [25, 25, 25]
    arr[:, 16:] = [230, 230, 230]
    arr[14:18, 14:18] = [255, 255, 255]
    Image.fromarray(arr).save(path)


def _write_preview(output: Path, source: Path, *, provider: str = "LOCAL_CLASSICAL") -> None:
    record = {
        "image": {"path": str(source), "filename": source.name},
        "current_findings": [
            {
                "category": "artifact.oversharpening_halo",
                "analyzer": "oversharpening_halo_analyzer/v1",
                "severity": "MEDIUM",
            }
        ],
        "recommended_operation": "REDUCE_HALO",
        "operation_rationale": "Fixture halo evidence.",
        "confidence": 0.61,
        "required_provider_type": provider,
        "preview_status": "WAITING_FOR_PROVIDER",
        "approval_state": "APPROVED",
    }
    (output / "improvement_preview.json").write_text(
        json.dumps({
            "schema": "dataset-forge/improvement-preview/v1",
            "summary": {},
            "preview_records": [record],
            "preview_entries": [record],
        }),
        encoding="utf-8",
    )


class LocalClassicalPreviewTests(unittest.TestCase):
    def test_generates_deterministic_isolated_artifact_without_modifying_source(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "inspect_output"
            output.mkdir()
            source = root / "source.png"
            _source_image(source)
            _write_preview(output, source)
            source_before = source.read_bytes()

            first = generate_local_classical_preview(output, source)
            second = generate_local_classical_preview(output, source)

            sidecar = json.loads((output / "preview_artifacts.json").read_text(encoding="utf-8"))
            preview = json.loads((output / "improvement_preview.json").read_text(encoding="utf-8"))
            artifact = sidecar["artifacts"][0]
            artifact_path = Path(first["artifact_path"])
            artifact_bytes = artifact_path.read_bytes()
            source_after = source.read_bytes()

        self.assertTrue(first["generated"])
        self.assertTrue(second["idempotent"])
        self.assertEqual(source_after, source_before)
        self.assertEqual(artifact["provider"]["type"], "LOCAL_CLASSICAL")
        self.assertEqual(artifact["provider"]["provider_version"], LOCAL_CLASSICAL_PROVIDER_VERSION)
        self.assertEqual(artifact["generation"]["operation"], "REDUCE_HALO")
        self.assertEqual(artifact["generation"]["parameters"]["edge_blend_strength"], 0.22)
        self.assertEqual(artifact["candidate"]["sha256"], hashlib.sha256(artifact_bytes).hexdigest())
        self.assertTrue(str(artifact["candidate"]["artifact_reference"]["relative_path"]).startswith("preview_artifacts/"))
        self.assertEqual(preview["preview_records"][0]["preview_status"], "READY")
        self.assertEqual(preview["preview_records"][0]["approval_state"], "NOT_REQUESTED")

    def test_generation_requires_local_classical_record(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "inspect_output"
            output.mkdir()
            source = root / "source.png"
            _source_image(source)
            _write_preview(output, source, provider="MANUAL")
            before = (output / "improvement_preview.json").read_bytes()

            with self.assertRaises(LocalClassicalPreviewError):
                generate_local_classical_preview(output, source)
            after = (output / "improvement_preview.json").read_bytes()

        self.assertEqual(after, before)
        self.assertFalse((output / "preview_artifacts.json").exists())

    def test_existing_artifact_requires_explicit_replace(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "inspect_output"
            output.mkdir()
            source = root / "source.png"
            manual = root / "manual.png"
            _source_image(source)
            Image.new("RGB", (32, 32), (40, 90, 140)).save(manual)
            _write_preview(output, source)

            import_manual_preview_candidate(output, source, manual)
            with self.assertRaises(PreviewArtifactError):
                generate_local_classical_preview(output, source)
            replaced = generate_local_classical_preview(output, source, replace_existing=True)

        self.assertTrue(replaced["generated"])

    def test_review_desk_exposes_generated_candidate_provenance(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "inspect_output"
            output.mkdir()
            source = root / "source.png"
            _source_image(source)
            _write_preview(output, source)
            (output / "inspection_report.json").write_text(
                json.dumps({"dataset_path": str(root), "dataset": {"image_count": 1}}),
                encoding="utf-8",
            )
            (output / "recommendation_summary.json").write_text(
                json.dumps({
                    "summary": {"image_count": 1, "needs_review_count": 1},
                    "recommendations": [
                        {
                            "image_path": str(source),
                            "display_label": "Needs Review",
                            "recommendation": "NEEDS_REVIEW",
                            "findings": [],
                            "finding_refs": [],
                        }
                    ],
                }),
                encoding="utf-8",
            )
            generate_local_classical_preview(output, source)

            payload = build_review_data(output)

        candidate = payload["improvement_preview"]["records"][0]["candidate_artifact"]
        self.assertTrue(candidate["available"])
        self.assertEqual(candidate["provider_type"], "LOCAL_CLASSICAL")
        self.assertEqual(candidate["generation"]["operation"], "REDUCE_HALO")


if __name__ == "__main__":
    unittest.main()
