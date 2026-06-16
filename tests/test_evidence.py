import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from dataset_forge.evidence import EVIDENCE_SCHEMA, EVIDENCE_VERSION, evidence_from_rows
from dataset_forge.pipeline import PipelineOptions, run_pipeline
from dataset_forge.recommendations.engine import recommend_evidence


class EvidenceTests(unittest.TestCase):
    def test_schema_is_versioned_and_has_future_namespaces(self) -> None:
        evidence = evidence_from_rows(
            [
                {
                    "filename": "sample.png",
                    "original_path": "sample.png",
                    "status": "analyzed",
                    "overall_quality_score": 90,
                    "artifact_score": 10,
                    "texture_score": 20,
                    "megapixels": 2,
                }
            ]
        )
        payload = evidence.to_dict()
        image = payload["images"][0]

        self.assertEqual(payload["schema"], EVIDENCE_SCHEMA)
        self.assertEqual(payload["version"], EVIDENCE_VERSION)
        self.assertIn("quality_metrics", image)
        self.assertIn("artifact_metrics", image)
        self.assertIn("texture_metrics", image)
        self.assertIn("dataset_relative_metrics", image)
        self.assertEqual(image["semantic_metrics"], {})
        self.assertEqual(image["benchmark_metrics"], {})

    def test_recommendation_engine_is_the_evidence_consumer(self) -> None:
        evidence = evidence_from_rows(
            [
                {
                    "filename": "artifact.png",
                    "original_path": "artifact.png",
                    "status": "analyzed",
                    "overall_quality_score": 40,
                    "artifact_score": 80,
                    "texture_score": 20,
                    "megapixels": 2,
                }
            ]
        )
        self.assertEqual(recommend_evidence(evidence)[0].action, "CLEAN_STRONG")

    def test_pipeline_preserves_reports_and_writes_evidence(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            output = root / "output"
            source.mkdir()
            Image.new("RGB", (64, 64), "gray").save(source / "sample.png")

            run_pipeline(
                PipelineOptions(
                    input_path=source,
                    output_path=output,
                    health_report=True,
                )
            )

            evidence = json.loads(
                (output / "evidence.json").read_text(encoding="utf-8")
            )
            self.assertEqual(evidence["version"], EVIDENCE_VERSION)
            self.assertTrue((output / "manifest.csv").is_file())
            self.assertTrue((output / "dataset_report.json").is_file())
            self.assertTrue((output / "dataset_health.json").is_file())
            self.assertTrue((output / "recommendations.csv").is_file())


if __name__ == "__main__":
    unittest.main()
