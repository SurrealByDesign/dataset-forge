import csv
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from dataset_forge.pipeline import PipelineOptions, run_pipeline
from dataset_forge.quality import assess_dataset_quality, load_quality_weights


class QualityTests(unittest.TestCase):
    def test_scores_image_quality_components(self) -> None:
        rows = [_quality_row("healthy.png")]

        report, recommendations, summary = assess_dataset_quality(
            rows,
            load_quality_weights(),
        )

        row = rows[0]
        self.assertGreater(float(row["overall_quality_score"]), 60)
        self.assertEqual(row["duplicate_risk"], 0)
        self.assertEqual(row["resolution_score"], 100)
        self.assertEqual(row["brightness_consistency_score"], 100)
        self.assertGreater(float(row["contrast_score"]), 60)
        self.assertEqual(recommendations[0].recommended_action, "Recommend keep as-is")
        self.assertEqual(summary.dataset_health_score, report["dataset_health_score"])

    def test_dataset_health_falls_for_burden_and_duplicates(self) -> None:
        weights = load_quality_weights()
        healthy_rows = [
            _quality_row("one.png"),
            _quality_row("two.png"),
        ]
        unhealthy_rows = [
            _quality_row(
                "one.png",
                artifact=90,
                texture=90,
                megapixels=0.1,
                brightness=10,
                contrast=5,
            ),
            _quality_row(
                "two.png",
                artifact=90,
                texture=90,
                megapixels=4,
                brightness=90,
                contrast=70,
                exact_duplicate_of="one.png",
            ),
        ]

        healthy_report, _, _ = assess_dataset_quality(healthy_rows, weights)
        unhealthy_report, _, _ = assess_dataset_quality(unhealthy_rows, weights)

        self.assertGreater(
            healthy_report["dataset_health_score"],
            unhealthy_report["dataset_health_score"],
        )
        self.assertEqual(unhealthy_report["likely_duplicates"], 1)
        self.assertEqual(unhealthy_report["low_resolution_images"], 1)

    def test_generates_duplicate_and_cleanup_recommendations(self) -> None:
        rows = [
            _quality_row("duplicate.png", exact_duplicate_of="original.png"),
            _quality_row("artifact.png", artifact=80),
        ]

        _, recommendations, summary = assess_dataset_quality(
            rows,
            load_quality_weights(),
        )

        by_name = {item.filename: item for item in recommendations}
        self.assertEqual(by_name["duplicate.png"].severity, "CRITICAL")
        self.assertEqual(
            by_name["duplicate.png"].recommended_action,
            "Recommend duplicate removal",
        )
        self.assertEqual(
            by_name["artifact.png"].recommended_action,
            "Recommend cleanup",
        )
        self.assertEqual(
            by_name["artifact.png"].suggested_preset,
            "general_artifact_cleanup",
        )
        self.assertEqual(summary.critical_issues, 2)

    def test_custom_image_weights_change_overall_score(self) -> None:
        with TemporaryDirectory() as temp:
            config = Path(temp) / "weights.json"
            config.write_text(
                json.dumps(
                    {
                        "image_weights": {
                            "artifact_quality": 0,
                            "texture_quality": 0,
                            "duplicate_quality": 0,
                            "resolution": 1,
                            "brightness_consistency": 0,
                            "contrast": 0,
                        },
                        "dataset_weights": {
                            "exact_duplicates": 1,
                            "probable_duplicates": 0,
                            "artifact_burden": 0,
                            "texture_burden": 0,
                            "resolution_consistency": 0,
                            "brightness_consistency": 0,
                            "contrast_consistency": 0,
                            "aspect_ratio_consistency": 0,
                        },
                    }
                ),
                encoding="utf-8",
            )
            rows = [_quality_row("small.png", megapixels=0.25)]

            assess_dataset_quality(rows, load_quality_weights(config))

            self.assertEqual(
                rows[0]["overall_quality_score"],
                rows[0]["resolution_score"],
            )
            self.assertEqual(rows[0]["overall_quality_score"], 25)

    def test_health_report_writes_outputs_without_changing_sources(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            output = root / "output"
            source.mkdir()
            image_path = source / "sample.png"
            Image.new("RGB", (1200, 900), (80, 110, 140)).save(image_path)
            before = image_path.read_bytes()

            summary = run_pipeline(
                PipelineOptions(
                    input_path=source,
                    output_path=output,
                    health_report=True,
                )
            )

            health = json.loads(
                (output / "dataset_health.json").read_text(encoding="utf-8")
            )
            with (output / "recommendations.csv").open(
                newline="",
                encoding="utf-8",
            ) as handle:
                recommendations = list(csv.DictReader(handle))
            with (output / "manifest.csv").open(
                newline="",
                encoding="utf-8",
            ) as handle:
                manifest = list(csv.DictReader(handle))

            self.assertIsNotNone(summary.health)
            self.assertEqual(health["total_images"], 1)
            self.assertEqual(len(recommendations), 1)
            self.assertTrue(manifest[0]["overall_quality_score"])
            self.assertEqual(before, image_path.read_bytes())
            self.assertFalse((output / "originals").exists())


def _quality_row(
    filename: str,
    *,
    artifact: float = 10,
    texture: float = 20,
    megapixels: float = 4,
    brightness: float = 50,
    contrast: float = 35,
    aspect_ratio: float = 1.0,
    exact_duplicate_of: str = "",
    probable_duplicate_of: str = "",
) -> dict[str, object]:
    return {
        "filename": filename,
        "original_path": filename,
        "status": "analyzed",
        "artifact_score": artifact,
        "texture_score": texture,
        "megapixels": megapixels,
        "average_brightness": brightness,
        "average_contrast": contrast,
        "aspect_ratio": aspect_ratio,
        "exact_duplicate_of": exact_duplicate_of,
        "probable_duplicate_of": probable_duplicate_of,
    }


if __name__ == "__main__":
    unittest.main()
